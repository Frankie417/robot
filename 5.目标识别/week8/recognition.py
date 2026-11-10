"""Week7 model plus a more tolerant palm classifier, preserving strict OK."""
import math
from pathlib import Path
import cv2
import numpy as np
import mediapipe as mp
from week8_settings import FIVE_MODEL_THRESHOLD,FIVE_EXTEND_RATIO,OTHER_GESTURE_THRESHOLD

模型路径=Path(__file__).resolve().parent/'models/gesture_recognizer.task'
相机号=0
手势中文={'One':'食指','Two':'食指和中指','Three':'食指中指无名指','Five':'张开手掌','OK':'拇指食指成环'}
有效手势=tuple(手势中文)
手部连线=((0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),(11,12),
          (9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20))


def classify_geometry(ratios,ring_distance,official,official_score):
    """Pure geometry decision: OK/Three before relaxed Five to avoid ambiguity."""
    if ring_distance<=.42 and all(ratios[i]>=1.85 for i in (1,2,3)):
        margin=min(.42-ring_distance,*[ratios[i]-1.85 for i in (1,2,3)])
        return 'OK',min(.99,.70+max(0,margin)),'关键点几何余量'
    if all(ratios[i]>=1.85 for i in (0,1,2)) and ratios[3]<=1.55:
        margin=min(*[ratios[i]-1.85 for i in (0,1,2)],1.55-ratios[3])
        return 'Three',min(.99,.70+max(0,margin)),'关键点几何余量'
    if official in ('Pointing_Up','Victory') and official_score>=OTHER_GESTURE_THRESHOLD:
        return {'Pointing_Up':'One','Victory':'Two'}[official],official_score,'模型分类分数'
    # Thumb does not need to be fully straight; all four other fingers do.
    # Keep index/thumb apart so an OK ring cannot become Five.
    if ring_distance>.50 and all(r>=FIVE_EXTEND_RATIO for r in ratios):
        score=min(.90,.55+max(0,min(ratios)-FIVE_EXTEND_RATIO)*.25)
        return 'Five',score,'宽松手掌几何余量'
    if official=='Open_Palm' and official_score>=FIVE_MODEL_THRESHOLD and ring_distance>.42:
        return 'Five',official_score,'模型分类分数'
    return '未定义手势',0.0,'无'


def 创建识别器(模式):
    if not 模型路径.is_file():
        raise FileNotFoundError('缺少模型：'+str(模型路径))
    options=mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_buffer=模型路径.read_bytes()),running_mode=模式,num_hands=2,
        min_hand_detection_confidence=.45,min_hand_presence_confidence=.45,min_tracking_confidence=.45)
    return mp.tasks.vision.GestureRecognizer.create_from_options(options)


def 识别画面(图像,识别器,时间戳=None):
    rgb=cv2.cvtColor(图像,cv2.COLOR_BGR2RGB)
    inp=mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(rgb))
    result=识别器.recognize(inp) if 时间戳 is None else 识别器.recognize_for_video(inp,时间戳)
    official,score='None',0.0
    if result.gestures and result.gestures[0]:
        official,score=result.gestures[0][0].category_name,float(result.gestures[0][0].score)
    label,value,source='无手',0.0,'无'
    if result.hand_landmarks:
        points=result.hand_landmarks[0]
        aspect=图像.shape[1]/图像.shape[0]
        def distance(a,b):
            return math.hypot((points[a].x-points[b].x)*aspect,points[a].y-points[b].y)
        ratios=[distance(tip,base)/max(distance(pip,base),1e-6) for base,pip,tip in ((5,6,8),(9,10,12),(13,14,16),(17,18,20))]
        ring=distance(4,8)/max(distance(5,17),1e-6)
        label,value,source=classify_geometry(ratios,ring,official,score)
    threshold=FIVE_MODEL_THRESHOLD if label=='Five' else OTHER_GESTURE_THRESHOLD
    accepted=label in 有效手势 and value>=threshold and len(result.hand_landmarks)==1
    return {'类别':label,'置信度':value,'通过':accepted,'分数来源':source,'官方类别':official,'官方分数':score,'关键点':result.hand_landmarks}


def 标注画面(图像,结果):
    canvas=图像.copy();height,width=canvas.shape[:2]
    for hand in 结果['关键点']:
        for a,b in 手部连线:
            cv2.line(canvas,(int(hand[a].x*width),int(hand[a].y*height)),(int(hand[b].x*width),int(hand[b].y*height)),(0,255,0),2)
    label={'无手':'No_Hand','未定义手势':'Unknown'}.get(结果['类别'],结果['类别'])
    if len(结果['关键点'])>1:
        label='Multiple_Hands - blocked'
    cv2.putText(canvas,'{} {:.2f}'.format(label,结果['置信度']),(12,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,255,0) if 结果['通过'] else (0,255,255),2)
    return canvas
