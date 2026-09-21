# RViz and ROS Runtime Validation

## Environment

- Host: Windows 11 x64
- Runtime: WSL2 Ubuntu 20.04.6 LTS, ROS1 Noetic
- Display: `:0` through WSLg
- Fixed frame: `base_link`
- End frame used for TF validation: `grasping_frame`

## Original model

- `roslaunch marm_description view_marm.launch`: started successfully.
- Nodes observed: `/joint_state_publisher_gui`, `/robot_state_publisher`, `/rviz`, `/rosout`.
- Topics observed: `/joint_states`, `/tf`, `/tf_static` and RViz interaction topics.
- GUI exposed `joint1` through `joint6` plus `finger_joint1`.
- Zero-pose TF `base_link -> grasping_frame`: translation approximately `[0, 0, 0.610]`, RPY approximately `[3.142, -1.571, 0]` radians.
- After GUI Randomize, `/joint_states` contained seven non-zero/updated positions and the end TF changed to approximately `[-0.030, -0.100, -0.078]`, proving the GUI-to-TF runtime chain responded.

## Course variant

- `roslaunch marm_description view_marm_course_variant.launch`: started successfully.
- Runtime `/robot_description` reported `joint4 axis=-1 0 0`.
- The same four ROS nodes, seven movable joints and root-to-end TF were present.
- `check_urdf` passed for the generated variant.

## Checklist

| Item | Result | Evidence or limitation |
|---|---|---|
| RViz process starts | Pass | `/rviz` node and window observed |
| Fixed Frame | Pass | `base_link`, RViz Global Status OK |
| RobotModel loaded | Pass at ROS/RViz status level | RobotModel enabled with green status |
| Complete rendered geometry visible | Not independently captured | WSLg/OpenGL viewport is black in the capture interface |
| Mesh paths | Not applicable | Model uses box/cylinder primitives, no mesh URI |
| joint1-joint6 in GUI | Pass | All six controls observed; GUI reports seven movable joints including gripper |
| Slider/model response | Pass | Randomize changed `/joint_states` and end TF |
| TF tree | Pass | `base_link -> grasping_frame` repeatedly returned transforms |
| TF display enabled in RViz | Pass during live session | TF checkbox was enabled and remained error-free |
| Physical-direction agreement | Not tested | Physical arm control was prohibited |
| Before/after visible screenshots | Manual capture required | OpenGL viewport was not capturable in this environment |

No serial port, GPIO, servo command or physical-arm program was used.
