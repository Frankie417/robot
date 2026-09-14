'''
将画面中的2D像素转换为工作上的坐标
----------------------------------------------
'''
import os
import numpy as np
import cv2
import yaml

class Image2Workspace:
    '''图像像素转换为工作台'''
    def __init__(self, cam, config_folder="config"):
        self.config_folder = config_folder
        self.cam = cam
        # 载入九点标定法的配置文件
        handeye_9points_config = None
        file_path =  os.path.join(self.config_folder, "handeye_9points.yaml")
        with open(file_path, 'r', encoding='utf-8') as f:
            handeye_9points_config = yaml.load(f.read(), Loader=yaml.SafeLoader)
        # 工作台上九点坐标(2D)
        self.board_width = handeye_9points_config["board_width"]
        self.board_height = handeye_9points_config["board_height"]
        # P0点的坐标
        x0 = 0.5 * self.board_height
        y0 = 0.5 * self.board_width
        self.x0 = x0
        self.y0 = y0
        self.ws_9points_2d = np.float64([
            [x0, y0],   #P0
            [x0, 0],    #P1
            [x0, -y0],  #P2
            [0, y0],    #P3
            [0, 0],     #P4
            [0, -y0],   #P5
            [-x0, y0],  #P6
            [-x0, 0],   #P7
            [-x0, -y0], #P8
        ])
        # 载入九点在2D图像中的坐标
        self.img_9points = np.loadtxt(os.path.join(self.config_folder, "img9points.txt"), delimiter=',')

        # 载入相机外参
        # 相机坐标系到工作台坐标系的变换
        self.T_cam2ws = np.loadtxt(os.path.join(self.config_folder, "T_cam2ws.txt"), delimiter=',')
        # 转换为旋转向量与平移向量的形式
        self.rvec_cam2ws = cv2.Rodrigues(self.T_cam2ws[:3, :3])[0]
        self.tvec_cam2ws = self.T_cam2ws[:3, 3]
        # 载入工件平面的高度
        object_config = None
        with open(os.path.join(self.config_folder, "object.yaml"), 'r', encoding='utf-8') as f:
            object_config = yaml.load(f.read(), Loader=yaml.SafeLoader)
        self.object_height = object_config["height"]
        # 更新仿射变换矩阵
        self.update_affine_matrix(self.object_height)

    def get_img_9points(self, height):
        '''获取9点在画面中的坐标
        @height: 物体上表面距离工作台的高度
        '''
        # 给九点赋值Z轴坐标
        ws_9points_z = np.zeros((9, 3))
        ws_9points_z[:, :2] = self.ws_9points_2d
        ws_9points_z[:, 2] = height
        # 3D点投影在2D像素中
        img_9points_z_2d, jacobian = cv2.projectPoints(\
            ws_9points_z, self.rvec_cam2ws, self.tvec_cam2ws, \
            self.cam.intrinsic_new, self.cam.distortion_new)
        # 得到工作台九点在特定高度下的像素投影
        img_9points_z_2d = img_9points_z_2d.reshape((-1, 2))
        return img_9points_z_2d

    def update_affine_matrix(self, height):
        '''更新仿射变换矩阵'''
        self.img_9points_z_2d = self.get_img_9points(height)
        # 计算仿射变换矩阵
        self.affine2d_matrix = cv2.estimateAffine2D(self.img_9points_z_2d, \
            self.ws_9points_2d)[0]
        return self.affine2d_matrix

    def img2workspace(self, px, py):
        '''像素坐标转换为工作台坐标'''
        a, b, c, d, e, f = self.affine2d_matrix.reshape(-1)
        wx = a*px + b*py + c 
        wy = d*px + e*py + f
        return (wx, wy)

if __name__ == "__main__":
    import numpy as np
    import cv2
    # 测试脚本
    from camera import Camera

    # 创建相机对象
    camera = Astra()
    # 初始相机
    camera.init_video_stream()
    # 载入标定数据
    camera.load_cam_calib_data()

    # 创建图像像素坐标转化为工作台的转换器
    img2ws = Image2Workspace(camera)
    # 为了方便测试，将工件高度设置为0
    img2ws.update_affine_matrix(0.0)

    # 创建一个名字叫做 “image_win” 的窗口
    win_name = 'image_win'
    cv2.namedWindow(win_name,flags=cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO | cv2.WINDOW_GUI_EXPANDED)
    # 鼠标在画面中的位置
    px = 0
    py = 0
    # 鼠标回调事件
    def on_mouse(event,x,y,flags,param):
        global px, py
        if event == cv2.EVENT_MOUSEMOVE:
            # 鼠标移动事件
            px = x
            py = y
    # 将on_mouse回调事件绑定到窗口image_win上
    cv2.setMouseCallback(win_name, on_mouse)

    while True:
        # 获取彩图与深度图
        color_image = camera.read()
        # 去除图像畸变
        color_image = camera.remove_distortion(color_image)
        # 将像素坐标转换为工作台坐标
        wx , wy = img2ws.img2workspace(px, py)
        # 创建画布
        canvas = np.copy(color_image)
        # 添加帮助信息
        cv2.putText(canvas, text=f'PX: {px} PY: {py}',\
                org=(50, camera.config['img_height']-50), fontFace=cv2.FONT_HERSHEY_SIMPLEX, \
                fontScale=1, thickness=2, lineType=cv2.LINE_AA, color=(0, 0, 255))
        cv2.putText(canvas, text=f'WS: X {wx:.1f} Y {wy:.1f}',\
                org=(50, camera.config['img_height']-100), fontFace=cv2.FONT_HERSHEY_SIMPLEX, \
                fontScale=1, thickness=2, lineType=cv2.LINE_AA, color=(0, 0, 255))

        # 更新窗口“image_win”中的图片
        cv2.imshow('image_win', canvas)

        key = cv2.waitKey(1)
        if key == ord('q'):
            # 如果按键为q 代表quit 退出程序
            break

    # 关闭摄像头
    camera.release()
    # 销毁所有的窗口
    cv2.destroyAllWindows()