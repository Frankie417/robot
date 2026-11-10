"""Build two standalone notebooks; neither needs sibling Python modules."""
import ast
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
LOCAL={'week8_settings','control','recognition','network_link','arm_interrupt','vision_sorter','receiver','receiver_panel'}


class Inline(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        return None if node.module in LOCAL else node

    def visit_FunctionDef(self,node):
        return None if node.name=='main' else self.generic_visit(node)

    def visit_If(self,node):
        if isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name) and node.test.left.id=='__name__':
            return None
        return self.generic_visit(node)

    def visit_Assign(self,node):
        names=[target.id for target in node.targets if isinstance(target,ast.Name)]
        if 'ROOT' in names:
            return ast.parse('ROOT = Path.cwd()').body[0]
        if '模型路径' in names:
            return ast.parse("模型路径 = Path.cwd()/'models/gesture_recognizer.task'").body[0]
        return self.generic_visit(node)


def build(name,title,intro,modules,last,language_version):
    cells=[]
    def add(kind,text):
        cell=dict(cell_type=kind,metadata={},source=text.splitlines(keepends=True))
        if kind=='code':
            cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    add('markdown','# '+title+'\n\n'+intro+'\n')
    add('markdown','## 集中参数\n\n手势默认 1红、2黄、3绿、5蓝，OK 确认。Five 不再停止。接收服务使用 8766 端口。下方抓取参数取自本次提供的 Week6 代码，原文件中的旧文字说明不参与计算。\n')
    add('code',(HERE/'week8_settings.py').read_text(encoding='utf-8'))
    for module in modules:
        add('markdown','## 内置 '+module+'\n\n直接运行，不需要另存为 .py 文件。\n')
        tree=Inline().visit(ast.parse((HERE/(module+'.py')).read_text(encoding='utf-8')))
        ast.fix_missing_locations(tree)
        code=ast.unparse(tree)+'\n'
        ast.parse(code,feature_version=(3,6))
        add('code',code)
    add('markdown','## 启动界面\n\n'+last[0]+'\n')
    add('code',last[1]+'\n')
    joined='\n'.join(''.join(c['source']) for c in cells if c['cell_type']=='code')
    for module in LOCAL:
        assert 'from '+module+' import' not in joined,module
    assert '__file__' not in joined
    nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),
                                     language_info=dict(name='python',version=language_version)),nbformat=4,nbformat_minor=4)
    with (HERE/name).open('x',encoding='utf-8') as stream:
        json.dump(nb,stream,ensure_ascii=False,indent=1)


def main():
    build('week8_jetson.ipynb','Week8 Jetson 接收与抓取',
          '在 Jetson 的 JupyterLab 中运行本 notebook。只上传这一个 notebook 即可获得业务代码；仍需设备原有 SDK/config 和 NumPy/OpenCV/pyserial/ipywidgets。关闭其他 Week6/Week7 的相机及串口连接。启动服务只连接设备，不移动；本机发送 prepare 后才回拍摄位，1/2/3/5 加 OK 后才抓取。',
          ['arm_interrupt','vision_sorter','receiver','receiver_panel'],
          ('点击启动 Week8 服务，把本次 TOKEN 复制到本机。地址 http://192.168.55.1:8766。仅真机模式，不需要 Jetson 安装 MediaPipe。停止当前动作按钮优先制停；关闭服务会等待制停并释放设备。',
           'service = create_receiver_panel(SORT_CONFIG)'), '3.6')
    build('week8_laptop.ipynb','Week8 本机手势选色',
          '必须使用本机 Python 3.11 内核，不能在 Jetson 的网页内核运行。需要将 models/gesture_recognizer.task 与 notebook 保存在同目录。运行会弹出本机桌面窗口；不自动打开摄像头或发运动命令。也可以直接双击 start_week8_laptop.bat。',
          ['control','recognition','network_link','app'],
          ('本机启动摄像头 → 连接 Week8 的 8766 服务并填本次 TOKEN → 解除停止 → Jetson回拍摄位 → P4 放一块 → 准备下一条 → 1红/2黄/3绿/5蓝 → OK。每轮只发一次。Five 使用较低门槛并增加宽松手掌几何判断，仍需 OK。停止用红色按钮或 Esc。窗口关闭后本单元结束。',
           "window = tk.Tk()\napp = App(window)\nwindow.mainloop()"), '3.11')
    print('Created standalone Week8 Jetson and laptop notebooks.')


if __name__=='__main__':
    main()
