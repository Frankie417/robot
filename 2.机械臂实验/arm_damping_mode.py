'''
阻尼模式下读取
1. 舵机角度
2. 关节角度
3. 末端位姿
----------------------------------------------
@https://www.dice.com.cn/
'''
import time
import math
from arm5dof_uservo import Arm5DoFUServo
from config import *

# 创建机械臂
arm = Arm5DoFUServo(is_init_pose=False)
# 设置为阻尼模式
# 数值越大，阻尼越大
arm.set_damping(1000)

# 不断查询舵机角度
# 不停的打印当前原始舵机角度
while True:
    # 获取原始角度列表
	angle_list = arm.get_servo_angle_list()
	# 打印原始舵机角度
	a1, a2, a3, a4, a5, a6 = angle_list
	print("舵机原始角度")
	print(f"J1: {a1:.1f} J2: {a2:.1f} J3: {a3:.1f} J4: {a4:.1f} J5: {a5:.1f} J6: {a6:.1f}")
	# 打印机械臂关节角度
	joint_angle_list = arm.get_joint_angle_list()
	a1, a2, a3, a4, a5, a6 = joint_angle_list
	print("机械臂关节角度")
	print(f" J1: {a1:.5f}\n J2: {a2:.5f}\n J3: {a3:.5f}\n" + \
		f" J4: {a4:.5f}\n J5: {a5:.5f}\n J6: {a6:.5f}\n")
	# 打印当前机械臂的位姿
	x, y, z, pitch, roll = arm.get_tool_pose()
	print("机械臂末端位姿")
	print(f"- 位置： X={x} Y={y} Z={z}")
	print(f"- 姿态: 俯仰角 {pitch:.5f} 横滚角 {roll:.5f}")
	time.sleep(1)