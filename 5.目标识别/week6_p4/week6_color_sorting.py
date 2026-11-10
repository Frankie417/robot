"""Jetson Jupyter panel: fixed P4 color sorting, no automatic movement on import."""
import argparse
import copy
import csv
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time
import traceback
import cv2
import numpy as np
from sorting_core import COLORS, SortGate, detect_color, load_config
from hardware_backend import Backend
from arm_interrupt import Cancelled

HERE=Path(__file__).resolve().parent


class Runtime:
    def __init__(self,config,notify=lambda message:None):
        self.config=copy.deepcopy(config)
        self.notify=notify
        self.lock=threading.RLock()
        self.cancel=threading.Event()
        self.camera_stop=threading.Event()
        self.gate=SortGate(frames=config['vision']['confirm_frames'],empty_frames=config['vision']['empty_frames'],
                           tolerance=config['vision']['position_tolerance_px'],reset_delay=config['vision']['reset_delay_seconds'])
        self.backend=Backend(self.config,self.cancel,False)
        self.jobs=queue.Queue()
        self.output=HERE/'results'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.image_callback=lambda image:None
        self.last=None
        self.last_time=0
        self.camera_thread=None
        self.observation_ready=True
        self.roi=None
        self.latest_trial=None
        self.stage=''
        self.closing=False
        self.actor=threading.Thread(target=self.motion_worker,daemon=True)
        self.actor.start()

    def log(self,event,**fields):
        self.output.mkdir(parents=True,exist_ok=True)
        with self.lock:
            with (self.output/'events.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(time=datetime.now().isoformat(),event=event,**fields),ensure_ascii=False)+'\n')

    def start_camera(self):
        if self.camera_thread and self.camera_thread.is_alive():
            return
        self.camera_stop.clear()
        self.camera_thread=threading.Thread(target=self.vision_worker,daemon=True)
        self.camera_thread.start()

    def apply_roi(self,roi):
        with self.lock:
            if self.gate.busy:
                raise RuntimeError('动作期间不能更改 P4 ROI')
            if self.last is None:
                raise RuntimeError('先打开摄像头')
            detect_color(self.last['raw'],self.config,roi)
            self.roi=list(roi)
            self.gate.stop()
            self.gate.anchor=None
            self.gate.count=0
        self.notify('已设置 P4 ROI；只放一个物块，点击开始自动分拣。')

    def start_auto(self):
        with self.lock:
            if self.last is None or time.monotonic()-self.last_time>1:
                raise RuntimeError('需要新鲜的摄像头画面')
            if self.roi is None:
                raise RuntimeError('先设置只包含 P4 抓取区的 ROI，排除彩色垃圾桶和机械臂')
            if not self.observation_ready:
                raise RuntimeError('先点击回观察位，再重新设置 P4 ROI')
            if self.cancel.is_set():
                raise RuntimeError('已停止或故障；点击解除停止后再开始')
            self.gate.start()
        self.notify('自动分拣已开启；连续稳定识别后执行，不需要手动选择颜色。')

    def stop(self):
        self.cancel.set()
        with self.lock:
            self.gate.stop()
            if not self.gate.busy:
                self.gate.busy=True
                self.gate.state='STOPPING'
                self.jobs.put(('hold',None))
        self.notify('已请求中断，等待同一动作线程完成位置保持。')

    def clear_stop(self):
        with self.lock:
            if self.gate.busy or self.gate.error:
                raise RuntimeError('动作/制停未完成或存在故障，先检查日志并重新连接')
            self.cancel.clear()
            self.gate.state='STOPPED'
        self.notify('停止已解除；不会自动续接原轨迹，需重新开始自动分拣。')

    def connect(self,hardware):
        with self.lock:
            if self.gate.busy or self.gate.enabled:
                raise RuntimeError('先停止自动分拣并等待动作/制停结束')
            self.gate.busy=True
            self.gate.error=False
            self.gate.state='CONNECTING'
            self.cancel.clear()
            self.jobs.put(('connect',bool(hardware)))

    def observe(self):
        with self.lock:
            if self.gate.busy or self.gate.enabled or self.gate.error:
                raise RuntimeError('先停用自动任务并处理故障')
            if self.cancel.is_set():
                raise RuntimeError('先解除停止')
            self.gate.busy=True
            self.gate.state='MOVING_OBSERVE'
            self.jobs.put(('observe',None))

    def save_image(self,image,name):
        self.output.mkdir(parents=True,exist_ok=True)
        ok,encoded=cv2.imencode('.png',image)
        if not ok:
            raise IOError('截图编码失败')
        encoded.tofile(str(self.output/name))
        return name

    def snapshot(self):
        with self.lock:
            if self.last is None or time.monotonic()-self.last_time>1:
                raise RuntimeError('没有新鲜画面')
            image=self.last['annotated'].copy()
        name=datetime.now().strftime('%H%M%S_%f')+'_preview.png'
        self.save_image(image,name)
        self.notify('已保存 '+str(self.output/name))

    def record_trial(self,actual,actual_bin,verdict,note):
        with self.lock:
            trial=copy.deepcopy(self.latest_trial)
            if not trial or self.gate.busy:
                raise RuntimeError('请在一轮分拣完成后记录')
            path=self.output/'manual_trials.csv'
            existing=[]
            if path.exists():
                with path.open(encoding='utf-8-sig',newline='') as stream:
                    existing=list(csv.DictReader(stream))
            if any(r['trial_id']==trial['trial_id'] for r in existing):
                raise RuntimeError('本轮已经记录，请勿重复统计')
            row=dict(trial_id=trial['trial_id'],time=datetime.now().isoformat(),mode=trial['mode'],
                     actual_color=actual,detected_color=trial['color'],expected_bin=self.config['bin_map'][actual]['label'],
                     actual_bin=actual_bin,observed_result=verdict,program_result=trial['status'],
                     note=note,screenshot=trial['screenshot'])
            fresh=not path.exists()
            with path.open('a',newline='',encoding='utf-8-sig') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(row))
                if fresh:
                    writer.writeheader()
                writer.writerow(row)
        self.notify('人工观察记录已保存；程序执行完毕不自动算作抓取成功。')

    def vision_worker(self):
        # Same as week5: no capture.set(width/height/fps/fourcc) calls.
        capture=cv2.VideoCapture(self.config['camera_device'])
        try:
            if not capture.isOpened():
                raise RuntimeError('摄像头无法打开，检查占用和编号')
            while not self.camera_stop.is_set():
                ok,raw=capture.read()
                if not ok or raw is None:
                    raise RuntimeError('摄像头取帧失败；已取消新任务并请求中断')
                with self.lock:
                    roi=copy.deepcopy(self.roi)
                result=detect_color(raw,self.config,roi)
                with self.lock:
                    self.last=dict(raw=raw.copy(),annotated=result['annotated'].copy(),result=result)
                    self.last_time=time.monotonic()
                    target=self.gate.feed(result) if roi is not None else None
                    state=self.gate.state
                    count=self.gate.count
                    mode='hardware' if self.backend.hardware else 'simulation'
                    stage=self.stage
                    if target:
                        self.jobs.put(('sort',dict(target=target,raw=raw.copy(),annotated=result['annotated'].copy())))
                display=result['annotated'].copy()
                cv2.putText(display,'{} {} stable={} {}'.format(mode,state,count,stage),(10,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),2)
                self.image_callback(display)
                self.camera_stop.wait(self.config['vision']['frame_delay_seconds'])
        except Exception as error:
            self.stop()
            with self.lock:
                self.gate.error=True
                self.gate.state='ERROR'
            self.log('camera_error',error=str(error))
            self.notify(str(error))
        finally:
            capture.release()

    def motion_worker(self):
        while True:
            op,data=self.jobs.get()
            if op=='shutdown':
                self.backend.close()
                self.backend.hardware=False
                with self.lock:
                    self.gate.state='CLOSED'
                return
            started=time.monotonic()
            status='done'
            error=None
            trial=None
            try:
                if op=='connect':
                    # Checks happen before closing/creating the replacement backend.
                    if data:
                        from hardware_backend import precheck
                        precheck(self.config,self.config['sdk_dir'])
                    self.backend.close()
                    self.backend=Backend(self.config,self.cancel,hardware=data)
                    self.observation_ready=not data
                    self.roi=None
                    self.notify('真机已连接，未移动；点击回观察位。' if data else '已切换演练模式。')
                elif op=='observe':
                    self.backend.move(self.config['observation_pose'])
                    self.observation_ready=True
                    self.roi=None
                    self.notify('已回观察位；请在当前画面重新设置 P4 ROI。')
                elif op=='sort':
                    target=data['target']
                    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    image=self.save_image(data['annotated'],stamp+'_detect.png')
                    self.save_image(data['raw'],stamp+'_raw.png')
                    trial=dict(trial_id=stamp,color=target['color'],mode='hardware' if self.backend.hardware else 'simulation',screenshot=image)
                    self.log('sort_start',**trial,target=target,plan_color=target['color'])
                    def stage(name):
                        with self.lock:
                            self.stage=name
                        self.log('stage',trial_id=stamp,stage=name)
                    self.backend.execute(target['color'],stage)
                elif op=='hold':
                    self.backend.hold()
            except Cancelled:
                status='interrupted'
            except Exception as exc:
                status='error'
                error=str(exc)
                self.cancel.set()
                self.log('exception',operation=op,error=error,traceback=traceback.format_exc())
            # Never open the gripper or go Home automatically after an error.
            if self.cancel.is_set() and op not in ('hold','connect'):
                try:
                    self.log('hold_result',result=self.backend.hold())
                except Exception as exc:
                    status='error'
                    error=(error+'; ' if error else '')+'制停失败: '+str(exc)
            with self.lock:
                if self.backend.hardware and (status!='done' or op=='hold'):
                    self.observation_ready=False
                    self.roi=None
                if trial:
                    trial.update(status=status,error=error,elapsed_seconds=round(time.monotonic()-started,3))
                    self.latest_trial=trial
                    self.log('sort_result',**trial)
                    self.gate.finish(status=='done')
                    if status=='interrupted':
                        self.gate.error=False
                        self.gate.stop()
                    self.notify('{} → {}：{}；移走/清空 P4 等待重置。'.format(trial['color'],self.config['bin_map'][trial['color']]['label'],status))
                else:
                    self.gate.busy=False
                    self.gate.error=bool(error)
                    self.gate.state='ERROR' if error else 'STOPPED'
                self.stage=''
            if error:
                self.notify(error)

    def close(self):
        if self.closing:
            return
        self.closing=True
        self.camera_stop.set()
        self.stop()
        self.jobs.put(('shutdown',None))
        self.notify('已关闭预览并请求制停；待线程结束后可关闭 notebook 内核。')


