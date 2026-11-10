"""Fixed-P4 HSV detection, state transitions and deterministic motion plans."""
import copy
import json
import math
from pathlib import Path
import time
import cv2
import numpy as np

COLORS = ('red', 'yellow', 'green', 'blue')
BGR = {'red':(0,0,255), 'yellow':(0,255,255), 'green':(0,255,0), 'blue':(255,0,0)}


def load_config(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def check_pose(pose, label):
    if not isinstance(pose, dict):
        raise ValueError(label+': 缺少位姿')
    values = [pose.get(k) for k in ('x','y','z','pitch_deg','roll_deg')]
    if any(isinstance(v, bool) or not isinstance(v, (float,int)) or not math.isfinite(v) for v in values):
        raise ValueError(label+': 请填写有限的 XYZ/Pitch/Roll，不能使用空值')
    if not -180 <= pose['pitch_deg'] <= 180 or not -180 <= pose['roll_deg'] <= 180:
        raise ValueError(label+': 角度必须是单圈有效角度，原始异常 Roll 不可直接使用')
    if not 10 <= pose['z'] <= 350:
        raise ValueError(label+': Z 超出 10..350 mm 检查范围')
    return pose


def make_plan(config, color):
    """Explicit endpoints; never synthesize a +55 mm bin waypoint blindly."""
    if color not in COLORS:
        raise ValueError('未知颜色')
    pick = config['p4']['pick']
    above = config['p4']['above']
    dest = config['bin_map'][color]['pose']
    dest_above = config['bin_map'][color]['above']
    home = config['observation_pose']
    return [dict(op='open', stage='OPEN'),
            dict(op='move', stage='APPROACH', pose=copy.deepcopy(above)),
            dict(op='move', stage='PICK', pose=copy.deepcopy(pick)),
            dict(op='close', stage='GRIP'),
            dict(op='move', stage='LIFT', pose=copy.deepcopy(above)),
            dict(op='move', stage='TRANSFER_HOME', pose=copy.deepcopy(home)),
            dict(op='move', stage='BIN_ABOVE', pose=copy.deepcopy(dest_above)),
            dict(op='move', stage='PLACE', pose=copy.deepcopy(dest)),
            dict(op='release', stage='RELEASE'),
            dict(op='move', stage='RETREAT', pose=copy.deepcopy(dest_above)),
            dict(op='move', stage='RESET', pose=copy.deepcopy(home))]


def validate_motion_config(config, require_confirmed=True):
    if require_confirmed and not config.get('physical_calibration_confirmed',False):
        raise ValueError('P4 低位、桶位 Roll、上方点及路径尚未现场确认；先演练/示教，再设置 physical_calibration_confirmed')
    for color in COLORS:
        for step in make_plan(config, color):
            if step['op']=='move':
                check_pose(step['pose'],color+'/'+step['stage'])
    for label, low, high in [('P4', config['p4']['pick'],config['p4']['above'])]+[
        (c, config['bin_map'][c]['pose'],config['bin_map'][c]['above']) for c in COLORS]:
        if high['z'] <= low['z']:
            raise ValueError(label+': 上方点必须高于低位')
        if high['x'] != low['x'] or high['y'] != low['y']:
            raise ValueError(label+': Approach/Retreat 必须同 X/Y 垂直进出')
    for key in ('move_seconds','gripper_seconds'):
        if not isinstance(config.get(key),(int,float)) or not math.isfinite(config[key]) or config[key] < .3:
            raise ValueError(key+': 必须是至少 0.3 秒的有限数值')
    for key in ('open_angle_rad','release_angle_rad'):
        if not isinstance(config.get(key),(int,float)) or not 0 < config[key] <= math.pi/2:
            raise ValueError(key+': 夹爪开口必须在 0..pi/2 弧度内')


def detect_color(frame, config, roi=None):
    """All four colors at once. Return one target, empty, or ambiguous."""
    height,width = frame.shape[:2]
    if roi is None:
        x,y,w,h = 0,0,width,height
    else:
        if len(roi)!=4 or not all(isinstance(v,int) for v in roi):
            raise ValueError('ROI 格式为整数 x,y,width,height')
        x,y,w,h=roi
        if x<0 or y<0 or w<=0 or h<=0 or x+w>width or y+h>height:
            raise ValueError('P4 ROI 超出真实画面，请重新设置')
    cropped=frame[y:y+h,x:x+w]
    hsv=cv2.cvtColor(cropped,cv2.COLOR_BGR2HSV)
    kernel=np.ones((config['vision']['kernel_size'],)*2,np.uint8)
    masks,objects={},[]
    annotated=frame.copy()
    for color in COLORS:
        mask=np.zeros((h,w),np.uint8)
        for lower,upper in config['vision']['hsv'][color]:
            mask=cv2.bitwise_or(mask,cv2.inRange(hsv,np.asarray(lower,np.uint8),np.asarray(upper,np.uint8)))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel)
        masks[color]=mask
        for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[-2]:
            area=float(cv2.contourArea(contour))
            if area<config['vision']['min_area']:
                continue
            bx,by,bw,bh=cv2.boundingRect(contour)
            moments=cv2.moments(contour)
            center=(int(moments['m10']/moments['m00'])+x,int(moments['m01']/moments['m00'])+y)
            obj=dict(color=color,center=center,area=area,bbox=(bx+x,by+y,bw,bh))
            objects.append(obj)
            cv2.rectangle(annotated,(bx+x,by+y),(bx+x+bw,by+y+bh),BGR[color],2)
            cv2.putText(annotated,color,(bx+x,max(20,by+y-5)),cv2.FONT_HERSHEY_SIMPLEX,.6,BGR[color],2)
    cv2.rectangle(annotated,(x,y),(x+w-1,y+h-1),(255,255,255),2)
    cv2.putText(annotated,'P4 ROI' if roi else 'PREVIEW - set P4 ROI',(x+5,y+24),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),2)
    # A covered/black camera frame must not count as an empty pickup zone.
    invalid=float(cv2.cvtColor(cropped,cv2.COLOR_BGR2GRAY).mean()) < config['vision']['min_scene_brightness']
    kind='invalid' if invalid else ('target' if len(objects)==1 else ('empty' if not objects else 'ambiguous'))
    return dict(kind=kind,target=objects[0] if kind=='target' else None,objects=objects,masks=masks,annotated=annotated)


