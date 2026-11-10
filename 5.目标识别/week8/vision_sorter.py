"""Jetson color verification and Week6's supplied fixed-P4 pick sequence."""
from datetime import datetime
import copy
import json
import math
from pathlib import Path
import sys
import threading
import time
import cv2
import numpy as np
from arm_interrupt import InterruptibleArm,Cancelled
from week8_settings import SORT_CONFIG

COLORS=('red','yellow','green','blue')
BGR={'red':(0,0,255),'yellow':(0,255,255),'green':(0,255,0),'blue':(255,0,0)}


def detect_color(frame,config):
    h,w=frame.shape[:2]
    x1,y1,x2,y2=config['roi'] if config['roi'] is not None else (0,0,w,h)
    if not (0<=x1<x2<=w and 0<=y1<y2<=h):
        raise ValueError('P4 ROI 超出实际相机画面；格式 x1,y1,x2,y2')
    crop=frame[y1:y2,x1:x2]
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    kernel=np.ones((5,5),np.uint8)
    objects=[];canvas=frame.copy()
    for color in COLORS:
        mask=np.zeros(crop.shape[:2],np.uint8)
        for lower,upper in config['hsv'][color]:
            mask=cv2.bitwise_or(mask,cv2.inRange(hsv,np.asarray(lower,np.uint8),np.asarray(upper,np.uint8)))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel)
        for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[-2]:
            area=float(cv2.contourArea(contour))
            if area<config['min_area']:
                continue
            x,y,bw,bh=cv2.boundingRect(contour)
            target=dict(color=color,pixel=(x+x1+bw//2,y+y1+bh//2),area=area)
            objects.append(target)
            cv2.rectangle(canvas,(x+x1,y+y1),(x+x1+bw,y+y1+bh),BGR[color],2)
            cv2.putText(canvas,color,(x+x1,max(20,y+y1-5)),cv2.FONT_HERSHEY_SIMPLEX,.6,BGR[color],2)
    cv2.rectangle(canvas,(x1,y1),(x2,y2),(255,255,255),1)
    usable=float(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY).mean())>=config['min_scene_brightness']
    return dict(objects=objects,usable=usable,canvas=canvas)


class CameraMonitor:
    def __init__(self,config):
        self.config=config
        self.cv=threading.Condition(threading.RLock())
        self.stop_event=threading.Event()
        self.latest=None;self.error=None;self.sequence=0
        self.need_empty=False;self.empty_count=0;self.empty_after=0
        self.thread=threading.Thread(target=self.read,daemon=True)

    def start(self):
        self.thread.start()
        with self.cv:
            self.cv.wait_for(lambda:self.latest is not None or self.error is not None,timeout=3)
        self.health()

    def read(self):
        cap=cv2.VideoCapture(self.config['camera_device'])
        try:
            if not cap.isOpened():
                raise RuntimeError('Jetson 摄像头无法打开')
            while not self.stop_event.is_set():
                ok,raw=cap.read()
                if not ok or raw is None:
                    raise RuntimeError('Jetson 摄像头取帧失败')
                result=detect_color(raw,self.config)
                with self.cv:
                    self.sequence+=1
                    self.latest=dict(result,raw=raw.copy(),time=time.monotonic(),sequence=self.sequence)
                    if self.need_empty and self.latest['time']>=self.empty_after:
                        self.empty_count=self.empty_count+1 if result['usable'] and not result['objects'] else 0
                        if self.empty_count>=self.config['empty_frames']:
                            self.need_empty=False
                    self.cv.notify_all()
        except Exception as exc:
            with self.cv:
                self.error=type(exc).__name__+': '+str(exc)
                self.cv.notify_all()
        finally:
            cap.release()

    def health(self):
        with self.cv:
            if self.error:
                raise RuntimeError(self.error)
            if self.latest is None or time.monotonic()-self.latest['time']>self.config['frame_timeout']:
                raise RuntimeError('Jetson 相机没有新鲜画面')

    def next_after(self,cutoff,cancel,timeout=2):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if cancel.is_set():
                raise Cancelled('Cancelled while waiting for camera')
            with self.cv:
                self.cv.wait(timeout=.04)
                self.health()
                if self.latest['time']>cutoff:
                    return dict(self.latest)
        raise RuntimeError('等待 Jetson 新帧超时')

    def require_empty(self,cutoff):
        with self.cv:
            self.need_empty=True
            self.empty_count=0
            self.empty_after=cutoff

    def state(self):
        with self.cv:
            return dict(camera_error=self.error,camera_fresh=self.latest is not None and time.monotonic()-self.latest['time']<=self.config['frame_timeout'],
                        p4_colors=[] if self.latest is None else [obj['color'] for obj in self.latest['objects']],
                        p4_need_empty=self.need_empty,empty_frames=self.empty_count)

    def jpeg(self):
        with self.cv:
            if self.latest is None:
                return None
            image=self.latest['canvas'].copy()
        ok,encoded=cv2.imencode('.jpg',image)
        return encoded.tobytes() if ok else None

    def close(self):
        self.stop_event.set()
        self.thread.join(2)
        if self.thread.is_alive():
            raise RuntimeError('相机读取仍未退出，勿重复启动')


def sdk_poses(config):
    sdk=Path(config['sdk_dir']).resolve()
    if not (sdk/'arm5dof_kinematic.py').is_file():
        raise FileNotFoundError('未找到课程 SDK：'+str(sdk))
    sys.path.insert(0,str(sdk))
    from config import ARM_POSE_DICT,PITCH_PANEL_A,PITCH_PANEL_B,PITCH_PANEL_C
    from arm5dof_kinematic import Arm5DoFKinematic
    k,b=np.loadtxt(str(sdk/'config/z_error_polyfit.txt'),delimiter=',')
    def from_values(values):
        x,y,z,pitch,roll=values
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError('位姿含非法数值')
        return ([float(x),float(y),float(z)],math.radians(pitch),math.radians(roll%360))
    poses={'pick':from_values(config['p4_pick']),'above':from_values(config['p4_above'])}
    for name in ('home','capture_image'):
        x,y,z,pitch,roll=ARM_POSE_DICT[name]
        adjusted=z+float(k)*math.hypot(x,y)+float(b)
        if pitch is None:
            pitch=PITCH_PANEL_A*math.hypot(x,y)+PITCH_PANEL_B*adjusted+PITCH_PANEL_C
        poses[name]=([float(x),float(y),float(z)],pitch,roll)
    for color in COLORS:
        poses[color]=from_values(config['bin_map'][color]['pose'])
    solver=Arm5DoFKinematic()
    for name,(xyz,pitch,roll) in poses.items():
        x,y,z=xyz
        adjusted=z+float(k)*math.hypot(x,y)+float(b)
        if not solver.inverse_kinematic(x,y,adjusted,pitch,roll):
            raise ValueError('IK 无解，未连接串口：'+name+' '+str(xyz))
    return poses


class Week8Arm:
    def __init__(self,cancel,config=None):
        self.cancel=cancel
        self.config=copy.deepcopy(SORT_CONFIG if config is None else config)
        self.poses=sdk_poses(self.config)
        self.robot=InterruptibleArm(self.config['sdk_dir'],self.config['arm_port'],cancel)
        self.camera=CameraMonitor(self.config)
        self.view_ready=False
        self.stage='CONNECTED_NOT_MOVED'
        self.last_outcome=None
        self.output=Path.cwd()/'week8_records'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        try:
            self.camera.start()
        except Exception:
            self.camera.stop_event.set()
            self.camera.thread.join(2)
            self.robot.close()
            raise

    def status(self):
        return dict(self.camera.state(),view_ready=self.view_ready,stage=self.stage,last_outcome=self.last_outcome)

    def validate_command(self,command):
        self.camera.health()
        if command=='prepare':
            return
        if command not in ('sort_red','sort_yellow','sort_green','sort_blue'):
            raise ValueError('未知 Week8 指令')
        if not self.view_ready:
            raise ValueError('先发送“Jetson 回拍摄位”指令')
        if self.camera.state()['p4_need_empty']:
            raise ValueError('上一轮 P4 尚未连续清空；不能重复抓取')

    def log(self,event,**fields):
        self.output.mkdir(parents=True,exist_ok=True)
        with (self.output/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(time=datetime.now().isoformat(),event=event,stage=self.stage,**fields),ensure_ascii=False)+'\n')

    def check(self):
        self.robot.check()
        self.camera.health()

    def settled(self):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            self.check()
            if self.robot.manager.is_stop():
                return
            self.cancel.wait(.02)
        raise RuntimeError('等待关节到位超时')

    def move(self,name):
        self.stage=name
        self.check()
        xyz,pitch,roll=self.poses[name]
        result=self.robot.arm.set_tool_pose(xyz,tool_pitch=pitch,tool_roll=roll,T=self.config['move_seconds'],
                                           is_soft_move=True,is_wait=True,callback=self.check)
        if result is False:
            raise RuntimeError(name+' 运动 IK 失败')
        self.settled()

    def gripper(self,close):
        self.stage='GRIP_CLOSE' if close else 'GRIP_OPEN'
        self.check()
        method=self.robot.arm.gripper_close if close else self.robot.arm.gripper_open
        method(T=self.config['gripper_seconds'],is_wait=True,callback=self.check)
        self.settled()

    def execute(self,command):
        self.validate_command(command)
        if command=='prepare':
            self.view_ready=False
            self.move('capture_image')
            cutoff=time.monotonic()+self.config['post_return_settle']
            if self.camera.state()['p4_need_empty']:
                self.camera.require_empty(cutoff)
            self.camera.next_after(cutoff,self.cancel,timeout=3)
            self.view_ready=True
            self.stage='READY_FOR_GESTURE'
            return dict(prepared=True,moved='capture_image')
        color=command[len('sort_'):]
        self.stage='VERIFY_SELECTED_'+color.upper()
        # Final color check happens before even opening the gripper.
        frame=self.camera.next_after(time.monotonic(),self.cancel)
        objects=frame['objects']
        if not frame['usable'] or len(objects)!=1:
            raise ValueError('P4 必须恰好有一个有效色块，当前数量 '+str(len(objects)))
        if objects[0]['color']!=color:
            raise ValueError('手势选择 '+color+'，但 P4 识别到 '+objects[0]['color']+'；未抓取')
        self.output.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now().strftime('%H%M%S_%f')
        ok,encoded=cv2.imencode('.png',frame['canvas'])
        if not ok:
            raise IOError('识别截图编码失败')
        filename=stamp+'_'+color+'.png';encoded.tofile(str(self.output/filename))
        self.log('sort_start',selected_color=color,detected_color=objects[0]['color'],screenshot=filename)
        self.view_ready=False
        self.camera.require_empty(float('inf'))
        self.gripper(False)
        self.move('above');self.move('pick');self.gripper(True)
        self.move('above');self.move('home');self.move(color);self.gripper(False)
        self.move('home');self.move('capture_image')
        returned=time.monotonic()
        self.camera.require_empty(returned+self.config['post_return_settle'])
        self.stage='VERIFY_P4_CLEAR'
        deadline=time.monotonic()+self.config['p4_clear_timeout']
        while time.monotonic()<deadline and self.camera.state()['p4_need_empty']:
            self.check()
            self.cancel.wait(.04)
        self.view_ready=True
        clear=not self.camera.state()['p4_need_empty']
        self.last_outcome=dict(selected_color=color,detected_color=objects[0]['color'],target_bin=self.config['bin_map'][color]['bin'],
                               commands_returned=True,p4_clear=clear,actual_bin_observed=False,screenshot=filename,
                               message='P4 已清空，桶内结果待人工确认' if clear else '动作已返回但 P4 未清空；检查抓取并移走物块，不会重复抓取')
        self.stage='READY_FOR_GESTURE' if clear else 'WAIT_P4_CLEAR'
        self.log('sort_returned',outcome=self.last_outcome)
        return self.last_outcome

    def hold(self):
        self.view_ready=False
        self.camera.require_empty(float('inf'))
        self.stage='HOLDING'
        report=self.robot.hold()
        self.stage='STOPPED_HELD'
        return report

    def close(self):
        try:
            self.camera.close()
        finally:
            self.robot.close()
