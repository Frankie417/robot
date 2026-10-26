"""Jetson HTTP receiver over the Micro-USB gadget network (Python 3.6+)."""
import argparse
from collections import OrderedDict
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
try:
    from http.server import ThreadingHTTPServer
except ImportError:  # Jetson Ubuntu 18.04 may still use Python 3.6.
    from socketserver import ThreadingMixIn
    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
import secrets
import threading
import time
import uuid
from arm_interrupt import InterruptibleArm, SimulatedArm, Cancelled


class Engine:
    def __init__(self, hardware=None, heartbeat_timeout=1.5):
        self.cancel = threading.Event()
        self.cancel.set()
        self.arm = hardware(self.cancel) if hardware else SimulatedArm(self.cancel)
        self.mode = 'hardware' if hardware else 'simulation'
        self.cv = threading.Condition(threading.RLock())
        self.session = uuid.uuid4().hex
        self.epoch = 0
        self.stopped, self.busy = True, False
        self.phase = 'locked'
        self.last_seen = None
        self.timeout = heartbeat_timeout
        self.job = None
        self.hold_pending = False
        self.results = OrderedDict()
        self.hold_result = None
        self.shutdown = False
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()
        self.watchdog = threading.Thread(target=self.watch, daemon=True)
        self.watchdog.start()

    def status(self):
        with self.cv:
            return dict(session=self.session, epoch=self.epoch, mode=self.mode, busy=self.busy,
                        stopped=self.stopped, stop_phase=self.phase, hold_result=self.hold_result)

    def heartbeat(self):
        with self.cv:
            self.last_seen = time.monotonic()
            return self.status()

    def stop(self, reason='Five/manual stop'):
        with self.cv:
            self.cancel.set()
            if not self.stopped or self.phase == 'locked':
                self.epoch += 1
                self.stopped, self.busy = True, True
                self.phase = 'stopping'
                self.hold_pending = True
                self.hold_result = {'reason': reason}
                self.cv.notify_all()
            return self.status()

    def clear(self, epoch):
        with self.cv:
            if epoch != self.epoch or self.busy or self.phase in ('stopping', 'failed'):
                raise ValueError('Busy, stale epoch or stop failed; inspect the arm before reset')
            if self.last_seen is None or time.monotonic()-self.last_seen > self.timeout:
                raise ValueError('No fresh heartbeat')
            self.stopped, self.phase = False, 'ready'
            self.cancel.clear()
            return self.status()

    def submit(self, identifier, command, epoch):
        with self.cv:
            if identifier in self.results:
                return dict(self.results[identifier])
            if command not in ('open_gripper', 'close_gripper', 'home'):
                raise ValueError('Unknown command')
            if epoch != self.epoch or self.stopped or self.busy:
                raise ValueError('Stopped, busy or obsolete command epoch')
            if self.last_seen is None or time.monotonic()-self.last_seen > self.timeout:
                raise ValueError('Heartbeat expired')
            self.busy = True
            self.results[identifier] = dict(id=identifier, status='running', command=command, mode=self.mode)
            while len(self.results) > 1000:
                self.results.popitem(last=False)
            self.job = (identifier, command)
            self.cv.notify_all()
            return dict(self.results[identifier])

    def worker(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.job is not None or self.hold_pending or self.shutdown)
                if self.shutdown and not self.job and not self.hold_pending:
                    return
                job, self.job = self.job, None
            error = None
            if job:
                try:
                    self.arm.execute(job[1])
                except Cancelled:
                    self.cancel.set()
                except Exception as exc:
                    error = str(exc)
                    self.stop('Motion failure: '+error)
            with self.cv:
                needs_hold = self.cancel.is_set()
            hold_error, report = None, None
            if needs_hold:
                try:
                    report = self.arm.hold()
                except Exception as exc:
                    hold_error = str(exc)
            with self.cv:
                if needs_hold:
                    self.stopped = True
                    self.hold_pending = False
                    self.phase = 'failed' if hold_error else 'held'
                    self.hold_result = {'error': hold_error} if hold_error else report
                self.busy = self.hold_pending
                if job:
                    self.results[job[0]].update(status='error' if error or hold_error else ('interrupted' if needs_hold else 'done'),
                                               error=error or hold_error, stop_phase=self.phase)
                self.cv.notify_all()

    def watch(self):
        while not self.shutdown:
            with self.cv:
                expired = self.last_seen is not None and time.monotonic()-self.last_seen > self.timeout
                if expired and not self.stopped:
                    self.stop('USB network heartbeat lost')
            time.sleep(.1)

    def close(self):
        self.stop('Receiver shutdown')
        with self.cv:
            self.cv.wait_for(lambda: not self.busy, timeout=8)
            if self.busy:
                raise RuntimeError('Stop incomplete; inspect arm and use hardware stop')
            self.shutdown = True
            self.cv.notify_all()
        self.thread.join(1)
        self.arm.close()


def make_server(engine, token, host='0.0.0.0', port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, code, value):
            payload = json.dumps(value).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def auth(self):
            if not secrets.compare_digest(self.headers.get('X-Gesture-Token', ''), token):
                self.answer(401, {'error': 'Invalid token'})
                return False
            return True

        def do_GET(self):
            if not self.auth():
                return
            if self.path == '/status':
                self.answer(200, engine.status())
            elif self.path.startswith('/result/'):
                with engine.cv:
                    result = engine.results.get(self.path[len('/result/'):])
                    self.answer(200 if result else 404, dict(result) if result else {'error':'Unknown command ID'})
            else:
                self.answer(404, {'error':'Unknown path'})

        def do_POST(self):
            if not self.auth():
                return
            try:
                self.connection.settimeout(2)
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 2048:
                    raise ValueError('Invalid request size')
                packet = json.loads(self.rfile.read(length))
                if not isinstance(packet, dict):
                    raise ValueError('Invalid JSON object')
                if packet.get('session') != engine.session:
                    raise ValueError('Receiver session changed; reconnect')
                if self.path == '/heartbeat':
                    result = engine.heartbeat()
                elif self.path == '/stop':
                    result = engine.stop()
                elif self.path == '/clear':
                    result = engine.clear(packet.get('epoch'))
                elif self.path == '/command':
                    identifier = packet.get('id')
                    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 64:
                        raise ValueError('Invalid ID')
                    result = engine.submit(identifier, packet.get('command'), packet.get('epoch'))
                else:
                    raise ValueError('Unknown path')
                self.answer(200, result)
            except (ValueError, TypeError, TimeoutError) as exc:
                self.answer(409, {'error':str(exc)})
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--hardware', action='store_true')
    parser.add_argument('--sdk-dir')
    parser.add_argument('--arm-port', default='/dev/ttyTHS1')
    args = parser.parse_args()
    if args.hardware and not args.sdk_dir:
        parser.error('--hardware requires --sdk-dir')
    factory = (lambda event: InterruptibleArm(args.sdk_dir, args.arm_port, event)) if args.hardware else None
    engine = Engine(factory)
    token = secrets.token_urlsafe(24)
    server = make_server(engine, token, args.host, args.port)
    print('URL: http://192.168.55.1:'+str(args.port), flush=True)
    print('TOKEN: '+token, flush=True)
    print('MODE: '+engine.mode+'; initially STOPPED. Clear stop before arming.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
        server.server_close()


if __name__ == '__main__':
    main()
