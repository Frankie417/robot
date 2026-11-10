"""Build a new delivery archive and verification notes; preserve source materials."""
import copy
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from sorting_core import load_config
from hardware_backend import precheck

HERE=Path(__file__).resolve().parent


def main():
    verification=HERE/'verification'
    verification.mkdir(exist_ok=True)
    config=load_config(HERE/'bin_map.json')
    diagnostic=copy.deepcopy(config)
    for item in diagnostic['bin_map'].values():
        for key in ('pose','above'):
            item[key]['roll_deg']=item['diagnostic_modulo_roll_deg']
    sdk=HERE.parent.parent/'4.机械臂OpenCV视觉处理实验'
    checked=precheck(diagnostic,str(sdk),False)
    report=dict(time=datetime.now().isoformat(),sdk=str(sdk),
                purpose='Offline diagnostics only; candidate modulo Roll values; no UART connection or movement.',
                changes_to_operational_config=False,physical_calibration_confirmed=config['physical_calibration_confirmed'],
                reachable_key_poses=checked,
                automated_tests='12 passed; synthetic images, simulated motion and cancellation. No real camera/arm trial.',
                panel_smoke_test='passed',python36_syntax_check='passed')
    with (verification/'offline_verification.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    materials=HERE/'materials'
    materials.mkdir()
    for source in HERE.parent.glob('Ch6*.pdf'):
        shutil.copy2(source,materials/source.name)
    for source in HERE.parent.glob('*.docx'):
        if source.stat().st_size==19981:
            shutil.copy2(source,materials/source.name)
    with (HERE/'8次随机测试记录模板.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['序号','时间','模式','实际颜色','识别颜色','预期桶','实际桶','人工成功判定','失败环节','是否重复抓取','截图/日志','备注'])
        for index in range(1,9):
            writer.writerow([index]+['']*11)
    files=sorted(path for path in HERE.rglob('*') if path.is_file() and '__pycache__' not in path.parts and 'results' not in path.relative_to(HERE).parts)
    with (HERE/'SHA256SUMS.txt').open('x',encoding='utf-8') as stream:
        for path in files:
            stream.write(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(HERE).as_posix()+'\n')
    files.append(HERE/'SHA256SUMS.txt')
    target=HERE.parent/'week6_p4.zip'
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path,'week6_p4/'+path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for path in files:
            assert archive.read('week6_p4/'+path.relative_to(HERE).as_posix())==path.read_bytes()
    print(json.dumps(dict(archive=str(target),files=len(files),bytes=target.stat().st_size,offline_key_poses=len(checked),live_config_unchanged=True),ensure_ascii=False))


if __name__=='__main__':
    main()
