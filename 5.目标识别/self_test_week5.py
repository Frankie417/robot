"""Ch5 HSV 识别器的离线自检，不需要连接摄像头。"""

import cv2
import numpy as np

from week5_color_recognition import COLOR_ORDER, DEFAULT_CONFIG, HsvColorRecognizer


def main():
    config = DEFAULT_CONFIG
    image = np.zeros((360, 520, 3), dtype=np.uint8)
    boxes = {
        "red": (30, 30, 120, 120),
        "yellow": (290, 30, 120, 120),
        "green": (30, 210, 120, 120),
        "blue": (290, 210, 120, 120),
    }
    for name, (x, y, width, height) in boxes.items():
        cv2.rectangle(image, (x, y), (x + width, y + height),
                      tuple(config["colors"][name]["bgr"]), -1)

    recognizer = HsvColorRecognizer(config)
    _, _, detections = recognizer.detect(image)
    detected = set(item["color"] for item in detections)
    expected = set(COLOR_ORDER)
    assert detected == expected, "期望 {}，实际 {}".format(expected, detected)
    assert len(detections) == 4, "期望识别到四个方块，实际 {} 个".format(len(detections))
    print("通过：红、黄、绿、蓝四个合成方块均被识别")


if __name__ == "__main__":
    main()
