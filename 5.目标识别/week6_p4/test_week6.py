"""Synthetic vision and simulated motion tests; never count as real trials."""
import copy
from pathlib import Path
import tempfile
import time
import unittest
from arm_interrupt import Cancelled
import cv2
import numpy as np
from sorting_core import load_config, detect_color, SortGate, make_plan, validate_motion_config
from week6_color_sorting import Runtime

HERE=Path(__file__).resolve().parent


def sample(color='red',center=(100,100)):
    return dict(kind='target',target=dict(color=color,center=center,area=2500,bbox=(75,75,50,50)))


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(HERE/'bin_map.json')

    def frame(self,color):
        frame=np.full((240,320,3),200,np.uint8)
        values={'red':(0,0,255),'yellow':(0,255,255),'green':(0,180,0),'blue':(255,0,0)}
        cv2.rectangle(frame,(80,80),(140,140),values[color],-1)
        return frame

    def test_four_colors_without_manual_selection(self):
        for color in ('red','yellow','green','blue'):
            result=detect_color(self.frame(color),self.config,[60,60,140,140])
            self.assertEqual(result['kind'],'target')
            self.assertEqual(result['target']['color'],color)
            self.assertEqual(result['target']['center'],(110,110))

    def test_roi_excludes_colored_bin_background(self):
        frame=self.frame('red')
        cv2.rectangle(frame,(230,60),(300,160),(0,255,0),-1)
        self.assertEqual(detect_color(frame,self.config)['kind'],'ambiguous')
        self.assertEqual(detect_color(frame,self.config,[60,60,140,140])['target']['color'],'red')

    def test_multiple_targets_and_black_cover_do_not_count_as_empty(self):
        frame=self.frame('red')
        cv2.rectangle(frame,(200,80),(260,140),(0,0,255),-1)
        self.assertEqual(detect_color(frame,self.config)['kind'],'ambiguous')
        self.assertEqual(detect_color(np.zeros_like(frame),self.config)['kind'],'invalid')
        self.assertEqual(detect_color(np.full_like(frame,200),self.config)['kind'],'empty')

    def test_invalid_roi(self):
        with self.assertRaises(ValueError):
            detect_color(self.frame('red'),self.config,[300,0,100,100])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate=SortGate(frames=3,empty_frames=2,reset_delay=.5)
        self.gate.start()

    def trigger(self):
        self.assertIsNone(self.gate.feed(sample(),0))
        self.assertIsNone(self.gate.feed(sample(),0))
        self.assertEqual(self.gate.feed(sample(),0)['color'],'red')

    def test_no_repeat_and_busy_occlusion_not_rearm(self):
        self.trigger()
        for _ in range(10):
            self.assertIsNone(self.gate.feed(dict(kind='empty'),0))
        self.gate.finish(True,now=1)
        for _ in range(10):
            self.assertIsNone(self.gate.feed(sample(),2))
        self.assertTrue(self.gate.need_empty)
        self.gate.feed(dict(kind='empty'),1.2)
        self.assertEqual(self.gate.empty_count,0)
        self.gate.feed(dict(kind='empty'),2)
        self.gate.feed(dict(kind='empty'),2)
        self.assertFalse(self.gate.need_empty)
        self.trigger()

    def test_color_change_and_position_jitter_reset(self):
        self.gate.feed(sample(),0)
        self.gate.feed(sample('blue'),0)
        self.assertEqual(self.gate.count,1)
        self.gate.feed(sample('blue',(200,200)),0)
        self.assertEqual(self.gate.count,1)
        self.gate.feed(dict(kind='ambiguous'),0)
        self.assertEqual(self.gate.count,0)

    def test_failure_requires_explicit_recovery(self):
        self.trigger()
        self.gate.finish(False,1)
        with self.assertRaises(RuntimeError):
            self.gate.start()
        self.assertIsNone(self.gate.feed(sample(),2))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(HERE/'bin_map.json')

    def test_original_roll_never_used_for_motion(self):
        self.assertIsNone(self.config['bin_map']['green']['pose']['roll_deg'])
        with self.assertRaises(ValueError):
            validate_motion_config(self.config,False)
        self.config['physical_calibration_confirmed']=True
        for spec in self.config['bin_map'].values():
            for key in ('pose','above'):
                spec[key]['roll_deg']=spec['raw_roll_deg']
        with self.assertRaises(ValueError):
            validate_motion_config(self.config)

    def test_candidate_rolls_still_do_not_enable_hardware(self):
        for spec in self.config['bin_map'].values():
            for key in ('pose','above'):
                spec[key]['roll_deg']=spec['diagnostic_modulo_roll_deg']
        validate_motion_config(self.config,False)
        with self.assertRaises(ValueError):
            validate_motion_config(self.config,True)

    def test_plan_lifts_before_transfer_and_releases_only_at_destination(self):
        plan=make_plan(self.config,'yellow')
        stages=[step['stage'] for step in plan]
        self.assertLess(stages.index('LIFT'),stages.index('TRANSFER_HOME'))
        self.assertLess(stages.index('PLACE'),stages.index('RELEASE'))
        self.assertEqual(plan[-1]['stage'],'RESET')
        self.assertEqual(next(s['pose'] for s in plan if s['stage']=='PICK'),self.config['p4']['pick'])


