"""Newline-delimited JSON bridge protocol. Never send this to a servo board."""
import json
import queue
import threading
import time
import uuid
import serial


class SerialLink:
    def __init__(self, port=None, baud=115200, wire=None):
        self.wire = wire if wire is not None else serial.Serial(port, baud, timeout=0.1, write_timeout=1)
        self.pending = {}
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        buffer = b''
        while not self.closed.is_set():
            try:
                chunk = self.wire.read(1)
                if not chunk:
                    continue
                buffer += chunk
                if len(buffer) > 8192:
                    buffer = b''
                if not buffer.endswith(b'\n'):
                    continue
                line, buffer = buffer, b''
                try:
                    reply = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(reply, dict) or not isinstance(reply.get('id'), str):
                    continue
                with self.lock:
                    inbox = self.pending.get(reply.get('id'))
                if inbox:
                    inbox.put(reply)
            except (serial.SerialException, OSError):
                self.closed.set()

    def request(self, command, timeout=20):
        identifier = uuid.uuid4().hex
        inbox = queue.Queue()
        with self.lock:
            self.pending[identifier] = inbox
        try:
            if self.closed.is_set():
                raise RuntimeError('串口已断开')
            packet = json.dumps({'id': identifier, 'command': command}) + '\n'
            with self.write_lock:
                self.wire.write(packet.encode('ascii'))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.closed.is_set():
                    raise RuntimeError('串口连接中断；执行结果未知，请检查接收端')
                try:
                    reply = inbox.get(timeout=min(0.2, max(0.001, deadline-time.monotonic())))
                except queue.Empty:
                    continue
                if reply.get('status') == 'accepted':
                    continue
                if reply.get('status') == 'error':
                    raise RuntimeError(reply.get('message', '接收端报错'))
                if reply.get('status') in ('done', 'status'):
                    return reply
            raise TimeoutError('等待接收端结果超时；不要自动重发，先检查机械臂与接收端')
        finally:
            with self.lock:
                self.pending.pop(identifier, None)

    def close(self):
        self.closed.set()
        self.thread.join(timeout=0.5)
        self.wire.close()