class SortGate:
    def __init__(self,frames=6,empty_frames=8,tolerance=18,reset_delay=.5):
        self.frames,self.empty_frames,self.tolerance,self.reset_delay=frames,empty_frames,tolerance,reset_delay
        self.enabled=False
        self.busy=False
        self.need_empty=False
        self.error=False
        self.state='STOPPED'
        self.count=self.empty_count=0
        self.anchor=None
        self.after=0

    def start(self):
        if self.busy or self.error:
            raise RuntimeError('动作未结束或存在故障，请先处理')
        self.enabled=True
        self.state='RESET' if self.need_empty else 'READY'
        self.count=0
        self.anchor=None

    def stop(self):
        self.enabled=False
        self.count=0
        self.anchor=None
        self.state='STOPPING' if self.busy else 'STOPPED'

    def feed(self,result,now=None):
        now=time.monotonic() if now is None else now
        if not self.enabled or self.busy or self.error:
            return None
        if self.need_empty:
            self.state='RESET'
            if now < self.after:
                return None
            self.empty_count=self.empty_count+1 if result['kind']=='empty' else 0
            if self.empty_count>=self.empty_frames:
                self.need_empty=False
                self.empty_count=0
                self.state='READY'
            return None
        if result['kind']!='target':
            self.count=0
            self.anchor=None
            self.state='DETECT'
            return None
        target=result['target']
        same=(self.anchor is not None and target['color']==self.anchor['color'] and
              math.hypot(target['center'][0]-self.anchor['center'][0],target['center'][1]-self.anchor['center'][1])<=self.tolerance)
        self.count=self.count+1 if same else 1
        if not same:
            self.anchor=copy.deepcopy(target)
        self.state='CONFIRM'
        if self.count>=self.frames:
            self.busy=True
            self.state='BUSY'
            self.count=0
            return copy.deepcopy(target)
        return None

    def finish(self,success,now=None):
        self.busy=False
        self.need_empty=True
        self.empty_count=self.count=0
        self.anchor=None
        self.after=(time.monotonic() if now is None else now)+self.reset_delay
        if not success:
            self.enabled=False
            self.error=True
            self.state='ERROR'
        else:
            self.state='RESET' if self.enabled else 'STOPPED'
