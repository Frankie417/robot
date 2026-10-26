"""Real environment/model/camera probe. Does not make gesture accuracy claims."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import cv2
import mediapipe as mp
import numpy as np
from serial.tools import list_ports
from recognition import 创建识别器, 识别画面, 模型路径


def main():
    report = dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
                  opencv=cv2.__version__, mediapipe=mp.__version__, numpy=np.__version__,
                  model_bytes=模型路径.stat().st_size, model_sha256=hashlib.sha256(模型路径.read_bytes()).hexdigest(),
                  ports=[dict(port=p.device, description=p.description) for p in list_ports.comports()])
    with 创建识别器(mp.tasks.vision.RunningMode.IMAGE) as model:
        blank = 识别画面(np.zeros((480,640,3), dtype=np.uint8), model)
        report['blank_image_label'] = blank['类别']
        assert blank['类别'] == '无手' and not blank['通过']
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            raise RuntimeError('camera 0 cannot open')
        with 创建识别器(mp.tasks.vision.RunningMode.VIDEO) as model:
            times = []
            for index in range(10):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('camera read failed')
                started = time.monotonic()
                result = 识别画面(frame, model, int(started*1000)+index)
                times.append((time.monotonic()-started)*1000)
            report['camera'] = dict(opened=True, frames=10, shape=list(frame.shape), mean_inference_ms=round(sum(times)/len(times),1))
    except Exception as error:
        report['camera'] = dict(opened=False, error=str(error))
    finally:
        cap.release()
    path = Path(__file__).resolve().parent/'diagnostic_report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['camera']['opened']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
