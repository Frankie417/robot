"""Week8: 1/2/3/5 select a color, OK confirms. Five is NOT stop."""
import time
from week8_settings import GESTURE_COLOR_MAP,FIVE_MODEL_THRESHOLD,FIVE_CONFIRM_FRAMES,OTHER_GESTURE_THRESHOLD,OTHER_CONFIRM_FRAMES

ACTIONS={label:'sort_'+color for label,color in GESTURE_COLOR_MAP.items()}


class Controller:
    def __init__(self,timeout=8.0):
        self.timeout=timeout
        self.state='WAIT'
        self.armed=self.busy=self.stopped=False
        self.candidate=None
        self.last=None
        self.count=0
        self.selected_at=0

    def arm(self):
        if self.busy or self.stopped:
            return False
        self.armed=True
        self.state,self.candidate='WAIT',None
        self.last,self.count=None,0
        return True

    def stop(self):
        self.stopped,self.armed=True,False
        self.state,self.candidate='STOPPED',None
        self.last,self.count=None,0

    def clear(self):
        if self.busy:
            return False
        self.stopped,self.armed=False,False
        self.state,self.candidate='WAIT',None
        self.last,self.count=None,0
        return True

    def done(self,failed=False):
        self.busy,self.armed=False,False
        self.candidate=None
        if failed:
            self.stop()
        self.state='STOPPED' if self.stopped else 'WAIT'

    def feed(self,label,score,now=None):
        now=time.monotonic() if now is None else now
        threshold=FIVE_MODEL_THRESHOLD if label=='Five' else OTHER_GESTURE_THRESHOLD
        label=label if score>=threshold else None
        if self.stopped or self.busy or not self.armed:
            return None
        if self.candidate and now-self.selected_at>self.timeout:
            self.state,self.candidate='WAIT',None
            self.last,self.count=None,0
        self.count=self.count+1 if label==self.last else 1
        self.last=label
        frames=FIVE_CONFIRM_FRAMES if label=='Five' else OTHER_CONFIRM_FRAMES
        if label is None or self.count<frames:
            return None
        self.count=0
        if label in ACTIONS:
            self.candidate,self.selected_at,self.state=label,now,'SELECT'
        elif label=='OK' and self.candidate:
            command=ACTIONS[self.candidate]
            self.state,self.busy,self.armed='EXECUTE',True,False
            return command
        return None