def create_panel(config=None):
    import ipywidgets as widgets
    from IPython.display import display
    config=load_config(HERE/'bin_map.json') if config is None else config
    try:
        previous=globals().get('_runtime')
        if previous and previous.camera_thread and previous.camera_thread.is_alive():
            raise RuntimeError('旧预览仍在运行；先停止旧面板，等待线程退出，再重建')
        if previous and (previous.gate.busy or previous.backend.hardware):
            raise RuntimeError('旧机械臂连接仍存在；请先停止并重启内核，不能重复连接')
    except NameError:
        pass
    status=widgets.HTML(value='默认演练；在 Jetson 本机摄像头预览，先框定 P4。')
    runtime=Runtime(config,lambda text:setattr(status,'value',str(text)))
    globals()['_runtime']=runtime
    image=widgets.Image(format='jpeg',width=640)
    def show(frame):
        ok,encoded=cv2.imencode('.jpg',frame)
        if ok:
            image.value=encoded.tobytes()
    runtime.image_callback=show
    def guard(fn):
        def handler(_):
            try:
                if runtime.closing:
                    raise RuntimeError('面板正在关闭；等待线程结束后重新创建面板')
                fn()
            except Exception as error:
                status.value=str(error)
        return handler
    buttons=[]
    for label,fn in [('启动摄像头',runtime.start_camera),('开始自动分拣',runtime.start_auto),('停止当前动作',runtime.stop),('解除停止',runtime.clear_stop),('保存截图',runtime.snapshot),('关闭预览',runtime.close)]:
        button=widgets.Button(description=label)
        button.on_click(guard(fn))
        buttons.append(button)
    hardware=widgets.Button(description='连接真机')
    hardware.on_click(guard(lambda:runtime.connect(True)))
    simulate=widgets.Button(description='切回演练')
    simulate.on_click(guard(lambda:runtime.connect(False)))
    observe=widgets.Button(description='回观察位')
    observe.on_click(guard(runtime.observe))
    roi=[widgets.IntText(value=v,description=k,layout=widgets.Layout(width='145px')) for k,v in zip(('x','y','width','height'),(200,240,240,200))]
    roi_button=widgets.Button(description='应用 P4 ROI')
    roi_button.on_click(guard(lambda:runtime.apply_roi([w.value for w in roi])))
    actual=widgets.Dropdown(options=[(c, c) for c in COLORS],description='真实颜色')
    actual_bin=widgets.Dropdown(options=['厨余垃圾','其他垃圾','可回收物','有害垃圾','未投放/掉落'],description='实际投放')
    verdict=widgets.Dropdown(options=['成功','失败','未触发','误触发'],description='人工判定')
    note=widgets.Text(description='现场备注')
    record=widgets.Button(description='记录本轮实测')
    record.on_click(guard(lambda:runtime.record_trial(actual.value,actual_bin.value,verdict.value,note.value)))
    display(widgets.VBox([widgets.HTML(value='<b>Ch6 固定 P4 四色自动分拣</b>'),
                         widgets.HBox(buttons[:3]),widgets.HBox(buttons[3:]),
                         widgets.HBox([hardware,simulate,observe]),image,
                         widgets.HBox(roi+[roi_button]),status,
                         widgets.HBox([actual,actual_bin,verdict]),widgets.HBox([note,record])]))
    return runtime


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=HERE/'bin_map.json')
    parser.add_argument('--check-ik',action='store_true')
    parser.add_argument('--candidate-rolls',action='store_true',help='Only offline diagnostics; never enables hardware')
    parser.add_argument('--sdk-dir',type=str,help='Override SDK directory for offline diagnostics')
    args=parser.parse_args()
    config=load_config(args.config)
    if args.sdk_dir:
        config['sdk_dir']=args.sdk_dir
    if args.check_ik:
        if args.candidate_rolls:
            for color,spec in config['bin_map'].items():
                for key in ('pose','above'):
                    spec[key]['roll_deg']=spec['diagnostic_modulo_roll_deg']
        from hardware_backend import precheck
        print(json.dumps(precheck(config,config['sdk_dir'],require_confirmed=False),ensure_ascii=False,indent=2))
    else:
        create_panel(config)


if __name__=='__main__':
    main()
