"""Source-grounded PyBullet scene for the physical colour-block workspace.

The board dimensions, object height and arm-to-workspace transform come from
``arm5dof_python_uservo/config``.  Coordinates in the teaching notebooks are
arm-base coordinates in millimetres; PyBullet uses metres.
"""
from pathlib import Path
import math

import numpy as np
import pybullet as p


ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = ROOT / "arm5dof_python_uservo" / "config"
T_ARM2WS = np.loadtxt(REAL_CONFIG / "T_arm2ws.txt", delimiter=",")

# Actual calibration-board dimensions and visual-grasping object height.
BOARD_X_MM = 119.0
BOARD_Y_MM = 159.0
BLOCK_HEIGHT_MM = 28.0
BOARD_THICKNESS_M = 0.006


def arm_mm_to_world(position_mm):
    """The URDF base is the arm coordinate origin; convert mm to metres."""
    return [float(value) / 1000.0 for value in position_mm]


class RealWorkspaceScene:
    """Static scene built from the project's real calibration inputs."""

    def __init__(self):
        self.body_ids = []
        self.debug_ids = []
        self.active_block_id = None
        self.grasp_constraint_id = None
        self.pick_position_mm = None
        self.workspace_origin_mm = T_ARM2WS[:3, 3].copy()
        # T_arm2ws is nearly a planar rotation.  Preserve its measured yaw.
        self.workspace_yaw = math.atan2(T_ARM2WS[1, 0], T_ARM2WS[0, 0])

    def build(self, targets, pick_position):
        self._add_workspace_board()
        self._add_world_axes([0.0, 0.0, 0.0], "arm base", length=0.12)
        self._add_world_axes(arm_mm_to_world(self.workspace_origin_mm), "workspace", length=0.06)
        self._add_target_marker(pick_position, "pick", [0.95, 0.15, 0.95, 1.0])
        for name, position, color in targets:
            self._add_target_marker(position, name, color)
        self.pick_position_mm = list(pick_position)
        self.spawn_pick_block([0.9, 0.1, 0.1, 1.0])

    def configure_camera(self):
        # A useful oblique view of the arm and the calibrated board.
        target = arm_mm_to_world(self.workspace_origin_mm)
        p.resetDebugVisualizerCamera(
            cameraDistance=0.72,
            cameraYaw=45,
            cameraPitch=-38,
            cameraTargetPosition=target,
        )

    def _add_workspace_board(self):
        half = [BOARD_X_MM / 2000.0, BOARD_Y_MM / 2000.0, BOARD_THICKNESS_M / 2.0]
        collision = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
        visual = p.createVisualShape(
            p.GEOM_BOX, halfExtents=half, rgbaColor=[0.78, 0.68, 0.45, 1.0]
        )
        base = arm_mm_to_world(self.workspace_origin_mm)
        base[2] -= BOARD_THICKNESS_M / 2.0
        body = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=collision,
            baseVisualShapeIndex=visual,
            basePosition=base,
            baseOrientation=p.getQuaternionFromEuler([0.0, 0.0, self.workspace_yaw]),
        )
        self.body_ids.append(body)
        p.addUserDebugText(
            "calibrated workspace: 119 x 159 mm",
            arm_mm_to_world(self.workspace_origin_mm + np.array([0.0, 0.0, 8.0])),
            textColorRGB=[0.15, 0.12, 0.05],
            textSize=1.2,
        )

    def _add_target_marker(self, position_mm, label, rgba):
        center = arm_mm_to_world(position_mm)
        visual = p.createVisualShape(p.GEOM_SPHERE, radius=0.009, rgbaColor=rgba)
        body = p.createMultiBody(baseMass=0, baseVisualShapeIndex=visual, basePosition=center)
        self.body_ids.append(body)
        p.addUserDebugText(
            label,
            [center[0], center[1], center[2] + 0.018],
            textColorRGB=rgba[:3],
            textSize=1.15,
        )

    def spawn_pick_block(self, rgba):
        """Create one movable 28-mm block at the source region."""
        if self.active_block_id is not None:
            raise RuntimeError("A source block is already active")
        # The source code provides a pick tool point, not a measured cube centre.
        # Its XY is retained; its centre is placed on the calibrated board.
        position = arm_mm_to_world(self.pick_position_mm)
        position[2] = arm_mm_to_world(self.workspace_origin_mm)[2] + BLOCK_HEIGHT_MM / 2000.0
        half = [0.014, 0.014, BLOCK_HEIGHT_MM / 2000.0]
        collision = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
        visual = p.createVisualShape(p.GEOM_BOX, halfExtents=half, rgbaColor=rgba)
        body = p.createMultiBody(
            baseMass=0.015, baseCollisionShapeIndex=collision, baseVisualShapeIndex=visual, basePosition=position
        )
        p.changeDynamics(body, -1, lateralFriction=1.1, rollingFriction=0.0001)
        self.body_ids.append(body)
        self.active_block_id = body

    def grasp(self, arm):
        """Snap the active block to the actual tool frame and carry it by constraint."""
        if self.active_block_id is None:
            raise RuntimeError("No active block available to grasp")
        if self.grasp_constraint_id is not None:
            return
        tool_link = self._tool_link_index(arm.arm_id)
        tool_state = p.getLinkState(arm.arm_id, tool_link, computeForwardKinematics=True)
        tool_pos, tool_quat = tool_state[4], tool_state[5]
        p.resetBasePositionAndOrientation(self.active_block_id, tool_pos, tool_quat)
        p.resetBaseVelocity(self.active_block_id, [0, 0, 0], [0, 0, 0])
        self.grasp_constraint_id = p.createConstraint(
            arm.arm_id, tool_link, self.active_block_id, -1,
            p.JOINT_FIXED, [0, 0, 0], [0, 0, 0], [0, 0, 0],
        )
        p.changeConstraint(self.grasp_constraint_id, maxForce=300)

    def release(self, drop_position_mm):
        """Release the carried block at the original notebook's target point."""
        if self.active_block_id is None:
            return
        if self.grasp_constraint_id is not None:
            p.removeConstraint(self.grasp_constraint_id)
            self.grasp_constraint_id = None
        position = arm_mm_to_world(drop_position_mm)
        position[2] = max(position[2], BLOCK_HEIGHT_MM / 2000.0)
        p.resetBasePositionAndOrientation(self.active_block_id, position, [0, 0, 0, 1])
        p.resetBaseVelocity(self.active_block_id, [0, 0, 0], [0, 0, 0])
        self.active_block_id = None

    @staticmethod
    def _tool_link_index(arm_id):
        for index in range(p.getNumJoints(arm_id)):
            joint_name = p.getJointInfo(arm_id, index)[1].decode("utf-8")
            if joint_name == "tool_center_joint":
                return index
        raise RuntimeError("URDF does not contain tool_center_joint")

    def _add_world_axes(self, origin, label, length):
        origin = list(origin)
        axes = ([length, 0, 0], [0, length, 0], [0, 0, length])
        colors = ([1, 0, 0], [0, 1, 0], [0, 0, 1])
        for vector, color in zip(axes, colors):
            end = [origin[i] + vector[i] for i in range(3)]
            self.debug_ids.append(p.addUserDebugLine(origin, end, color, lineWidth=2.5))
        self.debug_ids.append(
            p.addUserDebugText(label, [origin[0], origin[1], origin[2] + 0.012], textColorRGB=[0, 0, 0], textSize=1.1)
        )
