# Model Structure

- Source: `/home/cubertzk/arm2025_ws/generated/marm.urdf`
- Robot name: `marm`
- Root link(s): `base_link`
- Link count: **11**
- Joint count: **10**
- Visual element count: **48**
- Collision element count: **9**
- Joint types: `fixed` = 3, `prismatic` = 1, `revolute` = 6
- Single connected tree: **yes**
- Cycle detected: **no** (confirmed by `check_urdf`)
- Isolated/unreachable links: **none**

| Joint | Type | Parent | Child | Origin xyz | Origin rpy | Axis xyz | Lower | Upper | Effort | Velocity |
|---|---|---|---|---|---|---|---|---|---|---|
| base_joint | fixed | base_link | link0 | 0 0 0.02 | 0 0 0 | — | — | — | — | — |
| joint1 | revolute | link0 | link1 | 0 0 0.02 | 0 1.570795 0 | -1 0 0 | -3.14159 | 3.14159 | 300 | 1 |
| joint2 | revolute | link1 | link2 | -0.1 0 0.0 | -1.570795 0 1.570795 | 1 0 0 | -3.14159 | 3.14159 | 300 | 1 |
| joint3 | revolute | link2 | link3 | 0 0 0.14 | 0 3.14159 0 | -1 0 0 | -3.14159 | 3.14159 | 300 | 1 |
| joint4 | revolute | link3 | link4 | 0.0 0.0 -0.15 | 0 1.570795 3.14159 | 1 0 0 | -3.14159 | 3.14159 | 300 | 1 |
| joint5 | revolute | link4 | link5 | 0.06 0.0 0.0 | 0 1.570795 0 | 1 0 0 | -3.14159 | 3.14159 | 300 | 1 |
| joint6 | revolute | link5 | link6 | 0 0 0.06 | 4.712384999999999 -1.570795 0 | 1 0 0 | -6.28318 | 6.28318 | 300 | 1 |
| finger_joint1 | prismatic | link6 | gripper_finger_link1 | 0.02 -0.03 0 | 0 0 0 | 0 1 0 | 0 | 0.06 | 100 | 0.02 |
| finger_joint2 | fixed | link6 | gripper_finger_link2 | 0.02 0.03 0 | 0 0 0 | — | — | — | — | — |
| grasping_frame_joint | fixed | link6 | grasping_frame | 0.06 0 0 | 0 0 0 | — | — | — | — | — |

## Link names

`base_link`, `link0`, `link1`, `link2`, `link3`, `link4`, `link5`, `link6`, `gripper_finger_link1`, `gripper_finger_link2`, `grasping_frame`
