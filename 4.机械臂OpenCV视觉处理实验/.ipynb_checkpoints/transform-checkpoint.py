'''
刚体空间变换 工具库
----------------------------------------------
@https://www.dice.com.cn/
'''
import math
import numpy as np
from numpy import sin, cos, pi

class Transform:
	@staticmethod
	def dxmat(dx):
		'''沿X轴平移'''
		return np.float32([
			[1, 0, 0, dx],
			[0, 1, 0, 0],
			[0, 0, 1, 0],
			[0, 0, 0, 1]])
	@staticmethod
	def dymat(dy):
		'''沿Y轴平移'''
		return np.float32([
			[1, 0, 0, 0],
			[0, 1, 0, dy],
			[0, 0, 1, 0],
			[0, 0, 0, 1]])
	
	@staticmethod
	def dzmat(dz):
		'''沿Z轴平移'''
		return np.float32([
			[1, 0, 0, 0],
			[0, 1, 0, 0],
			[0, 0, 1, dz],
			[0, 0, 0, 1]])
	@staticmethod
	def rxmat(gamma):
		'''绕X轴旋转'''
		return np.array([
			[1, 0,           0,          0],
			[0, cos(gamma), -sin(gamma), 0],
			[0, sin(gamma),  cos(gamma), 0],
			[0, 0,           0,          1]])

	@staticmethod
	def rymat(beta):
		'''绕Y轴旋转'''
		return np.array([
			[cos(beta),  0,  sin(beta), 0],
			[0,          1,  0,         0],
			[-sin(beta), 0,  cos(beta), 0],
			[0,           0,  0,         1]])
	@staticmethod
	def rzmat(alpha):
		return np.array([
			[cos(alpha), -sin(alpha), 0, 0],
			[sin(alpha),  cos(alpha), 0, 0],
			[0,           0,          1, 0],
			[0,           0,          0, 1]])
	@staticmethod
	def dhmat(alpha, a, theta, d):
		'''DH变换矩阵'''
		dhmat = Transform.rxmat(alpha)
		dhmat = dhmat.dot(Transform.dxmat(a))
		dhmat = dhmat.dot(Transform.rzmat(theta))
		dhmat = dhmat.dot(Transform.dzmat(d))
		return dhmat

	@staticmethod
	def euler2rmat(roll=0, pitch=0, yaw=0):
		'''欧拉角转换为旋转矩阵''' 
		alpha, beta, gamma = yaw, pitch, roll
		cos_gamma = np.cos(gamma)
		sin_gamma = np.sin(gamma)
		cos_beta = np.cos(beta)
		sin_beta = np.sin(beta)
		cos_alpha = np.cos(alpha)
		sin_alpha = np.sin(alpha)

		r11 = cos_alpha*cos_beta
		r12 = -sin_alpha*cos_gamma + sin_beta*sin_gamma*cos_alpha
		r13 = sin_alpha*sin_gamma + sin_beta*cos_alpha*cos_gamma
		r21 = sin_alpha*cos_beta
		r22 = sin_alpha*sin_beta*sin_gamma + cos_alpha*cos_gamma
		r23 = sin_alpha*sin_beta*cos_gamma - sin_gamma*cos_alpha
		r31 = -sin_beta
		r32 = sin_gamma*cos_beta
		r33 = cos_beta*cos_gamma
		return np.array([
			[r11, r12, r13],
			[r21, r22, r23],
			[r31, r32, r33]])
	@staticmethod
	def rmat2euler(rmat):
		'''旋转矩阵转换为欧拉角'''
		alpha = None # 偏航角
		beta = None  # 俯仰角
		gamma = None # 横滚角
		
		r11, r12, r13, r21, r22, r23, r31, r32, r33 = rmat.reshape(-1)
		if abs(r31) >= (1 - 0.000001):
			# 出现万向锁的问题
			if r31 < 0:
				gamma = 0
				beta = np.pi/2
				alpha = math.atan2(r23, r22)
				return [[gamma, beta, alpha]]
			else:
				gamma = 0
				beta = -np.pi/2
				alpha = math.atan2(-r23, r22)
				return [[gamma, beta, alpha]]
		else:
			# 正常求解
			cos_beta = np.sqrt(r32*r32 +r33*r33)
			cos_beta_list = [cos_beta, -cos_beta]
			rpy_list = []
			for cos_beta in cos_beta_list:
				beta = math.atan2(-r31, cos_beta)
				alpha = math.atan2(r21/cos_beta, r11/cos_beta)
				gamma = math.atan2(r32/cos_beta, r33/cos_beta)
				rpy_list.append([gamma, beta, alpha])
			return rpy_list
	
	@staticmethod
	def inverse(T):
		'''齐次变换矩阵求逆'''
		R = T[:3, :3]
		t = T[:3, 3].reshape((3, 1))
		R_T = R.T
		T_inv = np.eye(4)
		T_inv[:3, :3] = R_T
		T_inv[:3, 3] = -R_T.dot(t).reshape(-1)
		return T_inv
