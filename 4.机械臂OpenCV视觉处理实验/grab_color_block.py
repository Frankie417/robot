'''
抓取工作台上的物块
----------------------------------------------
@https://www.dice.com.cn/
'''
import sys
import math
import time
import cv2
import numpy as np
# 自定义库
sys.path.append("./")
from camera import Camera
from color_block_detector import ColorBlockDetector
from image2workspace import Image2Workspace
from arm5dof_uservo import Arm5DoFUServo
from arm_application import ArmApplication

#####################################
## 物块抓取的配置文件
#####################################
# - 物块像素尺寸最小值
cubic_min_size = 100
# - 物块像素尺寸最大值
cubic_max_size = 300
# - 机械臂抓取位姿偏移量
arm_offset_xy = -10.0 # XY平面上的偏移量
arm_offset_z = 0.0 # Z轴上的偏移量
# - 抓取阈值
# 	在某个位置检测到多少次就进行抓取
cubic_count_threshold = 20
# - 是否只抓取工作区内的物块
# 	True: 只抓取工作区内的物块
#   False: 工作区外的也抓
grab_cubic_in_ws = False
#####################################

# 创建机械臂
arm_config_folder = "config"
arm = Arm5DoFUServo(config_folder=arm_config_folder)
# 运动到图像拍摄点
arm.set_tool_pose(pose_name="capture_image")
# 创建机械臂APP
arm_app = ArmApplication(arm, config_folder=arm_config_folder)
# 要识别的颜色列表
color_name_list = ["red"]
# 创建摄像头
camera = Camera()
# 初始相机
capture = camera.capture
# 载入标定数据
camera.load_cam_calib_data()
# 色块识别器
color_block_detector = ColorBlockDetector()
# 像素到工作台坐标映射器
img2ws = Image2Workspace(camera)
# 机械臂物块抓取
# Key: 位置编码
# Value: (颜色名称, 计数)
candi_workpiece_dict = {} # 候选工件字典
def candi_workpiece_encoding(wx, wy, delta=20):
    '''工件坐标编码, 坐标单位mm'''
    return int(wx/delta) + int(wy/delta)*1000

def justify_workspace_posi(wx, wy, wz):
    '''调整工作空间坐标'''
    theta = math.atan2(wy, wx)
    r = math.sqrt(wx*wx + wy*wy)
    new_r = r + arm_offset_xy
    new_wx = new_r * math.cos(theta)
    new_wy = new_r * math.sin(theta) 
    new_wz = wz + arm_offset_z
    return new_wx, new_wy, new_wz
try:
    while True:
        # 开始时间
        t_start = time.time()
        ret,img_bgr = camera.read()
        if not ret:
            logging.error('图像获取失败')
            break
        # 识别色块
        canvas = np.copy(img_bgr)
        for color_name in color_name_list:
            rect_list, canvas = color_block_detector.color_clock_rect(\
                img_bgr, color_name, canvas=canvas)
            # 遍历所有的ROI框
            for rect in rect_list:
                x, y, w, h = rect
                # 过滤物块
                if w < cubic_min_size or w > cubic_max_size:
                    print(f"像素宽度 = {w}, 不满足尺寸要求")
                    continue
                if h < cubic_min_size or h > cubic_max_size:
                    print(f"像素高度 = {h}, 不满足尺寸要求")
                    continue
                # 计算物体像素中心坐标
                # 计算物体中心坐标
                px = x + w/2
                py = y + h/2
                # 将图像坐标系转换为工作台坐标系
                wx, wy = img2ws.img2workspace(px, py)
                # 判断是否在工作区内
                if grab_cubic_in_ws:
                    if abs(wx) > img2ws.x0 or abs(wy) > img2ws.y0:
                        # 在工作区格子外，不处理
                        print(f"超出工作区范围: wx = {wx} wy = {wy}")
                        continue 
                # 对位置进行编码
                code = candi_workpiece_encoding(wx, wy)
                if code not in candi_workpiece_dict:
                    candi_workpiece_dict[code] = [color_name, 1]
                else:
                    candi_workpiece_dict[code][0] = color_name
                    candi_workpiece_dict[code][1] += 1
                print(f"纳入统计: wx = {wx} wy = {wy} 编码 = {code}")
                if(candi_workpiece_dict[code][1] >= cubic_count_threshold):
                    # 抓取工件
                    print("- 抓取工件")
                    print(f"物块颜色 {color_name} wx={wx:.1f} wy={wy:.1f} mm")
                    wx2, wy2, wz2 = justify_workspace_posi(wx, wy, img2ws.object_height)
                    arm_app.grab_cubic(wx2-25, wy2+10, wz2)
                    # 清空投票字典
                    candi_workpiece_dict = {}
                    break
        # 统计帧率
        t_end = time.time()
        t_pass = t_end - t_start
        fps = int(1/t_pass)

        # 绘制帧率
        cv2.putText(canvas, text=f"FPS:{fps}",\
            org=(20, 20), fontFace=cv2.FONT_HERSHEY_SIMPLEX, \
            fontScale=0.8, thickness=2, lineType=cv2.LINE_AA, color=(0, 0, 255))

        cv2.imshow("canvas", canvas)
        key = cv2.waitKey(1)
        if key == ord('q'):
            break
except KeyboardInterrupt:
    print("按键中断")
finally:
    # 关闭所有的窗口
    cv2.destroyAllWindows()
    # 释放相机
    capture.release()
    # 机械臂卸力
    arm.set_damping(0)