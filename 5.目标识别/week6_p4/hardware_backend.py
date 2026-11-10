"""Offline IK before UART connection; one motion worker owns the arm."""
import math
from pathlib import Path
import sys
import time
import numpy as np
from sorting_core import COLORS, make_plan, validate_motion_config, check_pose
from arm_interrupt import InterruptibleArm, Cancelled


def precheck(config,sdk_dir,require_confirmed=True):
    validate_motion_config(config,require_confirmed)
    sdk=Path(sdk_dir).resolve()
    if not (sdk/'arm5dof_kinematic.py').is_file():
        raise FileNotFoundError('找不到 SDK: '+str(sdk))
    sys.path.insert(0,str(sdk))
    from arm5dof_kinematic import Arm5DoFKinematic
    k,b=np.loadtxt(str(sdk/'config/z_error_polyfit.txt'),delimiter=',')
    solver=Arm5DoFKinematic()
    checked=[]
    seen=set()
    for color in COLORS:
        for step in make_plan(config,color):
            if step['op']!='move':
                continue
            pose=step['pose']
            key=tuple(pose[k] for k in ('x','y','z','pitch_deg','roll_deg'))
            if key in seen:
                continue
            seen.add(key)
            z=pose['z']+float(k)*math.hypot(pose['x'],pose['y'])+float(b)
            solutions=solver.inverse_kinematic(pose['x'],pose['y'],z,
                math.radians(pose['pitch_deg']),math.radians(pose['roll_deg']))
            if not solutions:
                raise ValueError('IK 不可达，尚未连接舵机：'+color+'/'+step['stage']+' '+str(pose))
            checked.append(dict(color=color,stage=step['stage'],pose=pose,solutions=len(solutions)))
    return checked


class Backend:
    def __init__(self,config,cancel,hardware=False):
        self.config,self.cancel,self.hardware=config,cancel,hardware
        self.robot=None
        if hardware:
            precheck(config,config['sdk_dir'])
            self.robot=InterruptibleArm(config['sdk_dir'],config['arm_port'],cancel)

    def check(self):
        if self.cancel.is_set():
            raise Cancelled('分拣已取消')

    def move(self,pose):
        self.check()
        if not self.hardware:
            if self.cancel.wait(.12):
                self.check()
            return
        arm=self.robot.arm
        adjusted=arm.adjust_tool_posi([pose['x'],pose['y'],pose['z']])
        reachable,_=arm.inverse_kinematic(adjusted,math.radians(pose['pitch_deg']),math.radians(pose['roll_deg']))
        self.check()
        if not reachable:
            raise RuntimeError('运行时 IK 不可达，停止后续动作')
        result=arm.set_tool_pose([pose['x'],pose['y'],pose['z']],
            tool_pitch=math.radians(pose['pitch_deg']),tool_roll=math.radians(pose['roll_deg']),
            T=self.config['move_seconds'],is_soft_move=True,is_wait=True,callback=self.check)
        if result is False:
            raise RuntimeError('SDK 拒绝目标位姿')
        self.wait_settled()

    def wait_settled(self):
        if not self.hardware:
            return
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            self.check()
            if self.robot.manager.is_stop():
                return
            self.cancel.wait(.02)
        raise TimeoutError('关节未在等待时间内到位')

    def execute(self,color,stage_callback):
        for step in make_plan(self.config,color):
            self.check()
            stage_callback(step['stage'])
            if step['op']=='move':
                self.move(step['pose'])
            elif not self.hardware:
                if self.cancel.wait(.12):
                    self.check()
            else:
                arm=self.robot.arm
                if step['op']=='close':
                    arm.gripper_close(T=self.config['gripper_seconds'],callback=self.check)
                else:
                    key='release_angle_rad' if step['op']=='release' else 'open_angle_rad'
                    arm.gripper_open(angle=self.config[key],T=self.config['gripper_seconds'],callback=self.check)
                self.wait_settled()

    def hold(self):
        if self.hardware:
            return self.robot.hold()
        return {'simulation_interrupted':True}

    def close(self):
        if self.robot:
            self.robot.close()
