"""Local gesture recognition, Micro-USB HTTP transport and motion cancellation."""
import csv
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import mediapipe as mp
from PIL import Image, ImageTk

from control import Controller
from network_link import NetworkLink
from recognition import 创建识别器, 识别画面, 标注画面, 手势中文
from week8_settings import GESTURE_COLOR_MAP

ROOT = Path(__file__).resolve().parent
ACTION_NAMES = {'sort_red':'抓取红块→有害垃圾','sort_yellow':'抓取黄块→其他垃圾',
                'sort_green':'抓取绿块→厨余垃圾','sort_blue':'抓取蓝块→可回收垃圾',
                'prepare':'Jetson回拍摄位','stop':'停止当前动作','clear_stop':'解除停止'}


class App:
    def __init__(self, window):
        self.window = window
        self.window.title('Week8 手势选色 + OK 确认抓取 · Five 选择蓝色')
        self.control = Controller()
        self.link = None
        self.cap = self.recognizer = None
        self.frame = self.result = self.photo = None
        self.frame_at = 0
        self.timestamp = -1
        self.events = queue.Queue()
        self.pending = 0
        self.round_active = False
        self.round_action = ''
        self.round_result = ''
        self.round_mode = 'not_connected'
        self.recorded = False
        self.output = ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S')
        self.camera = tk.StringVar(value='0')
        self.address = tk.StringVar(value='http://192.168.55.1:8766')
        self.token = tk.StringVar()
        self.expected = tk.StringVar(value='One')
        self.note = tk.StringVar()
        self.status = tk.StringVar(value='先连接 Week8 Jetson 接收端；可以先启动本机摄像头观察手势。')
        self.recognition = tk.StringVar(value='等待摄像头')
        self.detail = tk.StringVar(value='WAIT · 尚未准备')
        self.summary = tk.StringVar(value='尚无测试记录')
        self.counts = []
        top = ttk.Frame(window, padding=8)
        top.pack(fill='x')
        ttk.Label(top, text='相机编号').pack(side='left')
        ttk.Entry(top, textvariable=self.camera, width=4).pack(side='left')
        for label, fn in [('启动摄像头', self.start), ('关闭摄像头', self.stop_camera), ('保存截图', self.snapshot)]:
            ttk.Button(top, text=label, command=lambda f=fn: self.guard(f)).pack(side='left', padx=3)
        self.view = ttk.Label(window, anchor='center', text='摄像头画面将在这里显示', width=85)
        self.view.pack(padx=8, pady=4)
        ttk.Label(window, textvariable=self.recognition, font=('Microsoft YaHei', 14)).pack()
        ttk.Label(window, textvariable=self.detail).pack()
        controls = ttk.Frame(window, padding=6)
        controls.pack()
        for label, fn in [('准备下一条', self.arm), ('停止当前动作', self.stop), ('解除停止', self.clear), ('Jetson回拍摄位',self.prepare_receiver)]:
            if label=='停止当前动作':
                tk.Button(controls,text=label,bg='#c62828',fg='white',command=lambda f=fn:self.guard(f)).pack(side='left',padx=4)
            else:
                ttk.Button(controls, text=label, command=lambda f=fn: self.guard(f)).pack(side='left', padx=4)
        ttk.Label(window, text='　'.join(label+'→'+color for label,color in GESTURE_COLOR_MAP.items())+'；再做 OK 才抓取').pack()
        ttk.Label(window, text='Five 已放宽识别，用于选蓝色，不再停止。停止请点击红色停止按钮或按 Esc。').pack()
        network_row = ttk.Frame(window, padding=8)
        network_row.pack(fill='x')
        ttk.Label(network_row, text='Jetson 地址').pack(side='left')
        ttk.Entry(network_row, textvariable=self.address, width=29).pack(side='left')
        ttk.Label(network_row, text='令牌').pack(side='left')
        ttk.Entry(network_row, textvariable=self.token, show='*', width=16).pack(side='left')
        for label, fn in [('连接并查询', self.connect), ('断开', self.disconnect)]:
            ttk.Button(network_row, text=label, command=lambda f=fn: self.guard(f)).pack(side='left', padx=3)
        trial = ttk.Frame(window, padding=8)
        trial.pack(fill='x')
        ttk.Label(trial, text='真实手势').pack(side='left')
        ttk.Combobox(trial, textvariable=self.expected, values=list(手势中文)+['No_Hand', 'Unknown'], state='readonly', width=10).pack(side='left')
        ttk.Entry(trial, textvariable=self.note, width=22).pack(side='left', padx=4)
        ttk.Button(trial, text='记录识别测试', command=lambda: self.guard(self.record_recognition)).pack(side='left', padx=3)
        ttk.Button(trial, text='记录本轮指令', command=lambda: self.guard(self.record_command)).pack(side='left', padx=3)
        ttk.Label(window, textvariable=self.summary).pack()
        ttk.Label(window, textvariable=self.status, wraplength=820, foreground='#005a8c', padding=8).pack(fill='x')
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.bind('<Escape>',lambda _:self.guard(self.stop))
        window.after(100, self.tick)

    def guard(self, fn):
        try:
            fn()
        except Exception as error:
            self.status.set(str(error))

    def log(self, event, **fields):
        self.output.mkdir(parents=True, exist_ok=True)
        with (self.output/'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(time=datetime.now().isoformat(), event=event, **fields), ensure_ascii=False)+'\n')

    def start(self):
        if self.cap:
            return
        cap = cv2.VideoCapture(int(self.camera.get()), cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                raise RuntimeError('摄像头无法打开；关闭其他相机程序，或尝试编号 1。')
            self.recognizer = 创建识别器(mp.tasks.vision.RunningMode.VIDEO)
            self.cap = cap
            self.status.set('摄像头已启动；先逐一测试五种手势。')
        except Exception:
            cap.release()
            raise

    def stop_camera(self):
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.recognizer:
            self.recognizer.close()
            self.recognizer = None
        self.frame = self.result = None
        self.stop()
        self.status.set('摄像头已释放，指令已停止锁定。重新启动后需解除停止并准备。')

    def tick(self):
        try:
            while True:
                callback, reply, error = self.events.get_nowait()
                self.pending -= 1
                callback(reply, error)
        except queue.Empty:
            pass
        if self.link and self.link.stop_latched.is_set():
            self.control.stop()
            state = self.link.state
            if self.link.fault:
                self.status.set('USB 网络故障；接收端将由心跳超时触发制停。请检查设备并重新连接。')
            elif state.get('stop_phase') == 'failed':
                self.status.set('制停反馈未确认！请检查设备并使用硬件停止装置。'+str(state.get('hold_result')))
            elif state.get('stop_phase') == 'held':
                self.status.set('已制停并保持位置。解除后先回拍摄位，清空 P4，再准备新指令。')
            elif state.get('stop_phase') == 'stopping':
                self.status.set('已发送制停请求，正在取消轨迹并核对位置保持反馈。')
        if self.cap:
            try:
                ok, frame = self.cap.read()
                if not ok:
                    raise RuntimeError('摄像头取帧失败')
                frame = cv2.flip(frame, 1)
                self.timestamp = max(self.timestamp+1, int(time.monotonic()*1000))
                result = 识别画面(frame, self.recognizer, self.timestamp)
                self.frame, self.result, self.frame_at = frame, result, time.monotonic()
                accepted = result['通过']
                command = self.control.feed(result['类别'], result['置信度'] if accepted else 0)
                if command:
                    if command == 'stop':
                        self.stop()
                    else:
                        self.round_action = command
                        self.send(command, self.action_done)
                annotated = 标注画面(frame, result)
                image = Image.fromarray(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
                image.thumbnail((800, 450))
                self.photo = ImageTk.PhotoImage(image)
                self.view.configure(image=self.photo, text='')
                self.recognition.set('{} {} · {:.3f} · {} · {}'.format(result['类别'], 手势中文.get(result['类别'], ''), result['置信度'], result['分数来源'], '通过' if accepted else '未通过'))
            except Exception as error:
                self.stop_camera()
                self.status.set('识别停止：'+str(error))
        remote='' if not self.link else str(self.link.state.get('vision',{}).get('p4_colors',[]))
        self.detail.set('状态 {} · 候选 {} · BUSY {} · Jetson P4 {}'.format(self.control.state, self.control.candidate or '无', self.control.busy,remote))
        self.window.after(100, self.tick)

    def send(self, command, callback):
        self.log('send', command=command, transport='usb_network' if self.link else 'not_connected')
        if not self.link:
            callback(None,'未连接 Week8 Jetson；没有发送运动指令')
            return
        link = self.link
        self.pending += 1
        def worker():
            try:
                reply = link.request(command)
                self.events.put((callback, reply, None))
            except Exception as error:
                self.events.put((callback, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def action_done(self, reply, error):
        self.control.done(failed=bool(error))
        self.round_result = 'error: '+error if error else reply.get('status', 'done')
        if reply:
            self.round_mode = reply['mode']
        self.status.set(('执行结果未知/失败：'+error) if error else '完成：'+ACTION_NAMES.get(self.round_action, '')+'（'+self.round_mode+'）；下一轮需重新准备。')
        if self.round_result == 'interrupted':
            self.control.stop()
            self.status.set('当前动作已被中断；解除停止后重新准备，不会续接原轨迹。')
        elif reply and isinstance(reply.get('outcome'),dict):
            self.status.set(reply['outcome'].get('message','动作返回')+'；下一轮重新准备。')
        self.log('result', command=self.round_action, reply=reply, error=error)

    def arm(self):
        self.require_frame()
        if not self.link:
            raise RuntimeError('先连接 Week8 Jetson')
        remote=self.link.state
        if remote.get('stopped') or remote.get('busy'):
            raise RuntimeError('Jetson 正在执行或停止锁定，先处理远端状态')
        vision=remote.get('vision',{})
        if not vision.get('view_ready'):
            raise RuntimeError('先点击 Jetson回拍摄位')
        if vision.get('p4_need_empty'):
            raise RuntimeError('先移走 P4 原物块，等待连续空区重置')
        if self.pending:
            raise RuntimeError('通信或动作尚未结束，请稍候。')
        if not self.control.arm():
            raise RuntimeError('请先解除停止锁定，或等待动作结束。')
        self.round_action = self.round_result = ''
        self.round_active, self.recorded = True, False
        self.round_mode = 'hardware_pending'
        self.status.set('已准备；1红/2黄/3绿/5蓝选择，再做 OK。Jetson 会核对 P4 的颜色。')

    def prepare_receiver(self):
        if not self.link or self.pending or self.control.busy:
            raise RuntimeError('需要已连接且没有动作/通信正在执行')
        self.control.stop()
        self.control.busy=True
        self.round_active=False
        self.round_action=self.round_result=''
        self.send('prepare',self.prepared)

    def prepared(self,reply,error):
        self.control.done(failed=bool(error))
        if error:
            self.status.set('回拍摄位失败：'+error)
        else:
            self.control.clear()
            self.status.set('Jetson 已回拍摄位。P4 放一个物块，然后点击准备下一条。')

    def stop(self):
        self.control.stop()
        self.send('stop', self.simple_done)

    def clear(self):
        if self.pending or self.control.busy:
            raise RuntimeError('动作或通信尚未结束，不能解除停止。')
        self.send('clear_stop', self.clear_done)

    def clear_done(self, reply, error):
        if error:
            self.status.set(error)
        else:
            self.control.clear()
            self.status.set('已解除停止；点击准备下一条后才会接受动作。')

    def simple_done(self, reply, error):
        self.status.set(('制停请求未确认：'+error) if error else '制停请求已送达，等待接收端反馈。')

    def connect(self):
        if self.pending or self.control.busy:
            raise RuntimeError('动作或通信进行中，不能切换连接。')
        if self.link:
            raise RuntimeError('已连接；请先断开后再更换接收端地址或令牌。')
        self.control.stop()
        self.pending += 1
        address, token = self.address.get(), self.token.get()
        def worker():
            try:
                link = NetworkLink(address, token)
                self.events.put((self.connected, link, None))
            except Exception as error:
                self.events.put((self.connected, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def connected(self, reply, error):
        if error:
            self.status.set('连接失败：'+error)
        else:
            self.link = reply
            state = reply.state
            self.status.set('USB 网络正常；接收端 {}，BUSY {}。解除停止后再准备。'.format(state['mode'], state['busy']))

    def disconnect(self):
        if self.pending or self.control.busy:
            raise RuntimeError('动作或通信进行中，不能断开。')
        if self.link:
            self.link.close()
            self.link = None
        self.control.stop()
        self.status.set('已断开；本机仍可观察识别，但不会发送抓取指令。')

    def require_frame(self):
        if self.frame is None or not self.cap or time.monotonic()-self.frame_at > 2:
            raise RuntimeError('请先启动摄像头，取得新画面。')

    def save_image(self, suffix):
        self.require_frame()
        self.output.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+suffix+'.png'
        ok, encoded = cv2.imencode('.png', 标注画面(self.frame, self.result))
        if not ok:
            raise RuntimeError('截图编码失败')
        encoded.tofile(str(self.output/name))
        return name

    def snapshot(self):
        name = self.save_image('gesture')
        self.status.set('已保存：'+str(self.output/name))

    def write_csv(self, name, row):
        self.output.mkdir(parents=True, exist_ok=True)
        target = self.output/name
        fresh = not target.exists()
        with target.open('a', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            if fresh:
                writer.writeheader()
            writer.writerow(row)

    def record_recognition(self):
        self.require_frame()
        actual = {'无手':'No_Hand', '未定义手势':'Unknown'}.get(self.result['类别'], self.result['类别'])
        correct = actual == self.expected.get() and (self.result['通过'] or actual in ('No_Hand', 'Unknown'))
        image = self.save_image('recognition_trial')
        self.write_csv('recognition_trials.csv', dict(time=datetime.now().isoformat(), expected=self.expected.get(), predicted=actual,
                       score=self.result['置信度'], score_source=self.result['分数来源'], accepted=self.result['通过'], correct=int(correct), note=self.note.get(), screenshot=image))
        self.counts.append(correct)
        self.summary.set('本次识别测试 {} 次，正确 {} 次，正确率 {:.1%}（人工逐次记录）'.format(len(self.counts), sum(self.counts), sum(self.counts)/len(self.counts)))
        self.status.set('识别测试已保存；这不代表机械臂动作验证。')

    def record_command(self):
        self.require_frame()
        if not self.round_active or self.recorded or self.pending or self.control.busy:
            raise RuntimeError('需先准备一轮并结束动作/通信；每轮只能记录一次。')
        self.write_csv('command_trials.csv', dict(time=datetime.now().isoformat(), command=self.round_action or 'none',
                       result=self.round_result or 'not_triggered', mode=self.round_mode, note=self.note.get(), screenshot=self.save_image('command_trial')))
        self.recorded = True
        self.status.set('指令记录已保存；硬件模式的 done 仅表示 SDK 返回，机械臂实际动作须现场观察并记入备注。')

    def close(self):
        if self.pending or self.control.busy:
            self.status.set('动作/通信尚未结束，请先停止锁定并等待结果后关闭。')
            return
        if self.cap:
            self.cap.release()
        if self.recognizer:
            self.recognizer.close()
        if self.link:
            self.link.close()
        self.window.destroy()


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
