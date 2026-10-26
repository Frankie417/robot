"""Run on the lab computer/Jetson, not on the recognition computer."""
import argparse
from collections import OrderedDict
import json
from pathlib import Path
import sys
import threading
import time
import serial


class Receiver:
    def __init__(self, send, action=None):
        self.send, self.action = send, action
        self.busy, self.stopped = False, False
        self.lock = threading.RLock()
        self.cache = OrderedDict()

    def reply(self, identifier, status, **fields):
        result = dict(id=identifier, status=status, busy=self.busy,
                      stopped=self.stopped, mode='hardware' if self.action else 'simulation', **fields)
        self.cache[identifier] = result
        while len(self.cache) > 1000:
            self.cache.popitem(last=False)
        self.send(result)

    def handle(self, packet):
        identifier, command = packet.get('id'), packet.get('command')
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 64:
            return
        with self.lock:
            if identifier in self.cache:
                self.send(self.cache[identifier])
                return
            if command == 'status':
                self.reply(identifier, 'status')
            elif command == 'stop':
                self.stopped = True
                self.reply(identifier, 'done', message='新动作已锁定；正在执行的动作不能由此中断')
            elif command == 'clear_stop' and not self.busy:
                self.stopped = False
                self.reply(identifier, 'done')
            elif command not in ('open_gripper', 'close_gripper', 'home', 'clear_stop'):
                self.reply(identifier, 'error', message='未知指令')
            elif self.busy or self.stopped:
                self.reply(identifier, 'error', message='接收端忙碌或已停止锁定')
            else:
                self.busy = True
                self.reply(identifier, 'accepted', command=command)
                threading.Thread(target=self.execute, args=(identifier, command), daemon=True).start()

    def execute(self, identifier, command):
        try:
            if self.action:
                self.action(command)
            else:
                time.sleep(1)
            with self.lock:
                self.busy = False
                self.reply(identifier, 'done', command=command)
        except Exception as error:
            with self.lock:
                self.busy, self.stopped = False, True
                self.reply(identifier, 'error', message=str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='连接识别电脑的串口，不是舵机串口')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--hardware', action='store_true')
    parser.add_argument('--sdk-dir', type=Path)
    parser.add_argument('--arm-port', help='接收端连接机械臂的另一串口，例如 /dev/ttyTHS1')
    args = parser.parse_args()
    action = None
    if args.hardware:
        if not args.sdk_dir or not args.arm_port:
            parser.error('--hardware 需要 --sdk-dir 和 --arm-port')
        if args.port == args.arm_port:
            parser.error('桥接串口与机械臂串口不能相同')
        sdk = args.sdk_dir.resolve()
        sys.path.insert(0, str(sdk))
        from arm5dof_uservo import Arm5DoFUServo
        arm = Arm5DoFUServo(device=args.arm_port, is_init_pose=False, config_folder=str(sdk/'config'))
        action = lambda command: {'open_gripper': arm.gripper_open, 'close_gripper': arm.gripper_close, 'home': arm.home}[command]()
    with serial.Serial(args.port, args.baud, timeout=0.2, write_timeout=1) as wire:
        write_lock = threading.Lock()
        def send(result):
            line = json.dumps(result, ensure_ascii=True)
            with write_lock:
                wire.write((line+'\n').encode('ascii'))
            print(line, flush=True)
        receiver = Receiver(send, action)
        print('Receiver ready; mode =', 'hardware' if action else 'simulation', flush=True)
        buffer = b''
        try:
            while True:
                chunk = wire.read(1)
                if not chunk:
                    continue
                buffer += chunk
                if len(buffer) > 4096:
                    buffer = b''
                if buffer.endswith(b'\n'):
                    line, buffer = buffer, b''
                    try:
                        packet = json.loads(line)
                        if isinstance(packet, dict):
                            receiver.handle(packet)
                    except (ValueError, UnicodeDecodeError):
                        print('Ignored invalid JSON line', flush=True)
        except KeyboardInterrupt:
            receiver.stopped = True
            while receiver.busy:
                time.sleep(0.1)


if __name__ == '__main__':
    main()
