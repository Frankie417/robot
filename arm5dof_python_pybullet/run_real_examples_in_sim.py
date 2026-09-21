"""PyBullet versions of the teaching notebooks in ``2.机械臂实验``.

The sequences intentionally preserve the original target poses.  They do not
use serial ports or a physical arm.  ``transport`` visualizes the arm path and
gripper commands; it does not yet model a grasped colour block.
"""
import argparse
import time

import numpy as np
import pybullet as p

from arm5dof_pybullet import Arm5DoFPyBullet
from real_scene import RealWorkspaceScene


HOME = ([150.0, 0.0, 200.0], None, np.pi)
# The original notebook used Roll=91.6 degrees at the source point.  In the
# URDF that leaves the jaws partly vertical.  Rotate the wrist into the same
# horizontal left/right pinch orientation used at the four drop points.
HORIZONTAL_GRIPPER_ROLL = np.radians(179.2)
PICK = ([217.0, 16.1, 9.2], np.radians(138.4), HORIZONTAL_GRIPPER_ROLL)
DROP_POINTS = [
    ([120.0, 134.0, 20.0], np.radians(140.0), np.radians(179.2)),
    ([220.0, 135.0, 30.0], np.radians(125.0), np.radians(179.2)),
    ([110.0, -136.0, 20.0], np.radians(140.0), np.radians(179.2)),
    ([205.0, -145.0, 30.0], np.radians(135.0), np.radians(179.2)),
]
TRANSIT_POINTS = [
    ([141.6, 76.2, 110.0], np.radians(125.0), np.radians(179.2)),
    ([220.0, 125.0, 80.0], np.radians(125.0), np.radians(179.2)),
    ([110.0, -136.0, 50.0], np.radians(140.0), np.radians(179.2)),
    ([205.0, -145.0, 60.0], np.radians(130.0), np.radians(179.2)),
]
SCENE_TARGETS = [
    ("green drop", DROP_POINTS[0][0], [0.1, 0.8, 0.1, 1.0]),
    ("yellow drop", DROP_POINTS[1][0], [0.95, 0.8, 0.05, 1.0]),
    ("red drop", DROP_POINTS[2][0], [0.9, 0.1, 0.1, 1.0]),
    ("blue drop", DROP_POINTS[3][0], [0.1, 0.3, 0.95, 1.0]),
]


def move(arm, pose, seconds=0.35):
    position, pitch, roll = pose
    corrected = arm.adjust_tool_posi(position)
    ok, _ = arm.inverse_kinematic(corrected, pitch if pitch is not None else arm.auto_gen_pitch(corrected), roll)
    if not ok:
        raise RuntimeError(f"Unreachable pose: {pose}")
    arm.set_tool_pose(position, tool_pitch=pitch, tool_roll=roll, T=seconds)
    # set_tool_pose already runs the minimum-jerk trajectory.  The former
    # second wait could block for ten seconds at every waypoint.
    time.sleep(0.05)


def go_home(arm):
    move(arm, HOME, seconds=0.5)


def dance(arm):
    """Copied from 03.机械臂舞蹈表演: four poses and gripper beats."""
    poses = [
        ([180.0, -50.0, 100.0], np.radians(110.0), np.radians(180.0)),
        ([180.0, 50.0, 100.0], np.radians(110.0), np.radians(180.0)),
        ([180.0, -50.0, 110.0], np.radians(110.0), np.radians(180.0)),
        ([180.0, 50.0, 110.0], np.radians(110.0), np.radians(180.0)),
    ]
    go_home(arm)
    for index, pose in enumerate(poses):
        move(arm, pose)
        for _ in range(2 + (index % 2)):
            arm.gripper_open(T=0.25)
            arm.gripper_close(T=0.25)
        arm.gripper_open(T=0.25)
        if index == 1:
            go_home(arm)
    go_home(arm)


def transport(arm, scene):
    """Copied from 04.机械臂定点搬运色块, as an arm-trajectory demo."""
    go_home(arm)
    for index, (transit, drop) in enumerate(zip(TRANSIT_POINTS, DROP_POINTS)):
        if index > 0:
            scene.spawn_pick_block(SCENE_TARGETS[index][2])
        arm.gripper_open(T=0.12)
        move(arm, PICK)
        arm.gripper_close(T=0.12)
        scene.grasp(arm)
        go_home(arm)
        move(arm, transit)
        move(arm, drop)
        arm.gripper_open(T=0.12)
        scene.release(drop[0])
        go_home(arm)
        arm.gripper_close(T=0.12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("demo", choices=("dance", "transport"))
    parser.add_argument("--headless", action="store_true", help="run without the PyBullet window")
    parser.add_argument("--hold", type=float, default=30.0, help="seconds to keep the GUI open after completion")
    args = parser.parse_args()

    gui = not args.headless
    arm = Arm5DoFPyBullet(connection_mode=p.GUI if gui else p.DIRECT)
    scene = RealWorkspaceScene()
    scene.build(SCENE_TARGETS, PICK[0])
    if gui:
        scene.configure_camera()
    try:
        if args.demo == "dance":
            dance(arm)
        else:
            transport(arm, scene)
        pose = arm.get_tool_pose()
        print("completed", args.demo, "final_tool_pose=", np.round(pose, 3).tolist())
        if gui and args.hold > 0:
            time.sleep(args.hold)
    finally:
        arm.close()


if __name__ == "__main__":
    main()
