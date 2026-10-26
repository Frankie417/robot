"""Ch5：固定 ROI 的 HSV 色块识别与实验报告取证程序。

程序识别红、黄、绿、蓝方块，显示原始标注画面和四种颜色的 Mask，
保存报告截图并写入 CSV 测试记录。程序开头的 HSV 数值只是初始值，
必须依据实际相机、方块和灯光重新标定后才能作为最终结果。
"""

from __future__ import print_function

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


COLOR_ORDER = ("red", "yellow", "green", "blue")
KEY_TO_COLOR = {
    ord("1"): "red",
    ord("2"): "yellow",
    ord("3"): "green",
    ord("4"): "blue",
}

# ================================================================
# 现场调参区：先只改这里，不需要再维护额外配置文件。
# HSV 初值必须用实际相机画面重新标定；OpenCV 的 H 范围为 0 到 179。
# ROI=None 表示处理整幅画面；例如 (170, 90, 300, 300) 表示固定工作区。
# ================================================================
CAMERA_DEVICE = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
ROI = None
MIN_AREA = 700
KERNEL_SIZE = 5

COLOR_CONFIG = {
    # 红色跨越 H=0/179 边界，必须保留两段区间。
    "red": {
        "bgr": (0, 0, 255),
        "intervals": (((0, 90, 70), (10, 255, 255)), ((170, 90, 70), (179, 255, 255))),
    },
    "yellow": {
        "bgr": (0, 255, 255),
        "intervals": (((18, 80, 80), (38, 255, 255)),),
    },
    "green": {
        "bgr": (0, 255, 0),
        "intervals": (((40, 60, 50), (90, 255, 255)),),
    },
    "blue": {
        "bgr": (255, 0, 0),
        "intervals": (((95, 80, 50), (135, 255, 255)),),
    },
}

DEFAULT_CONFIG = {
    "camera": {
        "device": CAMERA_DEVICE,
        "width": CAMERA_WIDTH,
        "height": CAMERA_HEIGHT,
        "fps": CAMERA_FPS,
        "roi": ROI,
    },
    "detection": {
        "min_area": MIN_AREA,
        "kernel_size": KERNEL_SIZE,
    },
    "colors": COLOR_CONFIG,
}


