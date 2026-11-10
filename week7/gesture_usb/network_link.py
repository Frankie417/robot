"""Independent HTTP requests: stopping never waits behind a motion request."""
import json
import threading
import time
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError
import uuid


class NetworkLink:
    def __init__(self, url, token):
        self.url, self.token = url.rstrip('/'), token.strip()
        self.session = None
        self.epoch = None
        self.closed = threading.Event()
        self.stop_latched = threading.Event()
        self.fault = None
        self.motion_lock = threading.Lock()
        state = self.call('/status')
        self.session, self.epoch = state['session'], state['epoch']
        self.state = state
        self.call('/heartbeat', {})
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()

    def call(self, path, packet=None):
        if packet is not None:
            packet = dict(packet, session=self.session)
        data = None if packet is None else json.dumps(packet).encode('utf-8')
        request = Request(self.url+path, data=data,
                          headers={'X-Gesture-Token':self.token, 'Content-Type':'application/json'})
        # USB gadget traffic is local; bypass system HTTP proxies.
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(request, timeout=.8) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(json.loads(exc.read()).get('error', str(exc))) from exc
        if self.session and 'session' in result and result['session'] != self.session:
            raise RuntimeError('接收端已重启，必须重新连接')
        return result

    def heartbeat(self):
        while not self.closed.wait(.25):
            try:
                state = self.call('/heartbeat', {})
                self.state = state
                if state['stopped'] and state['epoch'] > self.epoch:
                    self.stop_latched.set()
            except Exception as exc:
                self.fault = str(exc)
                self.stop_latched.set()
                # Best effort explicit stop; receiver watchdog is the fallback.
                try:
                    self.call('/stop', {})
                except Exception:
                    pass
                return

    def request(self, command, timeout=15):
        if command == 'stop':
            self.stop_latched.set()
            self.state = self.call('/stop', {})
            self.epoch = self.state['epoch']
            return dict(self.state, status='stopping')
        if self.fault:
            raise RuntimeError('网络异常，请检查机械臂并重新连接：'+self.fault)
        if command == 'status':
            return self.call('/status')
        if command == 'clear_stop':
            self.state = self.call('/status')
            self.epoch = self.state['epoch']
            state = self.call('/clear', {'epoch':self.epoch})
            self.state = state
            self.stop_latched.clear()
            return state
        if self.stop_latched.is_set():
            raise RuntimeError('远端已停止，请先解除停止')
        # Capture epoch before dispatch; a concurrent stop invalidates delayed actions.
        epoch = self.epoch
        if not self.motion_lock.acquire(False):
            raise RuntimeError('已有动作等待执行结果')
        try:
            identifier = uuid.uuid4().hex
            self.call('/command', {'id':identifier, 'command':command, 'epoch':epoch})
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                result = self.call('/result/'+identifier)
                if result['status'] != 'running':
                    if result['status'] == 'error':
                        raise RuntimeError(result.get('error') or '执行/制停失败')
                    return result
                if self.closed.wait(.05):
                    raise RuntimeError('连接已关闭，执行结果未知')
            raise TimeoutError('动作结果超时，请检查机械臂，禁止直接重发')
        except Exception:
            try:
                self.request('stop')
            except Exception:
                pass
            raise
        finally:
            self.motion_lock.release()

    def close(self):
        try:
            self.request('stop')
        except Exception as exc:
            # Permit reconnect after unplugging USB; the receiver watchdog
            # remains responsible for stopping when this request cannot arrive.
            self.fault = str(exc)
        finally:
            self.closed.set()
            self.thread.join(2)