class RuntimeTests(unittest.TestCase):
    def test_interruption_does_not_open_gripper_or_return_home(self):
        config=load_config(HERE/'bin_map.json')
        runtime=Runtime(config)
        calls=[]
        class Fake:
            hardware=True
            def execute(self,color,stage):
                calls.append('APPROACH')
                stage('APPROACH')
                runtime.cancel.wait(2)
                raise Cancelled('test stop')
            def hold(self):
                calls.append('HOLD')
                return {'feedback_stable':True}
            def close(self):
                calls.append('CLOSE')
        runtime.backend=Fake()
        with tempfile.TemporaryDirectory() as directory:
            runtime.output=Path(directory)
            runtime.gate.start()
            target=None
            for _ in range(config['vision']['confirm_frames']):
                target=runtime.gate.feed(sample())
            frame=np.full((100,100,3),180,np.uint8)
            runtime.jobs.put(('sort',dict(target=target,raw=frame,annotated=frame)))
            deadline=time.monotonic()+2
            while not calls and time.monotonic()<deadline:
                time.sleep(.01)
            runtime.stop()
            while runtime.latest_trial is None and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertEqual(runtime.latest_trial['status'],'interrupted')
            self.assertFalse(runtime.observation_ready)
            self.assertIsNone(runtime.roi)
            self.assertEqual(calls,['APPROACH','HOLD'])
            runtime.close()
            runtime.actor.join(2)
            self.assertFalse(runtime.actor.is_alive())

    def test_simulated_cycle_and_stop_have_separate_manual_truth(self):
        config=load_config(HERE/'bin_map.json')
        runtime=Runtime(config)
        with tempfile.TemporaryDirectory() as directory:
            runtime.output=Path(directory)
            runtime.gate.start()
            target=None
            for _ in range(config['vision']['confirm_frames']):
                target=runtime.gate.feed(sample('green'))
            self.assertIsNotNone(target)
            frame=np.full((100,100,3),180,np.uint8)
            runtime.jobs.put(('sort',dict(target=target,raw=frame,annotated=frame)))
            deadline=time.monotonic()+4
            while runtime.latest_trial is None and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertEqual(runtime.latest_trial['status'],'done')
            self.assertEqual(runtime.latest_trial['mode'],'simulation')
            self.assertFalse((runtime.output/'manual_trials.csv').exists())
            self.assertTrue(runtime.gate.need_empty)
            runtime.close()
            runtime.actor.join(2)
            self.assertFalse(runtime.actor.is_alive())


if __name__=='__main__':
    unittest.main(verbosity=2)
