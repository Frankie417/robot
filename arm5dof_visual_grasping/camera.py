'''Astra 3D相机 Python SDK
----------------------------------------------
'''
import os
import time
import pickle
import math
import yaml
import logging
import numpy as np
import cv2

class Camera:
    '''Camera相机类'''
    IS_DEBUG = True
    def __init__(self,id=None,config_folder="config"):
        self.config_folder = config_folder
        cam_config_path = os.path.join(config_folder, "camera.yaml")
        with open(cam_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.load(f.read(), Loader=yaml.SafeLoader)
        if id is None:
            self.id = int(self.config['device'])
        else:
            self.id = id
        self.capture = self.get_video_capture()
        
    # 设置摄像头参数   
    def init_uvc_param(self):
        '''UVC摄像头初始化'''
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl brightness={}".format(self.id,  self.config['uvc']['brightness']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl contrast={}".format(self.id,  self.config['uvc']['contrast']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl hue={}".format(self.id,  self.config['uvc']['hue']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl saturation={}".format(self.id,  self.config['uvc']['saturation']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl sharpness={}".format(self.id,  self.config['uvc']['sharpness']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl gamma={}".format(self.id,  self.config['uvc']['gamma']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl gain={}".format(self.id,  self.config['uvc']['gain']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl white_balance_temperature_auto={}".format(self.id,  self.config['uvc']['white_balance_temperature_auto']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl white_balance_temperature={}".format(self.id,  self.config['uvc']['white_balance_temperature']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl backlight_compensation={}".format(self.id,  self.config['uvc']['backlight_compensation']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl exposure_auto={}".format(self.id,  self.config['uvc']['exposure_auto']))
        os.system("v4l2-ctl -d /dev/video{} --set-ctrl exposure_absolute={}".format(self.id,  self.config['uvc']['exposure_absolute']))

    def get_video_capture(self):
        '''初始化视频流'''
        if os.name == 'nt':
            # Windows
            # capture = cv2.VideoCapture(device, cv2.CAP_DSHOW)
            self.capture = cv2.VideoCapture(self.id)
        elif os.name == 'posix':
            # Linux
            # capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
            # print("Device: {}".format(device))
            # 初始化UVC摄像头参数
            #self.init_uvc_param()
            self.capture = cv2.VideoCapture(self.id)
        # 设置分辨率
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.config['img_height']))#设置图像高度
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.config['img_width'])) #设置图像宽度
        self.capture.set(cv2.CAP_PROP_FPS,  int(self.config['fps']))
        self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')) # 设置编码方式
        # 缓冲区设置为1结果就是帧率只有 15fps
        # 缓冲区设置为2之后帧率提升到40FPS
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, int(self.config['buffer_size']) )#设置视频缓冲区为3
        
        return self.capture
    
    def read(self):
        '''获取图像'''
        ret, frame = self.capture.read()
        if not ret:
            return ret, frame
        if self.config['vflip'] and self.config['hflip']:
            frame = cv2.flip(frame, -1) # 同时垂直镜像与水平镜像
        elif self.config['vflip']:
            frame = cv2.flip(frame, 0)
        elif self.config['hflip']:
            frame = cv2.flip(frame, 1)
            
        if self.config['roi']['enable']:
            frame = frame[self.config['roi']['y']:self.config['roi']['y']+self.config['roi']['h'], self.config['roi']['x']:self.config['roi']['x']+self.config['roi']['w']]
        return ret, frame
    
    def load_cam_calib_data(self):
        '''载入相机标定数据'''
        # 读取标定参数
        # 获取摄像头内参
        self.intrinsic = np.loadtxt(os.path.join(self.config_folder, 'M_intrisic.txt'), delimiter=',')
        # 获取摄像头的畸变系数
        self.distortion = np.loadtxt(os.path.join(self.config_folder, 'distor_coeff.txt'), delimiter=',')
        # 去除畸变后的相机内参与畸变系数
        self.intrinsic_new = np.loadtxt(os.path.join(self.config_folder, 'M_intrisic_new.txt'), delimiter=',')
        self.distortion_new = np.ndarray([0, 0, 0, 0, 0]).astype("float32")
        # x轴的映射
        self.remap_x = np.load(os.path.join(self.config_folder, 'remap_x.npy'))
        # y轴映射
        self.remap_y = np.load(os.path.join(self.config_folder, 'remap_y.npy'))
        # 根据相机标定参数
        # 提取图像中心(cx, cy)与焦距f(单位：像素)
        self.fx = self.intrinsic[0, 0]
        self.fy = self.intrinsic[1, 1]
        self.f = (self.fx + self.fy) / 2

        # 图像中心的坐标
        self.cx = self.intrinsic[0, 2]
        self.cy = self.intrinsic[1, 2]
        # 生成视场角等相关参数
        self.alpha1 = np.arctan(self.cy/self.f)
        self.alpha2 = np.arctan((self.config['img_height']-self.cy)/self.f)
        self.beta1 = np.arctan(self.cx/self.f)
        self.beta2 = np.arctan((self.config['img_width']-self.cx)/self.f)

    def remove_distortion(self, image):
        '''图像去除畸变'''
        return cv2.remap(image, self.remap_x, self.remap_y, cv2.INTER_LINEAR)

    def empty_cache(self):
        '''清空摄像头的缓冲区'''
        for i_frame in range(self.config['buffer_size']):
            ret, frame = self.capture.read()



        
def main(argv):
    '''调整相机参数, 预览图像'''
    img_cnt = FLAGS.img_cnt
    # 是否显示FPS信息
    is_show_fps = False
    # 创建相机对象
    camera = Camera()
    # 初始相机
    capture = camera.capture
    print("FLAGS.rm_distortion = {}".format(FLAGS.rm_distortion))

    if FLAGS.rm_distortion:
        # 载入标定数据
        camera.load_cam_calib_data()
    # 创建一个名字叫做 “color” 的窗口
    cv2.namedWindow("color", \
        flags=cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO | cv2.WINDOW_GUI_EXPANDED)
    fps = 30 # 设定一个初始值
    while True:
        start = time.time()
        # 获取彩图与深度图
        ret,image = camera.read()
        if not ret:
            logging.error('图像获取失败')
            break
        if FLAGS.rm_distortion:
            # 图像去除畸变
            image = camera.remove_distortion(image)

        # 创建画布
        canvas = np.copy(image)
        if is_show_fps:
            # 添加帮助信息
            cv2.putText(canvas, text='S:Save Image',\
                    org=(50, camera.config['img_height']-100), fontFace=cv2.FONT_HERSHEY_SIMPLEX, \
                    fontScale=1, thickness=2, lineType=cv2.LINE_AA, color=(0, 0, 255))
            cv2.putText(canvas, text='Q: Quit',\
                    org=(50, camera.config['img_height']-50), fontFace=cv2.FONT_HERSHEY_SIMPLEX, \
                    fontScale=1, thickness=2, lineType=cv2.LINE_AA, color=(0, 0, 255))

            # 在画布上添加帧率的信息
            cv2.putText(canvas, text='FPS: {}'.format(fps),\
                    org=(50, 50), fontFace=cv2.FONT_HERSHEY_SIMPLEX, \
                    fontScale=1, thickness=2, lineType=cv2.LINE_AA, color=(0, 0, 255))
        # 更新窗口“color”中的图片
        cv2.imshow('color', canvas)

        end = time.time()
        fps = int(0.6*fps +  0.4*1/(end-start))
        # fps = 1
        key = cv2.waitKey(1)

        if key == ord('q'):
            # 如果按键为q 代表quit 退出程序
            break
        elif key == ord('s'):
            # s键代表保存数据
            cv2.imwrite('{}/{}.png'.format(FLAGS.img_path, img_cnt), image)
            logging.info("截图，并保存在  {}/{}.png".format(FLAGS.img_path, img_cnt))
            img_cnt += 1

    # 关闭摄像头
    capture.release()
    # 销毁所有的窗口
    cv2.destroyAllWindows()

if __name__ == '__main__':
    import logging
    import sys
    from absl import app
    from absl import flags

    # 设置日志等级
    logging.basicConfig(level=logging.INFO)

    # 定义参数
    FLAGS = flags.FLAGS
    flags.DEFINE_integer('img_cnt', 0, '图像计数的起始数值')
    flags.DEFINE_string('img_path', 'data/image_raw', '图像的保存地址')
    flags.DEFINE_boolean('rm_distortion', False, '载入相机标定数据, 去除图像畸变')

    # 运行主程序
    app.run(main)

