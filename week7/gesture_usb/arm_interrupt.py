"""Cooperative trajectory cancellation plus feedback-based position hold.

Only the motion worker touches the SDK/UART. The HTTP stop handler sets an Event.
This is a software protective stop, not a certified hardware emergency stop.
"""
import math
from pathlib import Path
import sys
import threading
import time


class Cancelled(Exception):
    pass


class InterruptibleArm:
    def __init__(self, sdk_dir, port, stop_event):
        sys.path.insert(0, str(Path(sdk_dir).resolve()))
        from arm5dof_uservo import Arm5DoFUServo
        from uservo import Packet
        self.stop_event = stop_event
        self.arm = Arm5DoFUServo(device=port, is_init_pose=False,
                                config_folder=str(Path(sdk_dir).resolve()/'config'))
        self.manager = self.arm.uservo
        self.ids = sorted(self.manager.servos)
        if self.ids != list(range(6)):
            raise RuntimeError('Expected six online servos with IDs 0..5; found '+str(self.ids))
        self.allow_hold = False
        self.feedback = {identifier: 0 for identifier in self.ids}
        # The SDK otherwise swallows SerialException and may return stale feedback.
        for code in (self.manager.CODE_QUERY_SERVO_ANGLE, self.manager.CODE_QUERY_SERVO_ANGLE_MTURN):
            original = self.manager.response_handle_funcs[code]
            def response(data, original=original):
                original(data)
                self.feedback[data[0]] = self.feedback.get(data[0], 0)+1
            self.manager.response_handle_funcs[code] = response
        motion_codes = {getattr(self.manager, name) for name in dir(self.manager)
                        if name.startswith('CODE_SET_SERVO_ANGLE')}
        def send(code, data):
            if code in motion_codes and not self.allow_hold:
                self.check()
            packet = Packet.pack(code, data)
            if self.arm.uart.write(packet) != len(packet):
                raise IOError('Incomplete servo UART write')
        self.manager.send_request = send
        self.arm.uart.write_timeout = 0.2
        self.original_query = self.manager.query_servo_angle
        self.manager.query_servo_angle = self.query
        self.arm.trajectory_callback_period = 1

    def check(self):
        if self.stop_event.is_set():
            raise Cancelled('Motion cancelled')

    def query(self, identifier):
        previous = self.feedback[identifier]
        angle = self.original_query(identifier)
        if self.feedback[identifier] == previous or angle is None or not math.isfinite(float(angle)):
            raise IOError('Missing fresh angle feedback from servo '+str(identifier))
        return float(angle)

    def execute(self, command):
        self.check()
        if command == 'open_gripper':
            self.arm.gripper_open(callback=self.check)
        elif command == 'close_gripper':
            self.arm.gripper_close(callback=self.check)
        elif command == 'home':
            result = self.arm.set_tool_pose(pose_name='home', T=2.0,
                                            is_soft_move=True, callback=self.check)
            if result is False:
                raise RuntimeError('Home inverse kinematics failed')
        else:
            raise ValueError('Unknown action')
        # Do not report success merely because trajectory generation returned.
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            self.check()
            if self.manager.is_stop():
                return
            self.stop_event.wait(.02)
        raise TimeoutError('Servo did not reach target')

    def hold(self):
        """Override the unfinished target with each servo's freshly measured angle."""
        self.allow_hold = True
        try:
            errors = []
            targets = {}
            for identifier in self.ids:
                try:
                    angle = self.query(identifier)
                    targets[identifier] = angle
                    if self.manager.set_servo_angle(identifier, angle, interval=0, power=0) is False:
                        raise IOError('Servo rejected hold')
                except Exception as error:
                    errors.append(str(error))
            if errors:
                raise RuntimeError('; '.join(errors))
            # Fresh feedback is required; no stale SDK cache may prove a stop.
            deadline = time.monotonic()+1.5
            stable = 0
            previous = {identifier: self.query(identifier) for identifier in self.ids}
            while time.monotonic() < deadline:
                time.sleep(.05)
                current = {identifier: self.query(identifier) for identifier in self.ids}
                near_target = all(abs(current[i]-targets[i]) <= 1.0 for i in self.ids)
                stable = stable+1 if near_target and all(abs(current[i]-previous[i]) <= .5 for i in self.ids) else 0
                if stable >= 2:
                    return {'hold_sent': True, 'feedback_stable': True}
                previous = current
            raise RuntimeError('Hold sent but stationary feedback not confirmed')
        finally:
            self.allow_hold = False

    def close(self):
        self.arm.uart.close()


class SimulatedArm:
    def __init__(self, stop_event, duration=2):
        self.stop_event, self.duration = stop_event, duration
        self.holds = 0

    def execute(self, command):
        if self.stop_event.wait(self.duration):
            raise Cancelled('Simulation interrupted')

    def hold(self):
        self.holds += 1
        return {'hold_sent': False, 'feedback_stable': False, 'simulation_interrupted': True}

    def close(self):
        pass
