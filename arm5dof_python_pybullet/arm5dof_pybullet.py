'''
四自由度机械臂 | PyBullet仿真机械臂SDK
----------------------------------------------
@https://www.dice.com.cn/
'''
import time
from turtle import st
import numpy as np
from collections import namedtuple
import logging
import pybullet
import pybullet_data
from pathlib import Path
# 自定义库
from arm5dof_kinematic import Arm5DoFKinematic
from minimum_jerk import minimum_jerk_plan, minimum_jerk_seq # 轨迹规划算法
from config import *

# 设置日志等级
logging.basicConfig(level=logging.INFO)


# 创建一个nametuple类型
JointInfo = namedtuple("JointInfo", ["id", "name", "lower_limit",\
						"upper_limit", "max_force", "max_velocity"])
	
class Arm5DoFPyBullet:
	'''五自由度机械臂 | PyBullet仿真机械臂SDK'''
	# 旋转关节名称列表
	joint_name_list = ["joint1", "joint2", "joint3", "joint4", "joint5", \
		"left_gripper_joint", "right_gripper_joint"]
	# 关节PID参数
	position_gain = 0.08 # 位置增益(Kp)
	position_gain_list = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1] # 位置增益(Kp)
	# velocity_gain = 0.3 # 速度增益(Kd)
	# 机械臂静止条件
	angle_tolerance = 0.01      # 弧度容差, 单位: rad
	velocity_tolerance = 0.01   # 转速容差, 单位: rad/s
	wait_timeout = 10.0         # 超时判断阈值，单位: s
	
	# 轨迹执行回调函数执行周期, 几个时间块执行一次
	trajectory_callback_period = 10
	
	def __init__(self, arm_urdf_path=None, connection_mode=None):
		'''Create the simulator.  ``connection_mode`` is ``pybullet.GUI`` by
		default; pass ``pybullet.DIRECT`` for a headless/reproducible run.'''
		self.connection_mode = pybullet.GUI if connection_mode is None else connection_mode
		# 创建仿真环境
		self.create_world()
		# 载入机械臂
		self.load_arm(arm_urdf_path)
		# 运动学求解器
		self.kinematic = Arm5DoFKinematic()
		# 目标关节角度字典
		self.target_joints_angle_dict = {}
		# Home 回归机械零点
		self.home()
	
	def home(self):
		'''回归机械零点'''
		self.set_tool_pose(pose_name="home", is_wait=True)
	
	def create_world(self):
		'''创建仿真环境初始化'''
		# 创建GUI服务器
		pybullet.connect(self.connection_mode)
		# 配置渲染选项
		# 载入棋盘格子
		# 添加额外的文件搜索路径
		pybullet.setAdditionalSearchPath(pybullet_data.getDataPath())
		# 载入棋盘平面(相当于地面)
		plane_id = pybullet.loadURDF("plane.urdf")
		# 设置重力
		pybullet.setGravity(0, 0, -9.8)
		# 开启实时仿真
		pybullet.setRealTimeSimulation(self.connection_mode == pybullet.GUI)
	
	def load_arm(self, arm_urdf_path=None):
		'''载入机械臂'''
		if arm_urdf_path is None:
			arm_urdf_path = str(Path(__file__).resolve().parent / "urdf" / "arm5dof.urdf")
		# 机械臂在世界坐标系下的位置, 单位m, 格式[x, y, z]
		arm_posi = [0, 0, 0]
		# 机械臂姿态-四元数, 格式 [x, y, z, w]
		arm_q =  [0, 0, 0, 1]
		# 定义标志位
		# 1. 开启机械臂连杆的自碰撞检测, 不检测与父连杆的碰撞
		flags = pybullet.URDF_USE_SELF_COLLISION_EXCLUDE_PARENT 
		# 2. 使用URDF模型里面的转动惯量
		flags |= pybullet.URDF_USE_INERTIA_FROM_FILE 
		# 载入机械臂URDF模型
		self.arm_id = pybullet.loadURDF(arm_urdf_path, arm_posi, arm_q, \
								useFixedBase=True, flags=flags)
		# 机械臂初始化
		# - 初始化机械臂的信息
		self.init_arm_info()
		# - 关节初始化
		self.reset_joints()
		# - 添加mimic约束
		self.add_joint_mimic_constraint()
		
	def init_arm_info(self):
		'''初始化机械臂的信息'''
		# 关节个数
		self.joint_num = pybullet.getNumJoints(self.arm_id)
		# 构造关节信息字典
		self.joint_info_dict = {}
		for joint_idx in range(self.joint_num):
			# 获取每个关节的信息
			joint_info = pybullet.getJointInfo(self.arm_id, joint_idx)
			# print(f"关节 #{joint_idx} 原始格式的joint info: {joint_info}")
			joint_name = joint_info[1].decode("utf-8")
			if joint_name in self.joint_name_list:
				# print("关节名称: {}".format(joint_name))
				# joint_info_dict[]
				joint_id = joint_info[0]
				joint_lower_limit = joint_info[8]
				joint_upper_limit = joint_info[9]
				joint_max_force = joint_info[10]
				joint_max_velocity = joint_info[11]
				joint_info = JointInfo(joint_id, joint_name, joint_lower_limit,
						joint_upper_limit, joint_max_force, joint_max_velocity)
				self.joint_info_dict[joint_name] = joint_info
		# 受控关节的名字列表
		# 右爪是从动，因此没有右爪
		self.ctl_joint_name_list = self.joint_name_list[:-1]
		# 受控关节ID列表
		self.ctl_joint_id_list = []
		for joint_name in self.ctl_joint_name_list:
			joint_id = self.joint_info_dict[joint_name].id
			self.ctl_joint_id_list.append(joint_id)
		# 受控关节的个数
		self.ctl_joint_num = len(self.ctl_joint_id_list)
		
	def reset_joints(self):
		'''关节重置'''	    
		# 控制多个旋转关节的角度
		# 位置控制 制定速度为0，位置为关节目标角度
		# 位置增益: Kp
		pybullet.setJointMotorControlArray(
			self.arm_id, self.ctl_joint_id_list,
			pybullet.POSITION_CONTROL,
			targetPositions=[0]*self.ctl_joint_num,
			targetVelocities=[0]*self.ctl_joint_num,
			positionGains=[1.0]*self.ctl_joint_num, 
			forces=[100.0]*self.ctl_joint_num)
	
	def add_joint_mimic_constraint(self):
		'''给关节添加Mimic约束'''
		# 但是在仿真环境下， 设置那个是主动关节不重要
		# 选择左爪为主动关节的原因是其角度范围为0-pi/2
		# 关节控制模式初始化
		# 将齿轮从动关节设置为速度控制模式,目标速度为0，最大力也必须设置为0
		# 这个很重要
		joint_info = self.joint_info_dict["right_gripper_joint"]
		pybullet.setJointMotorControl2(self.arm_id, joint_info.id,\
				pybullet.VELOCITY_CONTROL, targetVelocity=0, force=0)
		# 齿轮结构
		mimic_parent_name = 'left_gripper_joint'  # 齿轮父关节
		mimic_child_name = 'right_gripper_joint'  # 齿轮子关节
		
		# 注意：齿轮的约束，默认正值代表二者旋转角度异号， 负值代表同号
		mimic_gear_ratio = 1.0                         # 减速比与方向
		# 获取父子的关节ID
		mimic_parent_id = self.joint_info_dict[mimic_parent_name].id
		mimic_child_id = self.joint_info_dict[mimic_child_name].id
		mimic_max_force = 10000 # joint_info_dict[mimic_parent_name].max_force
		mimic_erp = 0.2
		# 设置约束
		mimic_constraint = pybullet.createConstraint(
				self.arm_id,    # 父body的ID
				mimic_parent_id,# 父关节的ID
				self.arm_id,    # 子Body的ID 
				mimic_child_id, # 子关节的ID
				jointType=pybullet.JOINT_GEAR, # 齿轮关节
				jointAxis=[0, 0, 1], 	       # 旋转轴 Z轴
				parentFramePosition=[0, 0, 0], # 父Body的关节坐标在质心上的偏移量  
				childFramePosition=[0, 0, 0])  # 子Body的关节坐标在质心上的偏移量 
		# 设置齿轮的减速比
		# erp: 约束误差容差 constraint error reduction parameter?
		# 实际上，感觉erp有点类似kp的效果
		pybullet.changeConstraint(mimic_constraint, gearRatio=mimic_gear_ratio, \
			maxForce=mimic_max_force, erp=mimic_erp)
	
	def set_joint_angle(self, joint_name, theta, is_wait=False, callback=None):
		'''设置关节角度'''
		# 关节ID
		joint_id = self.joint_info_dict[joint_name].id
		# print(f"JointID = {joint_id}")
		# 最大输出力矩
		max_force = self.joint_info_dict[joint_name].max_force
		# 控制多个旋转关节的角度
		# 位置控制 制定速度为0，位置为关节目标角度
		# 位置增益: Kp
		pybullet.setJointMotorControl2(
			self.arm_id, joint_id, pybullet.POSITION_CONTROL,
			targetPosition=theta, targetVelocity=0.0,
			positionGain=self.position_gain, \
			force=max_force)
		# 记录目标关节角度
		self.target_joints_angle_dict[joint_name] = theta
		if self.connection_mode == pybullet.DIRECT:
			pybullet.stepSimulation()
		# 等待
		if is_wait:
			self.wait(callback=callback)
	
	def set_joint_angle_list(self, theta_list, joint_name_list = None,  is_wait=False, callback=None):
		'''批量设置关节角度'''
		# 关节个数
		joint_num = len(theta_list)
		indexes = []
		forces = []
		for i in range(joint_num):
			joint_name = None
			if joint_name_list is None:
				joint_name = self.ctl_joint_name_list[i]
			else:
				joint_name = joint_name_list[i]
			joint = self.joint_info_dict[joint_name]
			indexes.append(joint.id)
			forces.append(joint.max_force)
			# 设置目标角度字典
			self.target_joints_angle_dict[joint_name] = theta_list[i]
		# 控制关节的数量
		ctl_joint_num = len(self.ctl_joint_name_list[:joint_num])
		# 控制多个旋转关节的角度
		pybullet.setJointMotorControlArray(
			self.arm_id, indexes, pybullet.POSITION_CONTROL, \
			targetPositions=theta_list, \
			targetVelocities=[0]*ctl_joint_num, \
			positionGains=self.position_gain_list[:ctl_joint_num], \
			forces=forces)
		if self.connection_mode == pybullet.DIRECT:
			pybullet.stepSimulation()
		# 等待
		if is_wait:
			return self.wait(callback=callback)
		else:
			return True

	def trajectory_plan(self, joint_name, theta_e:float, T:float, w_s:float=0.0, w_e:float=0.0, a_s:float=0, a_e:float=0):
		'''Minimum Jerk轨迹规划'''
		# 获取当前关节的
		theta_s = self.get_joint_angle(joint_name)
		# print("起始弧度 {} 中止弧度 {}".format(theta_s, theta_e))
		c = minimum_jerk_plan(theta_s, theta_e, w_s, w_e, a_s, a_e, T)
		t_arr, theta_arr = minimum_jerk_seq(T, c, delta_t=TRAJECTORY_DELTA_T)
		return t_arr, theta_arr
	
	def set_joint_angle_soft(self, joint_name, joint_angle, T=1.0, callback=None):
		'''设置单个关节角度带 Minimum Jerk轨迹规划'''
		t_arr, theta_arr = self.trajectory_plan(joint_name, joint_angle, T)
		# 按照轨迹去执行
		i = 0
		tn = len(t_arr)
		
		while True:
			t_start = time.time()
			if i >= tn:
				break
			next_theta = theta_arr[i]
			# 设置关节弧度
			self.set_joint_angle(joint_name, next_theta)
			t_end = time.time()
			m = int(math.ceil((t_end - t_start) / TRAJECTORY_DELTA_T))
			if m == 0:
				m = 1
			i += m
			# 补齐所需延迟等待的时间
			time.sleep(m*TRAJECTORY_DELTA_T - (t_end - t_start))
			# 回调函数执行
			if callback is not None and i%self.trajectory_callback_period == 0:
				callback()
		return theta_arr 
	
	def set_joint_angle_list_soft(self, thetas, T:float, callback=None):
		'''设置关节弧度2-带MinimumJerk 轨迹规划版本,需要阻塞等待.
		'''
		joint_num = len(thetas)
		joint_name_list = self.joint_name_list[:joint_num]
		# 将thetas转换为dict类型
		if type(thetas) == list:
			theta_arr = thetas
			thetas = {}
			for i in range(joint_num):
				joint_name = joint_name_list[i]    
				thetas[joint_name] = theta_arr[i]
		# print("Thetas: ")
		# print(thetas)
		
		# theta序列
		theta_seq_dict = {}
		t_arr = None # 时间序列
		# 生成轨迹序列
		for joint_name, theta_e in thetas.items():
			t_arr, theta_arr = self.trajectory_plan(joint_name, theta_e, T)
			theta_seq_dict[joint_name] = theta_arr

		# 按照轨迹去执行
		i = 0
		tn = len(t_arr)
		
		while True:
			t_start = time.time()
			if i >= tn:
				break
			next_thetas = []
			for joint_name in joint_name_list:
				next_thetas.append(theta_seq_dict[joint_name][i])
			# 设置关节弧度
			self.set_joint_angle_list(next_thetas, is_wait=False)
			t_end = time.time()
			m = int(math.ceil((t_end - t_start) / TRAJECTORY_DELTA_T))
			if m == 0:
				m = 1
			i += m
			# 补齐所需延迟等待的时间
			time.sleep(m*TRAJECTORY_DELTA_T - (t_end - t_start))
			# 回调函数执行
			if callback is not None and i%self.trajectory_callback_period==0:
				callback()
			
		return theta_seq_dict
		
	def get_joint_angle(self, joint_name):
		'''获取关节角度'''
		# 关节ID
		joint_id = self.joint_info_dict[joint_name].id
		
		# 获取关节状态
		joint_state = pybullet.getJointState(self.arm_id, joint_id)
		# 返回关节弧度
		return np.float64(joint_state[0])
	
	def get_joint_velocity(self, joint_name):
		'''获取关节速度'''
		# 关节ID
		joint_id = self.joint_info_dict[joint_name].id
		# 获取关节状态
		joint_state = pybullet.getJointState(self.arm_id, joint_id)
		# 返回关节弧度
		return np.float64(joint_state[1])
		
	def get_joint_angle_list(self, joint_name_list=None):
		'''批量获取关节角度'''
		theta_list = [] # 关节弧度列表
		if joint_name_list is not None:
			for joint_name in joint_name_list:
				theta_list.append(self.get_joint_angle(joint_name))
		else:
			for joint_idx in self.ctl_joint_id_list:
				# 获取关节状态
				joint_state = pybullet.getJointState(self.arm_id, joint_idx)
				# 获取关节弧度
				theta_i = joint_state[0]
				# 添加到关节列表里面
				theta_list.append(theta_i)
		return np.float64(theta_list)
	
	
	def get_joint_velocity_list(self):
		'''批量获取关节速度'''
		velocity_list = [] # 关节弧度列表
		for joint_idx in self.ctl_joint_id_list:
			# 获取关节状态
			joint_state = pybullet.getJointState(self.arm_id, joint_idx)
			# 获取关节弧度
			velocity_i = joint_state[1]
			# 添加到关节列表里面
			velocity_list.append(velocity_i)
		return np.float64(velocity_list)
	
	def get_tool_pose(self, return_type="XYZ_Pitch_Roll"):
		'''获取工具位姿
		返回格式: x, y, z, pitch, roll
		'''
		# 获取关节角度
		cur_joint_angle = self.get_joint_angle_list()[:5]
		# 正向运动学
		# 返回的数据格式: [x6, y6, z6, pitch, roll]
		return self.kinematic.forward_kinematic_v2(cur_joint_angle,\
	  		return_type=return_type)
		
	def inverse_kinematic(self, tool_posi, tool_pitch=np.pi/2, tool_roll=np.pi, is_debug=False):
		'''逆向运动学
		@tool_posi: 工具末端的位置
		@tool_pitch: 工具末端的俯仰角
		'''
		# 获取上次的关节角度
		last_joint_angle = self.get_joint_angle_list()[:5]
		if is_debug:
			print(f"上一次的关节角度: {last_joint_angle}")
		# 获取候选关节角度列表
		tx, ty, tz = tool_posi
		candi_joint_angle_list = self.kinematic.inverse_kinematic(\
	  		tx, ty, tz, tool_pitch, tool_roll, last_joint_angle=last_joint_angle, is_debug=is_debug)
		# 选取一个
		if len(candi_joint_angle_list) == 0:
			return False, None
		else:
			# TODO 选取一个最合适的解
			return True, candi_joint_angle_list[-1]
	
	def auto_gen_pitch(self, p_tool:list):
		'''自动生成俯仰角'''
		x, y, z = p_tool
		x0 = np.sqrt(x**2 + y**2)
		return PITCH_PANEL_A*x0 + PITCH_PANEL_B*z + PITCH_PANEL_C

	def adjust_tool_posi(self, p_tool:list):
		'''Apply the same radial Z correction as the physical-arm controller.'''
		x, y, z = p_tool
		k, b = Z_ERROR_POLYFIT
		return [x, y, z + k * np.sqrt(x**2 + y**2) + b]
	
	def set_tool_pose(self, tool_posi=None, tool_pitch=None, \
		tool_roll=np.pi, pose_name=None, is_soft_move=True, T=1.0, \
		is_wait=False, is_debug=False, callback=None):
		'''设置工具位姿'''
		# 根据名称填充位姿
		if pose_name is not None:
			# 使用位姿名称
			if pose_name in ARM_POSE_DICT.keys():
				x, y, z, tool_pitch, tool_roll = ARM_POSE_DICT[pose_name]
				tool_posi = [x, y, z]
			else:
				# 未知的位姿名称
				return False
		
		# 自动生成Pitch
		tool_posi = self.adjust_tool_posi(tool_posi)
		if tool_pitch is None:
			tool_pitch = self.auto_gen_pitch(tool_posi)
		# 逆向运动学
		ret, thetas = self.inverse_kinematic(\
			tool_posi, tool_pitch, tool_roll, is_debug=is_debug)
		# 判断是否有解
		if not ret:
			logging.warn('机械臂末端不能到达: {} Pitch={} Rool={}'.format(\
				tool_posi, tool_pitch, tool_roll))
			return False
		# 控制关节
		if is_soft_move:
			self.set_joint_angle_list_soft(thetas, T, callback=callback)
		else:
			return self.set_joint_angle_list(thetas, is_wait=is_wait, callback=callback)
	
	def set_gripper_angle(self, angle=0.0, is_soft_move=True, T=1.0, is_wait=True, callback=None):
		'''设置夹爪角度'''
		if is_soft_move:
			self.set_joint_angle_soft("left_gripper_joint", angle, T=T, callback=callback)
		else:
			self.set_joint_angle("left_gripper_joint", angle, is_wait=is_wait, callback=callback)
			
	def gripper_open(self, angle=np.pi/4, is_soft_move=True, T=1.0, is_wait=True, callback=None):
		'''夹爪张开'''
		self.set_gripper_angle(angle=angle, is_soft_move=is_soft_move, T=T, is_wait=is_wait, callback=callback)
		
	def gripper_close(self, angle=0, is_soft_move=True, T=1.0, is_wait=True, callback=None):
		'''夹爪闭合'''
		self.set_gripper_angle(angle=angle, is_soft_move=is_soft_move, T=T, is_wait=is_wait, callback=callback)
	
	def is_stop(self):
		'''返回当前机械臂末端是否静止'''
		tgt_jnt_dict = self.target_joints_angle_dict
		for joint_name in tgt_jnt_dict:
			# 判断关节是否运动到了目标位置
			target_angle = tgt_jnt_dict[joint_name]
			cur_angle = self.get_joint_angle(joint_name)
			if np.abs(target_angle - cur_angle) > self.angle_tolerance:
				# 角度误差大于容差
				return False
			# 判断关节是否在旋转
			cur_velocity = self.get_joint_velocity(joint_name)
			if np.abs(cur_velocity) > self.velocity_tolerance:
				return False
		return True
		
	def wait(self, timeout=10, callback=None):
		'''等待机械臂运动到目的地'''
		t_start = time.time()
		while not self.is_stop():
			if self.connection_mode == pybullet.DIRECT:
				pybullet.stepSimulation()
			t_cur = time.time() 
			if t_cur - t_start > self.wait_timeout:
				# 超时
				return False
			if callback is not None:
				callback()
			time.sleep(1.0 / 240.0 if self.connection_mode == pybullet.DIRECT else 0.1)
		return True
	
	def stop(self):
		'''机械臂停止运动'''
		# [PROBLEM] 这里有个小BUG
		# 在机械臂静止的时候，执行stop指令可以看到关节的微动
		# 机械臂末端下沉一点点距离，执行次数越多，下沉越明显。
		# 应该是跟PID参数调节以及控制器的实现逻辑有关? 目前没有找到解决办法
		
		# 获取当前的关节角度
		cur_joint_angle = self.get_joint_angle_list()
		# 设置关节角度为当前的角度
		self.set_joint_angle_list(cur_joint_angle)

	def close(self):
		'''Disconnect this simulator instance when the demo is complete.'''
		if pybullet.isConnected():
			pybullet.disconnect()
