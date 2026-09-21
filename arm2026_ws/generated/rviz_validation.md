# RViz and ROS Runtime Validation

## Final visual-refactor run

- Runtime: WSL2 Ubuntu 20.04 / ROS1 Noetic / WSLg (`DISPLAY=:0`).
- Started with `roslaunch marm_description view_marm.launch`; `roslaunch --nodes` listed `/joint_state_publisher_gui`, `/robot_state_publisher` and `/rviz`.
- Final live nodes were `/joint_state_publisher_gui`, `/robot_state_publisher`, `/rviz` and `/rosout`; topics included `/joint_states`, `/tf` and `/tf_static`.
- The structural-silhouette rebuild parsed as **11 links, 10 joints, 53 visual elements and 9 collision elements**; the live session is restarted from this rebuilt model.
- `/joint_state_publisher_gui` was confirmed to publish `/joint_states`. The final sampled message contained `joint1` through `joint6` and `finger_joint1`; the end-frame TF was available from `base_link` to `grasping_frame`.

## TF motion-chain evidence

- This run initially sampled the GUI at zero state and observed `base_link -> grasping_frame` near translation `[0, 0, 0.610]` with RPY `[3.142, -1.571, 0]`.
- To avoid competing publishers during an automated, no-hardware test, the GUI node was temporarily stopped. A short-lived `rospy` publisher waited for `robot_state_publisher` and sent a timestamped, in-limit `JointState` (`joint1..joint6 = [0.35, -0.70, 0.95, -0.45, 0.55, 0.25]`, `finger_joint1 = 0.025`). The resulting TF was translation `[-0.073, 0.002, 0.564]`, RPY `[0.578, -1.230, 2.744]`, so it changed from zero pose.
- The complete `view_marm.launch` group was then restarted. GUI, state publisher and RViz are running again. The final live GUI-published sample and its end TF were non-zero, demonstrating the active GUI-to-topic-to-TF path; no GUI slider was clicked programmatically.

## Limits and manual evidence

| Item | Result | Evidence or limitation |
|---|---|---|
| RViz process / node starts | Pass | `/rviz` process and node are live |
| GUI / state publisher / joint topic | Pass | all three live; GUI is `/joint_states` publisher |
| Root-to-end TF | Pass | `base_link -> grasping_frame` returned in zero and moved test states |
| Dynamic joint-to-TF chain | Pass | timestamped `rospy` test changed end TF as recorded above |
| Visual geometry | Static pass | 53 visuals in the rebuilt model; no mesh URI used |
| RViz viewport screenshot | Manual step remains | WSLg OpenGL viewport is black to this capture interface |
| Manual slider sweep | Manual step remains | move `joint1`..`joint6` in the visible GUI and capture the RViz viewport if a GUI-specific screenshot is required |
| Physical arm agreement | Not tested | no serial, GPIO, servo or physical-arm action was used |