def parse_roi(value):
    """解析 --roi x,y,width,height；未指定时处理整幅画面。"""
    if value is None:
        return None
    try:
        roi = tuple(int(piece.strip()) for piece in value.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("ROI 格式应为：x,y,width,height")
    if len(roi) != 4 or roi[2] <= 0 or roi[3] <= 0:
        raise argparse.ArgumentTypeError("ROI 宽高必须为正数")
    return roi


def crop_roi(frame, roi):
    """返回设置的 ROI 图像及其相对于原图的坐标偏移。"""
    if roi is None:
        return frame, 0, 0
    x, y, width, height = roi
    frame_h, frame_w = frame.shape[:2]
    if x < 0 or y < 0 or x + width > frame_w or y + height > frame_h:
        raise ValueError("ROI {} 超出 {}x{} 摄像头画面".format(roi, frame_w, frame_h))
    return frame[y:y + height, x:x + width], x, y


class HsvColorRecognizer(object):
    """完成 HSV 掩膜、形态学去噪、轮廓筛选和色块标注。"""

    def __init__(self, config):
        self.config = config
        self.min_area = float(config["detection"]["min_area"])
        self.kernel = np.ones(
            (int(config["detection"]["kernel_size"]), int(config["detection"]["kernel_size"])),
            np.uint8,
        )

    def make_mask(self, hsv, intervals):
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in intervals:
            lower_array = np.asarray(lower, dtype=np.uint8)
            upper_array = np.asarray(upper, dtype=np.uint8)
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower_array, upper_array))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
        return mask

    def detect(self, frame, roi=None):
        """返回标注图、各颜色 Mask 与检测结果；检测坐标均相对完整原图。"""
        cropped, offset_x, offset_y = crop_roi(frame, roi)
        hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)
        annotated = frame.copy()
        masks = {}
        detections = []

        for color_name in COLOR_ORDER:
            spec = self.config["colors"][color_name]
            mask = self.make_mask(hsv, spec["intervals"])
            masks[color_name] = mask
            contours_info = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = contours_info[-2]
            for contour in contours:
                area = float(cv2.contourArea(contour))
                if area < self.min_area:
                    continue
                x, y, width, height = cv2.boundingRect(contour)
                center_x = x + width // 2 + offset_x
                center_y = y + height // 2 + offset_y
                bgr = tuple(int(value) for value in spec["bgr"])
                cv2.rectangle(
                    annotated,
                    (x + offset_x, y + offset_y),
                    (x + width + offset_x, y + height + offset_y),
                    bgr,
                    2,
                )
                cv2.circle(annotated, (center_x, center_y), 4, bgr, -1)
                cv2.putText(
                    annotated,
                    "{} {:.0f}".format(color_name, area),
                    (x + offset_x, max(18, y + offset_y - 7)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    bgr,
                    2,
                    cv2.LINE_AA,
                )
                detections.append({
                    "color": color_name,
                    "center": (center_x, center_y),
                    "area": area,
                    "bbox": (x + offset_x, y + offset_y, width, height),
                })

        if roi is not None:
            x, y, width, height = roi
            cv2.rectangle(annotated, (x, y), (x + width, y + height), (255, 255, 255), 1)
            cv2.putText(annotated, "ROI", (x + 4, y + 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (255, 255, 255), 1, cv2.LINE_AA)
        return annotated, masks, detections


def make_mask_grid(masks):
    """生成带颜色名称的 2x2 Mask 拼图，便于直接用于实验报告截图。"""
    tiles = []
    for name in COLOR_ORDER:
        gray = masks[name]
        tile = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        bgr = tuple(int(value) for value in (0, 0, 0))
        cv2.putText(tile, name, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 255), 2, cv2.LINE_AA)
        tiles.append(tile)
    top = np.hstack((tiles[0], tiles[1]))
    bottom = np.hstack((tiles[2], tiles[3]))
    return np.vstack((top, bottom))


def ensure_csv(csv_path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        with open(str(csv_path), "w", newline="", encoding="utf-8-sig") as stream:
            csv.writer(stream).writerow([
                "timestamp", "expected_color", "detected_colors", "object_count",
                "result", "note",
            ])


def record_trial(csv_path, expected_color, detections):
    detected_colors = sorted(set(item["color"] for item in detections))
    success = expected_color is not None and expected_color in detected_colors
    with open(str(csv_path), "a", newline="", encoding="utf-8-sig") as stream:
        csv.writer(stream).writerow([
            datetime.now().isoformat(timespec="seconds"),
            expected_color or "not_set",
            ";".join(detected_colors) or "none",
            len(detections),
            "correct" if success else "incorrect",
            "",
        ])
    return success, detected_colors


def save_evidence(output_dir, raw, annotated, mask_grid):
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = {
        "raw": output_dir / (stamp + "_raw.png"),
        "result": output_dir / (stamp + "_result.png"),
        "masks": output_dir / (stamp + "_masks.png"),
    }
    cv2.imwrite(str(paths["raw"]), raw)
    cv2.imwrite(str(paths["result"]), annotated)
    cv2.imwrite(str(paths["masks"]), mask_grid)
    return paths


def parse_args(argv=None):
    """解析运行参数；在 Notebook 单元格中使用现场调参区的默认值。"""
    script_path = globals().get("__file__")
    if script_path:
        here = Path(script_path).resolve().parent
    else:
        here = Path.cwd()
        project_dir = here / "5.目标识别"
        if (project_dir / "week5_color_recognition.py").is_file():
            here = project_dir
        if argv is None:
            argv = []
    parser = argparse.ArgumentParser(description="Ch5 HSV 四色方块识别")
    parser.add_argument("--camera", type=int, help="摄像头设备号，优先于程序开头调参区")
    parser.add_argument("--roi", type=parse_roi, help="固定 ROI：x,y,width,height，优先于程序开头调参区")
    parser.add_argument("--output-dir", type=Path, default=here / "evidence")
    parser.add_argument("--record-csv", type=Path, default=here / "week5_test_records.csv")
    parser.add_argument("--expected", choices=COLOR_ORDER,
                        help="测试物块真实颜色；运行中可按 1-4 修改")
    return parser.parse_args(argv)


def open_camera(config, requested_device):
    camera_config = config["camera"]
    device = requested_device if requested_device is not None else int(camera_config["device"])
    if sys.platform.startswith("win"):
        capture = cv2.VideoCapture(device, cv2.CAP_DSHOW)
    else:
        capture = cv2.VideoCapture(device)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera_config["width"]))
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera_config["height"]))
    capture.set(cv2.CAP_PROP_FPS, int(camera_config["fps"]))
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    if not capture.isOpened():
        raise RuntimeError("无法打开摄像头 {}，请检查设备号和连接。".format(device))
    return capture


