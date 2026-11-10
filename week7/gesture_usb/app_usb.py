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

ROOT = Path(__file__).resolve().parent
ACTION_NAMES = {'open_gripper': '张开夹爪', 'close_gripper': '闭合夹爪', 'home': '回到零点', 'stop': '中断当前动作', 'clear_stop': '解除停止'}


class App:
    def __init__(self, window):
        self.window = window
        self.window.title('手势控制 · Micro-USB 网络版 · Five 中断动作')
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
        self.round_mode = 'local_simulation'
        self.recorded = False
        self.output = ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S')
        self.camera = tk.StringVar(value='0')
        self.address = tk.StringVar(value='http://192.168.55.1:8765')
        self.token = tk.StringVar()
        self.sim_cancel = threading.Event()
        self.expected = tk.StringVar(value='One')
        self.note = tk.StringVar()
        self.status = tk.StringVar(value='默认本机演练；无需连接机械臂。请启动摄像头。')
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
        for label, fn in [('准备下一条', self.arm), ('停止当前动作', self.stop), ('解除停止', self.clear)]:
            ttk.Button(controls, text=label, command=lambda f=fn: self.guard(f)).pack(side='left', padx=4)
        ttk.Label(window, text='One 食指 → 张开夹爪    Two 食指+中指 → 闭合夹爪    Three 食指+中指+无名指 → 回零').pack()
        ttk.Label(window, text='OK → 确认    Five 五指张开 → 取消当前轨迹并保持位置（软件制停，真机待验证）').pack()
        network_row = ttk.Frame(window, padding=8)
        network_row.pack(fill='x')
        ttk.Label(network_row, text='Jetson 地址').pack(side='left')
        ttk.Entry(network_row, textvariable=self.address, width=29).pack(side='left')
        ttk.Label(network_row, text='令牌').pack(side='left')
        ttk.Entry(network_row, textvariable=self.token, show='*', width=16).pack(side='left')
        for label, fn in [('连接并查询', self.connect), ('断开/本机演练', self.disconnect)]:
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
                self.status.set('已中断并进入位置保持；'+('关节反馈稳定。' if state['mode']=='hardware' else '接收端演练已中断。'))
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
        self.detail.set('状态 {} · 候选 {} · BUSY {} · {}'.format(self.control.state, self.control.candidate or '无', self.control.busy, 'Micro-USB 网络' if self.link else '本机演练'))
        self.window.after(100, self.tick)

    def send(self, command, callback):
        self.log('send', command=command, transport='usb_network' if self.link else 'local_simulation')
        if not self.link:
            self.pending += 1
            if command == 'stop':
                self.sim_cancel.set()
            elif command == 'clear_stop':
                self.sim_cancel.clear()
            def simulate():
                interrupted = self.sim_cancel.wait(2) if command in ('home', 'open_gripper', 'close_gripper') else False
                self.events.put((callback, {'mode':'local_simulation', 'status':'interrupted' if interrupted else 'done', 'command':command}, None))
            threading.Thread(target=simulate, daemon=True).start()
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
        self.log('result', command=self.round_action, reply=reply, error=error)

    def arm(self):
        self.require_frame()
        if self.pending:
            raise RuntimeError('通信或动作尚未结束，请稍候。')
        if not self.control.arm():
            raise RuntimeError('请先解除停止锁定，或等待动作结束。')
        self.round_action = self.round_result = ''
        self.round_active, self.recorded = True, False
        self.round_mode = 'usb_network_pending' if self.link else 'local_simulation'
        self.status.set('已准备；稳定做 One/Two/Three，再做 OK。保持手势不会重复执行。')

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
        self.status.set(('制停请求未确认：'+error) if error else ('制停请求已送达，等待接收端反馈。' if self.link else '本机演练动作已取消。'))

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
        self.status.set('已切回本机演练；解除停止后可继续测试。')

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
