# marm_description

ROS1 Noetic 课程机械臂描述包。模型使用基础几何体，不依赖外部 mesh。

当前视觉版采用多基础几何体组合：上臂、前臂和腕部改为箱式承力壳与外露纵向侧梁，圆柱只保留在关节端盖、轴承环和法兰。两根手指采用镜像的平行夹爪外观，每根都由滑块、白色导向段、蓝色指体、相向的橡胶夹持垫、青色细节条和小型紧固件组成；这只是 visual 外观，运动学、关节轴、限位和 collision 简化模型保持独立，便于教学和调试。

视觉设计参考了 Universal Robots、Franka、OpenMANIPULATOR 与 KUKA 开源 ROS 描述包常见的模块化外壳和工业配色，但没有复制或引入它们的 mesh 资产。

## 模型

- 原模型：`urdf/marm.xacro`
- 课程修改版：`urdf/marm_course_variant.xacro`
- 原模型启动：`roslaunch marm_description view_marm.launch`
- 修改版启动：`roslaunch marm_description view_marm_course_variant.launch`

课程修改版仅将 `joint4` 的轴从 `1 0 0` 反转为 `-1 0 0`；两份模型的最终视觉外观完全相同。

## 使用

```bash
source /opt/ros/noetic/setup.bash
source ~/arm2025_ws/devel/setup.bash
roslaunch marm_description view_marm.launch
```

实际模型包含 11 个 link、10 个 joint，其中 6 个 revolute、1 个 prismatic、3 个 fixed。视觉重构第一阶段将 10 个 visual 增至 42 个；平行夹爪二次外观重构后为 48 个；箱式主臂与腕部壳体重构后最终为 53 个 visual。完整结构见 `~/arm2025_ws/generated/model_structure.md`。

真实 URDF 离线渲染预览见 `~/arm2025_ws/report_assets/marm_visual_refactor_preview.png`，夹爪近景见 `~/arm2025_ws/report_assets/marm_gripper_parallel_jaw_detail.png`；两者均由展开 URDF 的 geometry、visual origin、material 与 FK 渲染，并非 RViz 截图。
