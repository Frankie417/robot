# marm_description

ROS1 Noetic 课程机械臂描述包。模型使用基础几何体，不依赖外部 mesh。

当前视觉版采用多基础几何体组合：分段式关节罩、端环、侧板、腕部法兰、夹爪掌部与防滑指尖。运动学、关节轴、限位和 collision 简化模型保持独立，便于教学和调试。

视觉设计参考了 Universal Robots、Franka、OpenMANIPULATOR 与 KUKA 开源 ROS 描述包常见的模块化外壳和工业配色，但没有复制或引入它们的 mesh 资产。

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
