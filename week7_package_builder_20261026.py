"""Assemble a new Week 7 distribution without modifying the source folder."""
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

SOURCE = Path(r'D:\robot\5.目标识别(已修改)')
TARGET = Path(r'D:\robot\week7')
ARCHIVE = Path(r'D:\robot\week7.zip')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source, destination):
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if sha(source) != sha(destination):
        raise RuntimeError('Copy verification failed: '+str(source))


def main():
    if ARCHIVE.exists():
        raise FileExistsError(ARCHIVE)
    copied = []
    for name in ['app_usb.py','arm_interrupt.py','control.py','network_link.py',
                 'receiver_usb.py','recognition.py','test_usb.py','start_usb_gesture.bat']:
        source = SOURCE/'gesture_usb'/name
        copied.append((source, sha(source)))
        copy(source, TARGET/'gesture_usb'/name)
    copy(SOURCE/'models/gesture_recognizer.task', TARGET/'models/gesture_recognizer.task')
    for name in ['Ch7 手势识别与机械臂指令控制.pdf', '实验七  手势识别与机械臂指令控制.docx']:
        copy(SOURCE/name, TARGET/'materials'/name)
    for source in sorted((SOURCE/'gesture_usb/results').rglob('*')):
        if source.is_file() and source.suffix.lower() in ('.png','.jpg','.jpeg','.jsonl','.csv'):
            copy(source, TARGET/'gesture_usb/results'/source.relative_to(SOURCE/'gesture_usb/results'))

    records = TARGET/'records'
    records.mkdir()
    results = []
    for path in sorted((TARGET/'gesture_usb/results').glob('*/events.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('event') == 'result':
                reply = row.get('reply') or {}
                results.append(dict(时间=row.get('time',''), 指令=row.get('command',''),
                                    模式=reply.get('mode',''), 回执状态=reply.get('status',''),
                                    停止阶段=reply.get('stop_phase',''), 错误=row.get('error') or reply.get('error') or '',
                                    来源日志=str(path.relative_to(TARGET)).replace('\\','/'),
                                    实际手势='待人工补充', 现场实际动作='待人工补充', 人工成功判定='待人工判定'))
    with (records/'动作回执汇总.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    columns=['序号','测试时间','模式','实际手势序列','识别结果','预期指令','现场实际动作','成功或失败','误触发或未触发说明','截图或日志文件','备注']
    with (records/'随机手势测试记录模板.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream)
        writer.writerow(columns)
        for index in range(1,11):
            writer.writerow([index]+['']*(len(columns)-1))
    hardware=[row for row in results if row['模式']=='hardware']
    simulation=[row for row in results if row['模式']=='simulation']
    counts=Counter(row['指令'] for row in hardware if row['回执状态']=='done')
    images=list((TARGET/'gesture_usb/results').rglob('*.png'))
    overview='''# 现有记录概览

本页由源目录的事件日志和文件清单自动汇总。动作回执不等同于人工随机手势验收。

'''
    overview+=f'- 归档截图：{len(images)} 张。\n- 动作最终回执：{len(results)} 条，其中硬件模式 {len(hardware)} 条、接收端演练 {len(simulation)} 条。\n'
    overview+='- 硬件模式 done 分布：'+ '，'.join(f'{name} {count} 次' for name,count in sorted(counts.items()))+'。\n'
    overview+='- 最终回执 interrupted：'+str(sum(row['回执状态']=='interrupted' for row in results))+' 条。\n'
    overview+='''
## 可以写入报告的事实

日志记录了真机模式下接收端返回的动作结果，可说明当时本机到接收服务、SDK 动作流程的运行情况。具体时间和指令见同目录的“动作回执汇总.csv”。截图可用于展示当时的手势识别画面，应逐张查看后选用。

## 不能从这些记录直接得出的结论

目前没有找到识别测试 CSV 或逐轮指令测试 CSV。日志未逐轮记录人工真实手势、预期动作、观察到的机械臂动作、随机性或全部失败尝试，因而不能据此计算真实随机手势正确率，也不能把 done 次数写成“全部正确”。

当前汇总没有动作最终返回 interrupted 的证据。因此 Five 的动作中断表现、真实制停延迟和停止后的机械运动状态仍需现场测试或补充其他真实证据。静态 Five 截图以及发送 stop 的日志不单独证明运动已停止。

“动作回执汇总.csv”中的人工字段为待填写项；空白的“随机手势测试记录模板.csv”不是已经完成的测试数据。
'''
    (records/'现有记录概览.md').write_text(overview,encoding='utf-8')

    verification=TARGET/'verification'
    verification.mkdir()
    process=subprocess.run([sys.executable,str(TARGET/'gesture_usb/test_usb.py')],cwd=TARGET,
                           capture_output=True,text=True,encoding='utf-8',errors='replace')
    report='打包验证时间：'+datetime.now().isoformat(timespec='seconds')+'\nPython：'+sys.version+'\n\n'
    report+=process.stdout+process.stderr+'\n退出码：'+str(process.returncode)+'\n'
    report+='\n该测试使用模拟机械臂和本机回环 HTTP，不代表真实手势准确率或机械臂急停验收。\n'
    (verification/'自动测试结果.txt').write_text(report,encoding='utf-8')
    if process.returncode:
        raise RuntimeError('Packaged tests failed; see verification output')
    # Compile without writing pyc files or touching the source directory.
    for path in TARGET.rglob('*.py'):
        compile(path.read_text(encoding='utf-8'),str(path),'exec')
    for source, original_hash in copied:
        if sha(source)!=original_hash:
            raise RuntimeError('Source changed while packaging: '+str(source))
    files=[path for path in TARGET.rglob('*') if path.is_file() and '__pycache__' not in path.parts]
    (TARGET/'SHA256SUMS.txt').write_text('\n'.join(sha(path)+'  '+path.relative_to(TARGET).as_posix()
                                               for path in sorted(files))+'\n',encoding='utf-8')
    files=[path for path in TARGET.rglob('*') if path.is_file() and '__pycache__' not in path.parts]
    with zipfile.ZipFile(ARCHIVE,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path,arcname='week7/'+path.relative_to(TARGET).as_posix())
    with zipfile.ZipFile(ARCHIVE) as archive:
        bad=archive.testzip()
        if bad:
            raise RuntimeError('ZIP CRC failed: '+bad)
        for path in files:
            name='week7/'+path.relative_to(TARGET).as_posix()
            if hashlib.sha256(archive.read(name)).hexdigest()!=sha(path):
                raise RuntimeError('ZIP hash mismatch: '+name)
    print(json.dumps(dict(archive=str(ARCHIVE),files=len(files),size_mb=round(ARCHIVE.stat().st_size/1024**2,2),
                          hardware_receipts=len(hardware),hardware_done_by_command=counts,
                          simulation_receipts=len(simulation),screenshots=len(images),tests='passed'),ensure_ascii=False))


if __name__=='__main__':
    main()
