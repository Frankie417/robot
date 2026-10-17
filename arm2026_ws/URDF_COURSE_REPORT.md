# 1. 实验目标

在 ROS1 中导入并验证 `marm_description`，掌握 Xacro/URDF 的 link、joint、parent/child、origin、axis、limit，完成编译、结构检查、Graphviz 图、RViz/TF 运行验证及一次可回滚的单参数修改。

本次在不改变运动学、碰撞或惯性语义的前提下重构了视觉层：第一阶段将 10 个 visual 部件扩展为 42 个；之后将原先像插座的夹爪替换为镜像的工业平行两指夹爪；再将上臂、前臂和腕部由圆管主体改为箱式承力壳与外露侧梁；最后参考 Unitree Z1 的模块化关节壳、端环和法兰层次，当前为 68 个 visual 部件。整个模型仍只使用 box、cylinder 等基础几何体，没有在本模型中引入外部 STL/DAE。

# 2. 实验环境

| 项目 | 实际结果 |
|---|---|
| 宿主系统 | Windows 11 家庭中文版，x64，Build 26200 |
| Linux | WSL2 Ubuntu 20.04.6 LTS，x86_64 |
| ROS | ROS1 Noetic 1.17.4 |
| Python | 3.8.10 |
| 工作空间 | `/home/cubertzk/arm2026_ws` |
| DISPLAY | `:0` |
| 说明 | 当前不是 Jetson Nano ARM 环境，需在学校设备复核截图与性能 |

# 3. 工作空间与功能包结构

课程 ZIP 的 SHA-256 为 `6111A01BCDD3B6A38640541FE7EB735ABE44BFDBBDF6865A024750CCC705A0F2`。包被复制到 `~/arm2026_ws/src/marm_description`，`src` 下仅有一份同名包，原 ZIP 未修改。

主要文件：

```text
~/arm2026_ws/src/marm_description/
├── CMakeLists.txt
├── package.xml
├── README.md
├── launch/
│   ├── view_marm.launch
│   └── view_marm_course_variant.launch
├── urdf/
│   ├── marm.xacro
│   └── marm_course_variant.xacro
└── urdf.rviz
```

# 4. URDF/Xacro 核心概念

- Link：刚性部件。本模型实例包括 `base_link`、`link0` 到 `link6`、两个夹爪 link 和 `grasping_frame`。
- Joint：连接 parent 与 child 的运动约束，例如 `joint4` 连接 `link3` 与 `link4`。
- parent/child：决定树的有向连接关系，形式为 `parent link -> joint -> child link`。
- `origin xyz`：joint 坐标系相对 parent 的平移。
- `origin rpy`：joint 坐标系相对 parent 的 Roll/Pitch/Yaw 旋转，单位为弧度。
- `axis`：在 joint 坐标系中定义旋转轴或移动轴。
- `limit`：为 revolute/prismatic joint 定义 lower、upper、effort、velocity。

# 5. Link/Joint 连接关系

实际根 link 是 `base_link`。主链为：

```text
base_link -> link0 -> link1 -> link2 -> link3 -> link4 -> link5 -> link6
```

`link6` 再分叉到 `gripper_finger_link1`、`gripper_finger_link2` 和 `grasping_frame`。工具统计结果为 11 links、10 joints，而不是课程目标中的 7/6；其中有 6 revolute、1 prismatic、3 fixed。模型是单棵连通树，无环、无孤立 link。完整逐关节表见 `generated/model_structure.md`。

# 6. origin、axis、limit 说明

以原模型 `joint4` 为例：

| 字段 | 实际值 |
|---|---|
| Type | `revolute` |
| Parent | `link3` |
| Child | `link4` |
| Origin xyz | `0.0 0.0 -0.15` |
| Origin rpy | `0 1.570795 3.14159`（转换后） |
| Axis | `1 0 0` |
| Lower / Upper | `-3.14159 / 3.14159` |
| Effort / Velocity | `300 / 1` |

正角度按右手定则绕 joint 坐标系的 +X 轴旋转。修改版将轴反转为 -X，因此相同正角度的旋转方向相反，但关节位置、parent/child 与 limit 不变。