def read_camera_frame(capture, device):
    """读取一帧；设备已打开却无画面时给出摄像头排查提示。"""
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError(
            "摄像头 /dev/video{} 已打开，但未收到画面。请检查 USB 连接和供电，"
            "拔插摄像头后用 v4l2-ctl -d /dev/video{} --stream-mmap=3 --stream-count=3 测试；"
            "如果系统级取帧也超时，问题不在 HSV 识别代码。".format(device, device)
        )
    return frame


def main():
    args = parse_args()
    config = DEFAULT_CONFIG
    roi = args.roi if args.roi is not None else config["camera"].get("roi")
    if roi is not None:
        roi = tuple(roi)
    recognizer = HsvColorRecognizer(config)
    expected_color = args.expected
    capture = open_camera(config, args.camera)
    device = args.camera if args.camera is not None else int(config["camera"]["device"])

    try:
        frame = read_camera_frame(capture, device)
        ensure_csv(args.record_csv)
        last_time = time.time()
        fps = 0.0
        print("按键：1 红色，2 黄色，3 绿色，4 蓝色；r 记录测试；s 保存截图；q 退出")
        print("HSV 与相机参数请在程序开头的现场调参区修改。")
        while True:
            raw = frame.copy()
            annotated, masks, detections = recognizer.detect(frame, roi)
            mask_grid = make_mask_grid(masks)

            now = time.time()
            instantaneous_fps = 1.0 / max(now - last_time, 1e-6)
            fps = instantaneous_fps if fps == 0.0 else 0.85 * fps + 0.15 * instantaneous_fps
            last_time = now
            state = "expected: {}".format(expected_color or "select 1-4")
            cv2.putText(annotated, "FPS {:.1f} | {} | objects {}".format(fps, state, len(detections)),
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("Ch5 result", annotated)
            cv2.imshow("Ch5 HSV masks red yellow green blue", mask_grid)

            key = cv2.waitKey(1) & 0xFF
            if key in KEY_TO_COLOR:
                expected_color = KEY_TO_COLOR[key]
                print("当前测试物块颜色：{}".format(expected_color))
            elif key == ord("r"):
                success, detected = record_trial(args.record_csv, expected_color, detections)
                print("已记录：真实颜色={}，检测结果={}，{}".format(
                    expected_color, detected, "正确" if success else "错误"))
            elif key == ord("s"):
                paths = save_evidence(args.output_dir, raw, annotated, mask_grid)
                print("已保存：{}".format(", ".join(str(path) for path in paths.values())))
            elif key in (ord("q"), 27):
                break
            frame = read_camera_frame(capture, device)
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
