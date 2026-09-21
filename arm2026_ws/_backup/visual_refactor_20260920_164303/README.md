# marm_description

ROS1 Noetic 课程机械臂描述包。模型使用基础几何体，不依赖外部 mesh。

## 模型

- 原模型：`urdf/marm.xacro`
- 课程修改版：`urdf/marm_course_variant.xacro`
- 原模型启动：`roslaunch marm_description view_marm.launch`
- 修改版启动：`roslaunch marm_description view_marm_course_variant.launch`

修改版仅将 `joint4` 的轴从 `1 0 0` 反转为 `-1 0 0`。原模型保持不变。

## 使用

```bash
source /opt/ros/noetic/setup.bash
source ~/arm2025_ws/devel/setup.bash
roslaunch marm_description view_marm.launch
```

实际模型包含 11 个 link、10 个 joint，其中 6 个 revolute、1 个 prismatic、3 个 fixed。完整结构见 `~/arm2025_ws/generated/model_structure.md`。
