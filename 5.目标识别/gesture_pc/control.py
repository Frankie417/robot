"""Gesture debounce and one-shot command selection, independent of hardware."""
import time

ACTIONS = {'One': 'open_gripper', 'Two': 'close_gripper', 'Three': 'home'}


class Controller:
    def __init__(self, frames=3, threshold=0.70, timeout=8.0):
        self.frames, self.threshold, self.timeout = frames, threshold, timeout
        self.state = 'WAIT'
        self.armed = self.busy = self.stopped = False
        self.candidate = None
        self.last = None
        self.count = self.stop_count = 0
        self.selected_at = 0

    def arm(self):
        if self.busy or self.stopped:
            return False
        self.armed = True
        self.state, self.candidate = 'WAIT', None
        self.last, self.count = None, 0
        return True

    def stop(self):
        self.stopped, self.armed = True, False
        self.state, self.candidate = 'STOPPED', None
        self.last, self.count = None, 0

    def clear(self):
        if self.busy:
            return False
        self.stopped, self.armed = False, False
        self.state, self.candidate = 'WAIT', None
        self.last, self.count, self.stop_count = None, 0, 0
        return True

    def done(self, failed=False):
        self.busy, self.armed = False, False
        self.candidate = None
        if failed:
            self.stop()
        self.state = 'STOPPED' if self.stopped else 'WAIT'

    def feed(self, label, score, now=None):
        now = time.monotonic() if now is None else now
        label = label if score >= self.threshold else None
        self.stop_count = self.stop_count + 1 if label == 'Five' else 0
        if not self.stopped and self.stop_count >= 2:
            self.stop()
            return 'stop'
        if self.stopped or self.busy or not self.armed:
            return None
        if self.candidate and now - self.selected_at > self.timeout:
            self.state, self.candidate = 'WAIT', None
            self.last, self.count = None, 0
        self.count = self.count + 1 if label == self.last else 1
        self.last = label
        if label is None or self.count < self.frames:
            return None
        self.count = 0
        if label in ACTIONS:
            self.candidate, self.selected_at, self.state = label, now, 'SELECT'
        elif label == 'OK' and self.candidate:
            self.state = 'CONFIRM'
            self.state, self.busy, self.armed = 'EXECUTE', True, False
            return ACTIONS[self.candidate]
        return None
