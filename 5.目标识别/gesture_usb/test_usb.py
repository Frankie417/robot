"""Loopback HTTP and cancellation tests, with no real arm movement."""
import threading
import time
import unittest
from unittest.mock import patch
import types
from control import Controller
from arm_interrupt import SimulatedArm, InterruptibleArm
from receiver_usb import Engine, make_server
from network_link import NetworkLink


def wait_until(predicate, seconds=3):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Condition did not complete')


class Tests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(heartbeat_timeout=.7)
        self.server = make_server(self.engine, 'test-token', '127.0.0.1', 0)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.url = 'http://127.0.0.1:'+str(self.server.server_address[1])
        self.link = NetworkLink(self.url, 'test-token')
        self.link.request('clear_stop')

    def tearDown(self):
        self.link.close()
        self.server.shutdown()
        self.server.server_close()
        self.engine.close()

    def test_stop_preempts_action_without_waiting_for_completion(self):
        replies = []
        action = threading.Thread(target=lambda: replies.append(self.link.request('home')))
        started = time.monotonic()
        action.start()
        wait_until(lambda: self.engine.busy)
        self.link.request('stop')
        action.join(1)
        self.assertFalse(action.is_alive())
        self.assertEqual(replies[0]['status'], 'interrupted')
        self.assertLess(time.monotonic()-started, 1)
        self.assertEqual(self.engine.phase, 'held')
        self.assertTrue(self.engine.stopped)
        self.assertGreater(self.engine.arm.holds, 0)
        self.link.request('clear_stop')
        time.sleep(.35)
        self.assertFalse(self.link.stop_latched.is_set())

    def test_old_epoch_rejected_after_stop_and_clear(self):
        old_epoch = self.engine.epoch
        self.link.request('stop')
        wait_until(lambda: not self.engine.busy)
        self.link.request('clear_stop')
        with self.assertRaises(ValueError):
            self.engine.submit('late-command', 'home', old_epoch)

    def test_duplicate_command_id(self):
        epoch = self.engine.epoch
        first = self.engine.submit('same', 'home', epoch)
        self.assertEqual(first, self.engine.submit('same', 'home', epoch))
        self.link.request('stop')
        wait_until(lambda: not self.engine.busy)
        self.assertEqual(self.engine.submit('same', 'home', epoch)['status'], 'interrupted')

    def test_lost_heartbeat_cancels_running_action(self):
        # Stop only the client's heartbeat, as if its process/USB link disappeared.
        self.link.closed.set()
        self.link.thread.join(1)
        self.engine.heartbeat()
        self.engine.submit('disconnect-test', 'home', self.engine.epoch)
        wait_until(lambda: self.engine.phase == 'held')
        self.assertEqual(self.engine.results['disconnect-test']['status'], 'interrupted')

    def test_hold_failure_cannot_be_cleared(self):
        def bad_hold():
            raise IOError('No servo feedback')
        self.engine.arm.hold = bad_hold
        self.link.request('stop')
        wait_until(lambda: self.engine.phase == 'failed')
        with self.assertRaises(RuntimeError):
            self.link.request('clear_stop')

    def test_wrong_token(self):
        with self.assertRaises(RuntimeError):
            NetworkLink(self.url, 'wrong-token')

    def test_normal_completion(self):
        self.engine.arm.duration = .15
        result = self.link.request('open_gripper')
        self.assertEqual(result['status'], 'done')
        self.assertFalse(self.engine.busy)

    def test_five_during_busy_reaches_network_stop(self):
        control = Controller()
        control.arm()
        for _ in range(3):
            control.feed('One', .95)
        for _ in range(3):
            command = control.feed('OK', .95)
        replies = []
        action = threading.Thread(target=lambda: replies.append(self.link.request(command)))
        action.start()
        wait_until(lambda: self.engine.busy)
        self.assertTrue(control.busy)
        self.assertIsNone(control.feed('Five', .95))
        self.assertEqual(control.feed('Five', .95), 'stop')
        self.link.request('stop')
        action.join(2)
        self.assertEqual(replies[0]['status'], 'interrupted')


class HoldTests(unittest.TestCase):
    def test_sdk_motion_writes_cancel_but_hold_can_override(self):
        writes = []
        event = threading.Event()
        class UART:
            def write(self, packet):
                writes.append(packet)
                return len(packet)
        class Manager:
            CODE_QUERY_SERVO_ANGLE = 10
            CODE_QUERY_SERVO_ANGLE_MTURN = 16
            CODE_SET_SERVO_ANGLE = 8
            def __init__(self):
                self.servos = dict.fromkeys(range(6))
                self.response_handle_funcs = {10: lambda data: None, 16: lambda data: None}
            def query_servo_angle(self, identifier):
                self.response_handle_funcs[10](bytes([identifier]))
                return 1.0
        class FakeArm:
            def __init__(self, **kwargs):
                self.uservo, self.uart = Manager(), UART()
        class Packet:
            @staticmethod
            def pack(code, data):
                return bytes([code])+data
        with patch.dict('sys.modules', {'arm5dof_uservo':types.SimpleNamespace(Arm5DoFUServo=FakeArm),
                                       'uservo':types.SimpleNamespace(Packet=Packet)}):
            arm = InterruptibleArm('.', 'unused', event)
            arm.manager.send_request(8, b'first')
            event.set()
            from arm_interrupt import Cancelled
            with self.assertRaises(Cancelled):
                arm.manager.send_request(8, b'late')
            self.assertEqual(len(writes), 1)
            arm.allow_hold = True
            arm.manager.send_request(8, b'hold')
            self.assertEqual(len(writes), 2)
            self.assertEqual(arm.query(0), 1.0)
            arm.manager.response_handle_funcs[10] = lambda data: None
            with self.assertRaises(IOError):
                arm.query(0)

    def test_hold_uses_measured_positions_and_requires_stability(self):
        arm = InterruptibleArm.__new__(InterruptibleArm)
        arm.ids = [0,1]
        arm.allow_hold = False
        arm.query = lambda identifier: [12.3, -20.1][identifier]
        class Manager:
            def __init__(self):
                self.commands = []
            def set_servo_angle(self, identifier, angle, **kwargs):
                self.commands.append((identifier, angle, kwargs))
                return True
        arm.manager = Manager()
        result = arm.hold()
        self.assertTrue(result['feedback_stable'])
        self.assertEqual([x[1] for x in arm.manager.commands], [12.3, -20.1])
        self.assertTrue(all(x[2]['interval'] == 0 for x in arm.manager.commands))
        self.assertFalse(arm.allow_hold)


if __name__ == '__main__':
    unittest.main(verbosity=2)
