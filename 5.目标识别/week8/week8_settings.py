"""Week8 parameters extracted from the supplied Week6 code, not its outdated prose."""
SORT_CONFIG = {'sdk_dir': '/home/jetson/Notebook/4.机械臂OpenCV视觉处理实验',
 'arm_port': '/dev/ttyTHS1',
 'camera_device': 0,
 'roi': (240, 210, 440, 390),
 'min_area': 700,
 'move_seconds': 1.5,
 'gripper_seconds': 0.5,
 'p4_pick': (200.2, -12.8, 45.0, 132.7, 179.0),
 'p4_above': (198.2, -12.8, 75.0, 132.7, 179.0),
 'bin_map': {'red': {'bin': '有害垃圾', 'pose': (103.3, -132.5, 175.1, 104.0, -945200.4)},
             'yellow': {'bin': '其他垃圾', 'pose': (219.0, 99.8, 175.6, 100.0, 137329.9)},
             'green': {'bin': '厨余垃圾', 'pose': (122.8, 114.8, 172.8, 104.0, -945200.4)},
             'blue': {'bin': '可回收垃圾', 'pose': (207.8, -141.3, 173.3, 99.5, 137329.9)}},
 'hsv': {'red': [((0, 80, 50), (10, 255, 255)), ((170, 80, 50), (179, 255, 255))],
         'yellow': [((18, 80, 60), (38, 255, 255))],
         'green': [((40, 60, 35), (90, 255, 255))],
         'blue': [((90, 75, 45), (135, 255, 255))]},
 'empty_frames': 8,
 'post_return_settle': 0.6,
 'p4_clear_timeout': 3.0,
 'min_scene_brightness': 10,
 'frame_timeout': 1.0}
GESTURE_COLOR_MAP = {'One':'red','Two':'yellow','Three':'green','Five':'blue'}
FIVE_MODEL_THRESHOLD = 0.50
FIVE_EXTEND_RATIO = 1.55
FIVE_CONFIRM_FRAMES = 2
OTHER_GESTURE_THRESHOLD = 0.70
OTHER_CONFIRM_FRAMES = 3
RECEIVER_PORT = 8766
API_VERSION = 'week8-v1'
