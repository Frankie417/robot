"""Jetson notebook controls. Starting the service connects UART but does not move."""
import copy
import html
import secrets
import threading
import time
import traceback
from receiver import Engine,make_server
from vision_sorter import Week8Arm
from week8_settings import SORT_CONFIG,RECEIVER_PORT


def create_receiver_panel(config=None):
    import ipywidgets as widgets
    from IPython.display import display
    previous=globals().get('_week8_service')
    if previous and (previous.get('engine') or previous.get('starting')):
        raise RuntimeError('旧 Week8 接收服务仍在运行；先关闭服务，等待串口释放')
    config=copy.deepcopy(SORT_CONFIG if config is None else config)
    state={'engine':None,'server':None,'starting':False,'closing':False,'preview':None}
    globals()['_week8_service']=state
    start=widgets.Button(description='启动 Week8 服务',button_style='success')
    stop=widgets.Button(description='停止当前动作',button_style='danger')
    close=widgets.Button(description='关闭服务')
    status=widgets.HTML(value='未启动；先关闭 Week6/Week7 的相机与舵机连接。')
    token_label=widgets.HTML(value='')
    camera=widgets.Image(format='jpeg',width=640)
    output=widgets.Output()

    def preview():
        while state['engine'] is not None and not state['closing']:
            engine=state['engine']
            try:
                jpeg=engine.arm.camera.jpeg()
                if jpeg:
                    camera.value=jpeg
                snapshot=engine.status()
                text='BUSY {} / STOP {} / 阶段 {} / P4 {} / 等待空场 {}'.format(
                    snapshot['busy'],snapshot['stopped'],snapshot['vision']['stage'],
                    snapshot['vision']['p4_colors'],snapshot['vision']['p4_need_empty'])
                status.value=html.escape(text)
            except Exception as error:
                status.value='预览异常：'+html.escape(str(error))
            time.sleep(.2)

    def on_start(_):
        if state['engine'] is not None or state['starting']:
            return
        state['starting']=True
        status.value='正在预检、连接 SDK 和打开相机；此时不移动机械臂。'
        def worker():
            engine=None;server=None
            try:
                engine=Engine(lambda event:Week8Arm(event,config))
                token=secrets.token_urlsafe(24)
                server=make_server(engine,token,port=RECEIVER_PORT)
                state.update(engine=engine,server=server,closing=False)
                threading.Thread(target=server.serve_forever,daemon=True).start()
                token_label.value='<b>URL:</b> http://192.168.55.1:{}<br><b>TOKEN:</b> {}'.format(RECEIVER_PORT,html.escape(token))
                state['preview']=threading.Thread(target=preview,daemon=True)
                state['preview'].start()
            except Exception as error:
                status.value='启动失败：'+html.escape(str(error))
                with output:
                    print(traceback.format_exc())
                if server:
                    server.server_close()
                if engine:
                    try:
                        engine.close()
                    except Exception:
                        with output:
                            print(traceback.format_exc())
                state.update(engine=None,server=None)
            finally:
                state['starting']=False
        threading.Thread(target=worker,daemon=True).start()

    def on_stop(_):
        if state['engine']:
            state['engine'].stop('Jetson manual stop button')

    def on_close(_):
        if state['starting']:
            status.value='正在初始化，请等初始化完成后关闭。'
            return
        if not state['engine'] or state['closing']:
            return
        state['closing']=True
        engine,server=state['engine'],state['server']
        engine.stop('Jetson service close')
        def worker():
            try:
                server.shutdown();server.server_close()
                engine.close()
                state.update(engine=None,server=None)
                status.value='已关闭服务并释放相机、串口。'
                token_label.value=''
            except Exception as error:
                status.value='关闭失败：'+html.escape(str(error))
        threading.Thread(target=worker,daemon=True).start()

    start.on_click(on_start);stop.on_click(on_stop);close.on_click(on_close)
    display(widgets.VBox([widgets.HTML('<b>Week8 Jetson 手势选色抓取接收端</b>'),
                         widgets.HBox([start,stop,close]),token_label,status,camera,output]))
    state['close']=on_close
    return state
