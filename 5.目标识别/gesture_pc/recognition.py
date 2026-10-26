# Extracted from the original notebook; the source notebook is unchanged.
import time
from pathlib import Path
import cv2
import numpy as np
import mediapipe as mp
import math

目录 = Path(__file__).resolve().parent.parent
模型路径 = 目录 / 'models' / 'gesture_recognizer.task'
相机号 = 0
最低置信度 = 0.70
手势中文 = {'One': '食指竖起', 'Two': '食指和中指竖起', 'Three': '食指、中指和无名指竖起', 'OK': '拇指与食指成环', 'Five': '五指张开'}
有效手势 = tuple(手势中文)
伸直阈值 = 1.85
弯曲阈值 = 1.55
OK距离阈值 = 0.42

def 创建识别器(模式):
    """用已下载的官方模型创建 MediaPipe 识别器。"""
    if not 模型路径.is_file():
        raise FileNotFoundError('缺少手势模型：' + str(模型路径))
    选项 = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_buffer=模型路径.read_bytes()),
        running_mode=模式,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp.tasks.vision.GestureRecognizer.create_from_options(选项)

def 识别画面(图像, 识别器, 时间戳=None):
    """用官方类别识别一指、二指和五指张开，用关键点判断三指与 OK。"""
    彩色 = cv2.cvtColor(图像, cv2.COLOR_BGR2RGB)
    输入图 = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(彩色))
    if 时间戳 is None:
        原始结果 = 识别器.recognize(输入图)
    else:
        原始结果 = 识别器.recognize_for_video(输入图, 时间戳)
    官方类别, 官方分数 = '无手', 0.0
    if 原始结果.gestures and 原始结果.gestures[0]:
        首位 = 原始结果.gestures[0][0]
        官方类别, 官方分数 = 首位.category_name, float(首位.score)
    类别, 分数, 分数来源 = '未定义手势', 0.0, '无'
    if not 原始结果.hand_landmarks:
        类别 = '无手'
    else:
        点 = 原始结果.hand_landmarks[0]
        宽高比 = 图像.shape[1] / 图像.shape[0]
        def 距离(甲, 乙):
            return math.hypot((点[甲].x - 点[乙].x) * 宽高比, 点[甲].y - 点[乙].y)
        比值 = [距离(尖端, 根部) / max(距离(近端, 根部), 1e-6) for 根部, 近端, 尖端 in ((5,6,8),(9,10,12),(13,14,16),(17,18,20))]
        环距 = 距离(4, 8) / max(距离(5, 17), 1e-6)
        if 环距 <= OK距离阈值 and all(比值[i] >= 伸直阈值 for i in (1,2,3)):
            余量 = min(OK距离阈值-环距, *(比值[i]-伸直阈值 for i in (1,2,3)))
            类别, 分数, 分数来源 = 'OK', min(0.99, 0.70 + max(0.0, 余量)), '关键点几何余量'
        elif all(比值[i] >= 伸直阈值 for i in (0,1,2)) and 比值[3] <= 弯曲阈值:
            余量 = min(*(比值[i]-伸直阈值 for i in (0,1,2)), 弯曲阈值-比值[3])
            类别, 分数, 分数来源 = 'Three', min(0.99, 0.70 + max(0.0, 余量)), '关键点几何余量'
        elif 官方类别 in ('Pointing_Up', 'Victory', 'Open_Palm') and (官方类别 != 'Open_Palm' or 环距 > OK距离阈值):
            类别 = {'Pointing_Up':'One', 'Victory':'Two', 'Open_Palm':'Five'}[官方类别]
            分数, 分数来源 = 官方分数, '模型分类分数'
    通过 = 类别 in 有效手势 and 分数 >= 最低置信度 and len(原始结果.hand_landmarks) == 1
    return {'类别': 类别, '置信度': 分数, '通过': 通过, '分数来源': 分数来源, '官方类别': 官方类别, '官方分数': 官方分数, '关键点': 原始结果.hand_landmarks}

def 标注画面(图像, 结果):
    """在真实画面上绘制模型手部关键点和类别。"""
    标注 = 图像.copy()
    高, 宽 = 标注.shape[:2]
    手部连线 = ((0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
              (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
              (13,17),(0,17),(17,18),(18,19),(19,20))
    for 手 in 结果['关键点']:
        for 点序号甲, 点序号乙 in 手部连线:
            甲, 乙 = 手[点序号甲], 手[点序号乙]
            cv2.line(标注, (int(甲.x*宽), int(甲.y*高)), (int(乙.x*宽), int(乙.y*高)), (0, 255, 0), 2)
        for 点 in 手:
            cv2.circle(标注, (int(点.x*宽), int(点.y*高)), 3, (0, 0, 255), -1)
    英文类别 = {'无手': 'No_Hand', '未定义手势': 'Unknown'}.get(结果['类别'], 结果['类别'])
    文字 = '{} {:.2f}'.format(英文类别, 结果['置信度'])
    if len(结果['关键点']) > 1:
        文字 = 'Multiple_Hands - blocked'
    cv2.putText(标注, 文字, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if 结果['通过'] else (0, 255, 255), 2)
    return 标注

print('模型文件已找到：{}；可识别手势：{}'.format(模型路径.name, '、'.join(手势中文[x] for x in 有效手势)))
