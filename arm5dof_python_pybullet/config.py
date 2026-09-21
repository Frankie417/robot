'''
五自由度机械臂的配置文件
----------------------------------------------
@https://www.dice.com.cn/
'''
import math
import numpy as np

# 预设点
# [x, y, z, pitch, yaw]
# None代表不指定/需要自动生成
ARM_POSE_DICT = {
    # 零点位置
    # Keep the simulator aligned with robot/2.机械臂实验/config.py.
    'home': [150, 0, 200, None, np.pi],
    # 物块释放点
    'object_release': [0, 185, 30, None, np.pi]
    
}

# Pitch平面拟合结果
PITCH_PANEL_A = -0.002490
PITCH_PANEL_B = -0.004985
PITCH_PANEL_C = 3.048636

# Same end-effector Z correction used by robot/2.机械臂实验.
Z_ERROR_POLYFIT = (0.0156, -3.2391)


##########################################
## 轨迹规划
##
##########################################
TRAJECTORY_DELTA_T = 0.01 # 单位s

##########################################
## 插补算法
##
##########################################
RAD_PER_STEP = 0.05