# 7. 编译与启动步骤

```bash
source /opt/ros/noetic/setup.bash
cd ~/arm2026_ws
catkin_make
source ~/arm2026_ws/devel/setup.bash
roslaunch marm_description view_marm.launch
```

本次 `catkin_make` 返回 0，`rospack find marm_description` 返回 `/home/cubertzk/arm2026_ws/src/marm_description`。

# 8. Xacro 转 URDF 与 check_urdf

```bash
xacro ~/arm2026_ws/src/marm_description/urdf/marm.xacro \
  -o ~/arm2026_ws/generated/marm.urdf
check_urdf ~/arm2026_ws/generated/marm.urdf
```

最终主模型与课程修改版都通过 `check_urdf`，根 link 均为 `base_link`。当前计数为 11 links、10 joints、68 visuals、9 collisions；详见 `generated/check_urdf*.log` 与 `generated/model_structure.md`。

# 9. urdf_to_graphiz 结构图

```bash
cd ~/arm2026_ws/generated
urdf_to_graphiz marm.urdf
```

已生成 `marm.gv` 和 `marm.pdf`。Graphviz 同源 PNG 已目视检查，连接连续且分叉正确，保存于 `report_assets/04_marm_link_joint_tree.png`。

# 10. RViz 与 joint_state_publisher_gui 验证

最终主模型成功启动 `/joint_state_publisher_gui`、`/robot_state_publisher`、`/rviz` 和 `/rosout`，并实际存在 `/joint_states`、`/tf` 与 `/tf_static`。GUI 发布 `joint1` 到 `joint6` 以及 `finger_joint1`。为避免两个发布器竞争，自动动态验证时短暂关闭 GUI，再使用一个仅发布 ROS 话题的、带时间戳的 `rospy` `JointState`；末端 TF 从零位变化，随后完整 launch 已重新启动并恢复 GUI。详见 `generated/rviz_validation.md`。

RViz 配置的 Fixed Frame 为 `base_link`，且 `/rviz` 进程已实际启动。由于 WSLg 的 OpenGL 视口在捕获接口中呈黑色，本次不把无法读取的视口状态宣称为截图验证；完整模型、TF 轴及修改前后方向仍需在 Jetson 本地桌面或 NoMachine 中补拍，不能伪造截图。

# 11. TF 坐标系验证

零位时 `base_link -> grasping_frame` 的实测 TF 约为：

```text
translation: [0.000, 0.000, 0.610]
RPY rad: [3.142, -1.571, 0.000]
```

本次自动动态验证以安全的 ROS 话题发布方式发送带时间戳的、限位内关节状态，末端平移变为约 `[-0.073, 0.002, 0.564]`，证明 `/joint_states`、robot_state_publisher 与 TF 链路正常；验证后已重新启动完整 GUI/RViz 组。

# 12. 指定参数修改与现象解释

主模型与课程修改版同步了完全相同的视觉重构；视觉层之外没有变化。课程修改版仍只包含一项模型语义变化：

```diff
-        <axis xyz="1 0 0" />
+        <axis xyz="-1 0 0" />
```

语义对比程序确认只有 `joint4.axis` 不同；两版仍为 11 links/10 joints，修改版重新转换并通过 `check_urdf`。预期现象是轴所在直线不变，相同正角度绕相反方向旋转，后续 link 的 TF 随之改变；parent/child、origin、limit 和几何体均不变。OpenGL 视口截图限制使“同角度前后画面”尚需人工补证。

# 13. 课后作业

| 项目 | 内容 |
|---|---|
| Joint 名称 | `joint4` |
| Joint 类型 | `revolute` |
| Parent Link | `link3` |
| Child Link | `link4` |
| Origin xyz | `0.0 0.0 -0.15` |
| Origin rpy | `0 1.570795 3.14159` |
| Axis xyz | 原版 `1 0 0`；修改版 `-1 0 0` |
| 正方向判断 | 按对应轴向使用右手定则；反转 axis 后正方向反转 |
| Lower / Upper | `-3.14159 / 3.14159` |
| Effort / Velocity | `300 / 1` |

