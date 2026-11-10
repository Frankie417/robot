"""Create the new config and notebook once; never overwrite existing files."""
import json
from pathlib import Path
import math

HERE=Path(__file__).resolve().parent


def write_new(path,value):
    with path.open('x',encoding='utf-8') as stream:
        stream.write(value)


def main():
    def pose(x,y,z,pitch,roll):
        return dict(x=x,y=y,z=z,pitch_deg=pitch,roll_deg=roll)
    bins={}
    source=[('green','厨余垃圾',122.8,114.8,122.8,112.7,-945200.4),
            ('yellow','其他垃圾',219.0,99.8,135.6,106.5,137329.9),
            ('blue','可回收物',207.8,-141.3,133.3,104.5,137329.9),
            ('red','有害垃圾',127.4,-131.8,146.4,94.5,148789.0)]
    for color,label,x,y,z,pitch,rawroll in source:
        bins[color]=dict(label=label,pose=pose(x,y,z,pitch,None),above=pose(x,y,z+15,pitch,None),
                         raw_roll_deg=rawroll,diagnostic_modulo_roll_deg=round((rawroll+180)%360-180,1),
                         note='User supplied bin destination. Roll unset pending teaching. +15 mm is only an IK-feasible starting reference; confirm rim clearance and route.')
    config=dict(sdk_dir='/home/jetson/Notebook/4.机械臂OpenCV视觉处理实验',arm_port='/dev/ttyTHS1',camera_device=0,
                physical_calibration_confirmed=False,
                observation_pose=pose(150.0,0.0,200.0,96.1,180.0),
                p4=dict(pick=pose(192.2,-11.2,13.8,132.7,144.5),above=pose(192.2,-11.2,68.8,132.7,144.5),
                        note='Reference from week3 bottom-layer PICK, not week4 STACK destination. Reteach for this table/block and gripper.'),
                move_seconds=1.5,gripper_seconds=.7,open_angle_rad=math.pi/4,release_angle_rad=.40,
                bin_map=bins,
                vision=dict(confirm_frames=6,empty_frames=8,position_tolerance_px=18,reset_delay_seconds=.5,
                            frame_delay_seconds=.04,min_scene_brightness=10,min_area=700,kernel_size=5,
                            hsv=dict(red=[[[0,90,70],[10,255,255]],[[170,90,70],[179,255,255]]],
                                     yellow=[[[18,80,80],[38,255,255]]],green=[[[40,60,35],[90,255,255]]],
                                     blue=[[[95,80,50],[135,255,255]]])))
    write_new(HERE/'bin_map.json',json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    cells=[]
    def add(kind,text):
        cell=dict(cell_type=kind,metadata={},source=text.splitlines(keepends=True))
        if kind=='code':
            cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    add('markdown','# Ch6 固定 P4 四色垃圾桶自动分拣\n\n在 Jetson 的 JupyterLab 中运行本 notebook，本机浏览器只作操作界面。先预览/演练，真机运行前核对 `bin_map.json`。运行定义单元不会移动机械臂。完整说明见 README.md。\n')
    add('code',"from pathlib import Path\nimport sys\nBASE = Path.cwd()\nif not (BASE / 'week6_color_sorting.py').is_file():\n    raise FileNotFoundError('请在 week6_p4 文件夹中打开 notebook')\nif str(BASE) not in sys.path:\n    sys.path.insert(0, str(BASE))\nfrom sorting_core import load_config\nfrom week6_color_sorting import create_panel\nconfig = load_config(BASE / 'bin_map.json')\nprint('默认演练；物块每轮放在固定 P4；自动识别颜色，无需下拉选择颜色。')\nprint('桶位 Roll 尚未填入时，可以预览/演练，但不能连接真机。')\n")
    add('markdown','## 参数检查\n\n所有角度在配置中为度，发给 SDK 时只转换一次。不要把 week4 的堆叠放置高度当作 P4 抓取高度；不要直接把异常 Roll 填入运动位姿。编辑本新建配置后，停止旧面板并重新运行参数加载单元。\n')
    add('code',"for color, item in config['bin_map'].items():\n    print(color, item['label'], item['pose'], 'raw_roll=', item['raw_roll_deg'])\nprint('P4:', config['p4'])\n")
    add('markdown','## 实时预览和自动分拣\n\n点击启动摄像头，用 x/y/width/height 圈住 P4 并应用 ROI；演练模式下点击开始自动分拣。每轮只放一个物块。分拣后必须在动作结束之后连续看到 P4 空区，才会重新准备；BUSY 遮挡不计为空区。\n\n真机：先完成示教/检查并更新配置，再连接真机、回观察位、重新设置 P4 ROI、开始自动分拣。停止当前动作会取消剩余轨迹并保持位置，真实表现仍需现场检查。\n')
    add('code','runtime = create_panel(config)\n')
    add('markdown','## 数据记录\n\n每轮识别截图、阶段事件自动保存到 results。现场观察后，在面板填真实颜色、实际投放桶、成功/失败和备注，点击记录本轮实测。程序 done 不自动算实际分拣成功。课程 PDF 建议 8 次中至少 7 次正确；报告模板写至少 6 次，以教师最终要求为准。\n')
    add('code',"print('本次结果目录：', runtime.output)\nprint('当前状态：', runtime.gate.state)\n")
    add('markdown','## 结束\n\n点击关闭预览，或运行下面单元，等待动作线程制停并关闭串口后再关闭内核。停止后不自动回零或松爪。\n')
    add('code','runtime.close()\n')
    notebook=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python',version='3.6')),nbformat=4,nbformat_minor=4)
    write_new(HERE/'week6_color_sorting.ipynb',json.dumps(notebook,ensure_ascii=False,indent=1)+'\n')
    print('Created bin_map.json and week6_color_sorting.ipynb')


if __name__=='__main__':
    main()
