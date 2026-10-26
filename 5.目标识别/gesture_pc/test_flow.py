"""Protocol/state tests; never count these as real gesture/arm trials."""
import json
import queue
import threading
import time
import unittest
from control import Controller
from serial_link import SerialLink
from receiver import Receiver


class Wire:
    def __init__(self):
        self.queue = queue.Queue()
        self.receiver = Receiver(self.reply)

    def write(self, packet):
        self.receiver.handle(json.loads(packet))

    def reply(self, result):
        for value in (json.dumps(result)+'\n').encode():
            self.queue.put(bytes([value]))

    def read(self, _):
        try:
            return self.queue.get(timeout=.05)
        except queue.Empty:
            return b''

    def close(self):
        pass


class Tests(unittest.TestCase):
    def stable(self, c, label, now=1):
        result = None
        for _ in range(3):
            result = c.feed(label, .95, now)
        return result

    def test_one_shot_and_busy(self):
        c = Controller()
        self.assertIsNone(self.stable(c, 'OK'))
        self.assertTrue(c.arm())
        self.assertIsNone(self.stable(c, 'One'))
        self.assertEqual(self.stable(c, 'OK', 2), 'open_gripper')
        self.assertIsNone(self.stable(c, 'OK', 3))
        self.assertFalse(c.arm())
        c.done()
        self.assertIsNone(self.stable(c, 'One', 4))
        self.assertFalse(c.armed)

    def test_stop_during_busy(self):
        c = Controller()
        c.arm()
        self.stable(c, 'Two')
        self.stable(c, 'OK', 2)
        c.feed('Five', .95)
        self.assertEqual(c.feed('Five', .95), 'stop')
        self.assertFalse(c.clear())
        c.done()
        self.assertEqual(c.state, 'STOPPED')
        self.assertTrue(c.clear())
        self.assertFalse(c.armed)

    def test_low_score_interruption_and_expiry(self):
        c = Controller()
        c.arm()
        c.feed('One', .95, 1)
        c.feed('One', .2, 1)
        c.feed('One', .95, 1)
        self.assertIsNone(c.candidate)
        self.stable(c, 'Three', 2)
        self.assertIsNone(self.stable(c, 'OK', 11))
        self.assertFalse(c.busy)

    def test_serial_roundtrip_busy_stop_clear(self):
        wire = Wire()
        link = SerialLink(wire=wire)
        try:
            self.assertEqual(link.request('status')['mode'], 'simulation')
            results = []
            job = threading.Thread(target=lambda: results.append(link.request('open_gripper')))
            job.start()
            deadline = time.monotonic()+2
            while not wire.receiver.busy and time.monotonic()<deadline:
                time.sleep(.01)
            with self.assertRaises(RuntimeError):
                link.request('home')
            self.assertTrue(link.request('stop')['stopped'])
            with self.assertRaises(RuntimeError):
                link.request('clear_stop')
            job.join(3)
            self.assertEqual(results[0]['status'], 'done')
            with self.assertRaises(RuntimeError):
                link.request('home')
            self.assertFalse(link.request('clear_stop')['stopped'])
        finally:
            link.close()

    def test_duplicate_id_not_executed_twice(self):
        calls, replies = [], []
        receiver = Receiver(replies.append, lambda command: calls.append(command))
        packet = {'id':'same', 'command':'home'}
        receiver.handle(packet)
        deadline = time.monotonic()+2
        while receiver.busy and time.monotonic()<deadline:
            time.sleep(.01)
        receiver.handle(packet)
        self.assertEqual(calls, ['home'])
        self.assertEqual(replies[-1]['status'], 'done')


if __name__ == '__main__':
    unittest.main(verbosity=2)
