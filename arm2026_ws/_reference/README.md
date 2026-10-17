# Unitree Z1 官方 ROS 参考包

## 来源与版本

- 官方仓库：<https://github.com/unitreerobotics/z1_ros>
- ROS1 分支：`noetic`
- 主仓库提交：`d3bafd38fb48e805096da7abb0c19a15b636975d`
- 官方 `unitree_ros` 子模块提交：`8ebecd883a842a4631fcfa98933fae586aeb6709`
- 本地目录：`_reference/unitree_z1_ros_official_noetic/`

这是只读参考副本，不属于 `marm_description` 包，也不会被当前模型的 Xacro 自动加载。`unitree_ros` 子模块包含 `z1_description`、Gazebo 相关资源和官方网格，因此完整参考副本约 770 MB；网格只用于观察官方结构，不复制到我们的模型中。

## 目录结构

官方主仓库按职责拆分：

| 目录 | 作用 |
| --- | --- |
| `z1_bringup/` | 真实/仿真启动编排，例如 `sim_arm.launch`。 |
| `z1_controller/` | 控制器与 SDK 接口。 |
| `z1_hw/` | ROS hardware interface、trajectory controller 与夹爪 action。 |
| `z1_moveit_config/` | MoveIt 规划、控制器和 Gazebo 配置。 |
| `z1_rviz/` | RViz 模型显示和 MoveIt RViz 启动文件。 |
| `z1_examples/` | MoveIt 与夹爪示例。 |
| `z1_sdk/` | UDP/SDK 示例。 |
| `unitree_ros/robots/z1_description/` | 机器人描述包，包含 Xacro、URDF、材质/网格、碰撞和惯性数据。 |

关键官方描述文件：

- `unitree_ros/robots/z1_description/xacro/robot.xacro`：主入口。
- `unitree_ros/robots/z1_description/xacro/const.xacro`：尺寸、质量、惯性、关节范围和碰撞尺寸参数。
- `unitree_ros/robots/z1_description/xacro/gazebo.xacro`：Gazebo 控制插件与自碰撞配置。
- `unitree_ros/robots/z1_description/xacro/transmission.xacro`：可复用电机 transmission 宏。
- `unitree_ros/robots/z1_description/launch/z1_rviz.launch`：Xacro、关节 GUI、TF 发布器和 RViz 的最小显示链路。
- `z1_bringup/launch/sim_arm.launch`：Gazebo、ROS controller、MoveIt、RViz 的仿真总入口。

## 对我们模型的可借鉴点

官方 Z1 采用非常清晰的机械模块分段：

1. `link00` 底座电机壳体；
2. `link01` 肩部回转壳；
3. `link02` 第一段长承力臂和肘部电机壳；
4. `link03` 第二段偏置承力臂；
5. `link04`、`link05`、`link06` 三段紧凑腕部；
6. 可选固定夹爪掌部与运动夹爪部件。

本项目把这种“电机壳体—承力臂—端部关节壳—腕部—法兰/夹爪”的视觉层次映射到了现有 `base_link → link0 … link6`：增加独立端环、电机罩、箱型承力壳、侧向加强脊、腕部方壳和法兰适配层。我们保留自己的 Link/Joint 名称、origin、axis、limit、collision 和 inertial，未直接复制 Z1 的尺寸或网格。

## 官方包与本模型的边界

- 官方包的 `.dae/.STL` 网格不在 `src/marm_description` 中引用。
- 当前模型仍使用 box/cylinder/sphere 基础几何体，便于课堂解释和离线验证。
- 参考的是结构组织和工业外观语言，不声称我们的机械臂是实际 Unitree Z1。
- `z1_controller`、`z1_sdk`、UDP、真实硬件和串口接口不属于本课程模型运行范围；本项目只使用 Xacro、URDF、TF、joint state 和 RViz。

## 手工查看官方包

```bash
cd ~/arm2026_ws/_reference/unitree_z1_ros_official_noetic
sed -n '1,260p' unitree_ros/robots/z1_description/xacro/robot.xacro
sed -n '1,260p' unitree_ros/robots/z1_description/xacro/const.xacro
sed -n '1,220p' z1_rviz/launch/view_model.launch
```

不要在官方参考副本中直接修改并把改动混入我们的课程包；如果要试验，应复制到明确的实验目录，并保留上面的提交号。
