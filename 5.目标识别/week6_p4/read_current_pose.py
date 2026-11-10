"""Read teaching pose only. Does not send motion, Home, open or damping commands."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import threading
from arm_interrupt import InterruptibleArm


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-dir',required=True,type=Path)
    parser.add_argument('--arm-port',default='/dev/ttyTHS1')
    parser.add_argument('--label',required=True,help='p4_pick / p4_above / green / yellow / blue / red / green_above etc.')
    args=parser.parse_args()
    robot=InterruptibleArm(args.sdk_dir,args.arm_port,threading.Event())
    try:
        x,y,z,pitch,roll=[float(v) for v in robot.arm.get_tool_pose()]
        if not all(math.isfinite(v) for v in (x,y,z,pitch,roll)):
            raise ValueError('Invalid forward-kinematic pose')
        fk=dict(x=x,y=y,z=z,pitch_deg=math.degrees(pitch),roll_deg=math.degrees(roll))
        k,b=robot.arm.z_error_polyfit
        command=dict(fk,z=z-float(k)*math.hypot(x,y)-float(b))
        report=dict(label=args.label,time=datetime.now().isoformat(),
                    fk_pose_mm_deg=fk,command_pose_mm_deg=command,
                    explanation='SDK FK angles are radians: converted exactly once. command_pose compensates SDK Z correction so set_tool_pose does not apply it twice.')
        output=Path(__file__).resolve().parent/'results'
        output.mkdir(exist_ok=True)
        target=output/('taught_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        print('Saved:',target)
    finally:
        robot.close()


if __name__=='__main__':
    main()
