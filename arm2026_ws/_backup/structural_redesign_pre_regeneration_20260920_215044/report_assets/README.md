# Report Asset Checklist

`04_marm_link_joint_tree.png` is a real Graphviz rendering of `generated/marm.gv`; it is not a fabricated screenshot.

`marm_visual_refactor_preview.png` and `marm_gripper_parallel_jaw_detail.png` are real offline renders parsed from the expanded `marm.xacro` URDF. They use the model's link/joint transforms, visual origins, boxes/cylinders and named materials; they are evidence of the model geometry, not RViz screenshots.

## Evidence status

| Required evidence | Status | Suggested filename |
|---|---|---|
| RViz complete original model | Manual screenshot required | `01_rviz_original.png` |
| Visual-refactor overview | Available, real offline URDF render | `marm_visual_refactor_preview.png` |
| Parallel-jaw gripper close-up | Available, real offline URDF render | `marm_gripper_parallel_jaw_detail.png` |
| joint_state_publisher_gui joint1-joint6 | Verified live; manual screenshot required | `02_joint_gui.png` |
| RViz TF axes | Verified enabled; manual screenshot required | `03_rviz_tf.png` |
| Link/Joint tree | Available | `04_marm_link_joint_tree.png` |
| Model before modification | Manual screenshot required | `05_before_variant.png` |
| Model after modification | Manual screenshot required | `06_after_variant.png` |
| Source diff | Text evidence available | `../generated/variant.diff` |
| check_urdf output | Text evidence available | `../generated/check_urdf.log`, `../generated/check_urdf_variant.log` |
| catkin_make output | Text evidence available | `../generated/catkin_make.log` |
| joint_states output | Verified live; copy terminal output manually if a screenshot is required | `10_joint_states.png` |

The WSLg OpenGL viewport appeared black to the capture interface. The offline URDF images above are deliberately labeled separately and do not substitute for RViz screenshots. Capture items 1, 3, 5 and 6 directly from the Jetson desktop or NoMachine session.
