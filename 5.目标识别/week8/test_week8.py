"""No real UART or camera: geometry, state machine, HTTP and source motion plan."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import cv2
import numpy as np
from control import Controller
from recognition import classify_geometry,创建识别器,识别画面,mp
from week8_settings import SORT_CONFIG,GESTURE_COLOR_MAP
from vision_sorter import Week8Arm,detect_color,sdk_poses
from receiver import Engine,make_server
from network_link import NetworkLink
from arm_interrupt import Cancelled


def wait_until(predicate,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Timed out')


class GestureTests(unittest.TestCase):
    def test_five_is_color_selection_not_stop(self):
        c=Controller();c.arm()
        self.assertIsNone(c.feed('Five',.55,1))
        self.assertIsNone(c.feed('Five',.55,1))
        self.assertEqual(c.candidate,'Five')
        self.assertFalse(c.stopped)
        for _ in range(3):
            result=c.feed('OK',.9,2)
        self.assertEqual(result,'sort_blue')

    def test_all_four_mappings_and_one_shot(self):
        for gesture,color in GESTURE_COLOR_MAP.items():
            c=Controller();c.arm()
            for _ in range(3):
                self.assertIsNone(c.feed(gesture,.95,1))
            for _ in range(3):
                result=c.feed('OK',.95,2)
            self.assertEqual(result,'sort_'+color)
            self.assertIsNone(c.feed('OK',.95,3))
            self.assertIsNone(c.feed('Five',.99,3))
            c.done()
            self.assertFalse(c.armed)

    def test_five_low_score_and_ok_threshold(self):
        c=Controller();c.arm()
        for _ in range(5): c.feed('Five',.49)
        self.assertIsNone(c.candidate)
        for _ in range(2): c.feed('Five',.55)
        for _ in range(5): self.assertIsNone(c.feed('OK',.55))
        self.assertFalse(c.busy)

    def test_candidate_expiry(self):
        c=Controller();c.arm()
        for _ in range(3): c.feed('One',.9,1)
        for _ in range(3): self.assertIsNone(c.feed('OK',.9,10))
        self.assertFalse(c.busy)

    def test_relaxed_palm_geometry(self):
        label,score,source=classify_geometry([1.60,1.65,1.62,1.58],.9,'None',.1)
        self.assertEqual(label,'Five')
        self.assertGreaterEqual(score,.5)
        self.assertIn('几何',source)

    def test_ok_and_three_not_stolen_by_five(self):
        self.assertEqual(classify_geometry([1,2.2,2.2,2.2],.2,'Open_Palm',.9)[0],'OK')
        self.assertEqual(classify_geometry([2.2,2.2,2.2,1.2],1,'Open_Palm',.9)[0],'Three')
        self.assertNotEqual(classify_geometry([1.0]*4,1,'Closed_Fist',.95)[0],'Five')

    def test_official_five_score_052_is_accepted(self):
        self.assertEqual(classify_geometry([1.4]*4,.48,'Open_Palm',.52)[0],'Five')

    def test_model_loads_no_hand_is_blocked(self):
        with 创建识别器(mp.tasks.vision.RunningMode.IMAGE) as model:
            result=识别画面(np.zeros((480,640,3),np.uint8),model)
        self.assertEqual(result['类别'],'无手')
        self.assertFalse(result['通过'])


class FakeCamera:
    def __init__(self,color='red'):
        self.color=color;self.need_empty=False;self.auto_clear=True;self.error=False
        self.raw=np.full((480,640,3),120,np.uint8)
    def health(self):
        if self.error: raise RuntimeError('Camera lost')
    def next_after(self,*args,**kwargs):
        self.health()
        return dict(objects=[] if self.color is None else [dict(color=self.color,pixel=(300,270))],
                    usable=True,canvas=self.raw,raw=self.raw)
    def state(self):
        return dict(p4_need_empty=self.need_empty,camera_error=None,p4_colors=[] if self.color is None else [self.color],stage='test')
    def require_empty(self,cutoff):
        self.need_empty=True if cutoff==float('inf') else not self.auto_clear
    def close(self): pass


class FakeRobot:
    def __init__(self,cancel):
        self.cancel=cancel;self.calls=[];self.arm=self;self.manager=self
    def check(self):
        if self.cancel.is_set(): raise Cancelled('test cancel')
    def set_tool_pose(self,xyz,**kwargs): self.calls.append(('move',tuple(xyz)));return True
    def gripper_open(self,**kwargs): self.calls.append(('open',))
    def gripper_close(self,**kwargs): self.calls.append(('close',))
    def is_stop(self): return True
    def hold(self): self.calls.append(('hold',));return {'feedback_stable':True}
    def close(self): pass


def fake_arm(cancel,output,color='red'):
    arm=Week8Arm.__new__(Week8Arm)
    arm.cancel=cancel;arm.config=copy.deepcopy(SORT_CONFIG)
    arm.config['p4_clear_timeout']=.03;arm.config['post_return_settle']=0
    arm.poses={'pick':(list(arm.config['p4_pick'][:3]),0,0),'above':(list(arm.config['p4_above'][:3]),0,0),
               'home':([150,0,200],0,0),'capture_image':([105,0,60],0,0)}
    arm.poses.update({c:(list(v['pose'][:3]),0,0) for c,v in arm.config['bin_map'].items()})
    arm.robot=FakeRobot(cancel);arm.camera=FakeCamera(color)
    arm.view_ready=True;arm.stage='READY';arm.last_outcome=None;arm.output=Path(output)
    return arm


class MotionTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory()
    def tearDown(self): self.temp.cleanup()

    def test_wrong_color_does_not_even_open_gripper(self):
        arm=fake_arm(threading.Event(),self.temp.name,'blue')
        with self.assertRaisesRegex(ValueError,'P4'):
            arm.execute('sort_red')
        self.assertEqual(arm.robot.calls,[])

    def test_no_object_no_grab(self):
        arm=fake_arm(threading.Event(),self.temp.name,None)
        with self.assertRaises(ValueError): arm.execute('sort_red')
        self.assertFalse(arm.robot.calls)

    def test_sequence_uses_supplied_poses_and_no_extra_descent(self):
        arm=fake_arm(threading.Event(),self.temp.name,'green')
        outcome=arm.execute('sort_green')
        expected=[('open',),('move',tuple(SORT_CONFIG['p4_above'][:3])),('move',tuple(SORT_CONFIG['p4_pick'][:3])),
                  ('close',),('move',tuple(SORT_CONFIG['p4_above'][:3])),('move',(150,0,200)),
                  ('move',tuple(SORT_CONFIG['bin_map']['green']['pose'][:3])),('open',),
                  ('move',(150,0,200)),('move',(105,0,60))]
        self.assertEqual(arm.robot.calls,expected)
        self.assertTrue(outcome['p4_clear'])
        self.assertFalse(outcome['actual_bin_observed'])

    def test_uncleared_p4_blocks_next_grab(self):
        arm=fake_arm(threading.Event(),self.temp.name,'red')
        arm.camera.auto_clear=False
        outcome=arm.execute('sort_red')
        self.assertFalse(outcome['p4_clear'])
        before=list(arm.robot.calls)
        with self.assertRaises(ValueError): arm.execute('sort_red')
        self.assertEqual(before,arm.robot.calls)

    def test_cancel_blocks_remaining_motion(self):
        event=threading.Event();arm=fake_arm(event,self.temp.name)
        event.set()
        with self.assertRaises(Cancelled): arm.execute('sort_red')
        self.assertFalse(arm.robot.calls)


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=Engine(lambda event:fake_arm(event,self.temp.name))
        self.server=make_server(self.engine,'token','127.0.0.1',0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])
        self.link=NetworkLink(self.url,'token');self.link.request('clear_stop')
    def tearDown(self):
        self.link.close();self.server.shutdown();self.server.server_close();self.engine.close();self.temp.cleanup()

    def test_confirmed_command_roundtrip(self):
        result=self.link.request('sort_red')
        self.assertEqual(result['status'],'done')
        self.assertEqual(result['outcome']['selected_color'],'red')

    def test_wrong_selected_color_returns_error_no_grab(self):
        with self.assertRaisesRegex(RuntimeError,'P4'):
            self.link.request('sort_blue')
        self.assertFalse(any(c[0] in ('open','close','move') for c in self.engine.arm.robot.calls))

    def test_duplicate_request_does_not_repeat(self):
        epoch=self.engine.epoch
        self.engine.submit('same','sort_red',epoch)
        wait_until(lambda:not self.engine.busy)
        calls=len(self.engine.arm.robot.calls)
        self.assertEqual(self.engine.submit('same','sort_red',epoch)['status'],'done')
        self.assertEqual(calls,len(self.engine.arm.robot.calls))
        with self.assertRaises(ValueError): self.engine.submit('same','sort_blue',epoch)

    def test_stop_invalidates_delayed_command(self):
        old=self.engine.epoch
        self.link.request('stop');wait_until(lambda:not self.engine.busy)
        self.link.request('clear_stop')
        with self.assertRaises(ValueError): self.engine.submit('late','sort_red',old)

    def test_manual_stop_preempts_running_action(self):
        def slow(command):
            if self.engine.cancel.wait(2): raise Cancelled('interrupted')
        self.engine.arm.execute=slow
        replies=[]
        worker=threading.Thread(target=lambda:replies.append(self.link.request('sort_red')))
        worker.start();wait_until(lambda:self.engine.busy)
        self.link.request('stop');worker.join(2)
        self.assertEqual(replies[0]['status'],'interrupted')
        self.assertTrue(self.engine.stopped)

    def test_camera_loss_stops_running_action(self):
        def slow(command):
            if self.engine.cancel.wait(2): raise Cancelled('camera stop')
        self.engine.arm.execute=slow
        replies=[]
        worker=threading.Thread(target=lambda:replies.append(self.link.request('sort_red')))
        worker.start();wait_until(lambda:self.engine.busy)
        self.engine.arm.camera.error=True
        worker.join(2)
        self.assertEqual(replies[0]['status'],'interrupted')

    def test_lost_heartbeat_stops_running_action(self):
        def slow(command):
            if self.engine.cancel.wait(3): raise Cancelled('heartbeat stop')
        self.engine.arm.execute=slow
        self.link.closed.set();self.link.thread.join(1)
        self.engine.heartbeat()
        self.engine.submit('lost-link','sort_red',self.engine.epoch)
        wait_until(lambda:self.engine.results['lost-link']['status']=='interrupted')
        self.assertTrue(self.engine.stopped)

    def test_week7_service_is_rejected(self):
        original=self.engine.status
        self.engine.status=lambda:dict(original(),api_version='week7')
        try:
            with self.assertRaisesRegex(RuntimeError,'Week8'):
                NetworkLink(self.url,'token')
        finally:
            self.engine.status=original


if __name__=='__main__':
    unittest.main(verbosity=2)
