# Report Asset Checklist

`04_marm_link_joint_tree.png` is a real Graphviz rendering of `generated/marm.gv`; it is not a fabricated screenshot.

## Evidence status

| Required evidence | Status | Suggested filename |
|---|---|---|
| RViz complete original model | Manual screenshot required | `01_rviz_original.png` |
| joint_state_publisher_gui joint1-joint6 | Verified live; manual screenshot required | `02_joint_gui.png` |
| RViz TF axes | Verified enabled; manual screenshot required | `03_rviz_tf.png` |
| Link/Joint tree | Available | `04_marm_link_joint_tree.png` |
| Model before modification | Manual screenshot required | `05_before_variant.png` |
| Model after modification | Manual screenshot required | `06_after_variant.png` |
| Source diff | Text evidence available | `../generated/variant.diff` |
| check_urdf output | Text evidence available | `../generated/check_urdf.log`, `../generated/check_urdf_variant.log` |
| catkin_make output | Text evidence available | `../generated/catkin_make.log` |
| joint_states output | Verified live; copy terminal output manually if a screenshot is required | `10_joint_states.png` |

The WSLg OpenGL viewport appeared black to the capture interface even though RViz Global Status and RobotModel were green. Capture items 1, 3, 5 and 6 directly from the Jetson desktop or NoMachine session.