若 axis 错误，关节可能绕错误轴运动、正方向与实物相反、后续 TF 方向错误、模型互相穿插，并导致正逆运动学语义与实物不一致。

# 14. 问题与解决方法

1. ROS 工具最初不可见：仅在当前 shell 中 source `/opt/ros/noetic/setup.bash`，未修改 `.bashrc`。
2. 首次阶段 2 脚本使用 `set -u` 与 ROS 环境脚本冲突：写入前即停止，去掉 nounset 后重试。
3. 修改版首次补丁误命中 `joint2`：diff 在转换前发现；先备份错误副本，再恢复 joint2 并精确修改 joint4。
4. WSL 缺少 Poppler：未使用 sudo 安装；通过 Graphviz 同源 PNG 检查结构图，并保留 PDF 文件类型证据。
5. WSLg/OpenGL 画面无法由捕获接口读取：仅报告 RViz 状态、ROS topic/TF 与 GUI 证据，要求在 Jetson 桌面补拍。
6. 独立 TF 对比发布器没有形成动态 TF：失败日志移入 `_backup/failed_tf_comparison_*`，未把失败结果冒充成功；实际 GUI 动态链路已通过。

# 15. 视觉重构与夹爪设计

视觉设计吸收了 Universal Robots 的清晰模块化分段、Franka 的深浅双色圆润壳体、OpenMANIPULATOR 的紧凑关节和 KUKA 的工业高可见性点缀等公开 ROS 描述包的设计语言；未复制它们的 mesh 或资产。

- 底座、肩部、上臂、前臂和腕部使用石墨黑、枪灰、珠光白、铝灰和海洋蓝形成主层次；青色、橙色和黄色只作为识别条或紧固件点缀。
- 上臂、前臂与腕部的主体 visual 已改为方形/矩形承力壳，增加可见侧梁；圆柱只作为旋转端盖、轴承环和法兰，因此外部轮廓不再是简单圆管。
- 夹爪为真实关节原点下的镜像两指视觉：滑块、导向段、指体和相向橡胶垫构成平行夹爪，且没有改动两条 finger joint 或碰撞盒。
- 真实离线 URDF 总览位于 `report_assets/marm_visual_refactor_preview.png`，夹爪近景位于 `report_assets/marm_gripper_parallel_jaw_detail.png`。它们是从展开 URDF 的 visual geometry、origin、material 和 FK 生成，不是伪造的 RViz 截图。

# 16. 最终提交文件清单

- `~/arm2026_ws/URDF_COURSE_REPORT.md`
- `~/arm2026_ws/src/marm_description/README.md`
- `~/arm2026_ws/src/marm_description/urdf/marm.xacro`
- `~/arm2026_ws/src/marm_description/urdf/marm_course_variant.xacro`
- `~/arm2026_ws/src/marm_description/launch/view_marm.launch`
- `~/arm2026_ws/src/marm_description/launch/view_marm_course_variant.launch`
- `~/arm2026_ws/generated/marm.urdf`
- `~/arm2026_ws/generated/marm_course_variant.urdf`
- `~/arm2026_ws/generated/model_structure.md`
- `~/arm2026_ws/generated/marm.gv`
- `~/arm2026_ws/generated/marm.pdf`
- `~/arm2026_ws/generated/variant.diff`
- `~/arm2026_ws/generated/visual_refactor_invariants.md`
- `~/arm2026_ws/generated/rviz_validation.md`
- `~/arm2026_ws/generated/catkin_make.log`
- `~/arm2026_ws/generated/check_urdf.log`
- `~/arm2026_ws/generated/check_urdf_variant.log`
- `~/arm2026_ws/report_assets/README.md`
- `~/arm2026_ws/report_assets/04_marm_link_joint_tree.png`
- `~/arm2026_ws/report_assets/marm_visual_refactor_preview.png`
- `~/arm2026_ws/report_assets/marm_gripper_parallel_jaw_detail.png`

原始 ZIP 与原始 Xacro 均保留，所有错误尝试和覆盖前版本均位于 `~/arm2026_ws/_backup`。本任务未打开机械臂串口、未执行舵机/GPIO 指令、未控制实物机械臂。
