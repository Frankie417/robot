# 实机教学代码的 PyBullet 仿真

本目录包含来自 `robot/2.机械臂实验` 的两段动作序列的仿真版本：

- `dance`：对应 `03.机械臂舞蹈表演`；
- `transport`：对应 `04.机械臂定点搬运色块` 的抓取、过渡、放置轨迹。

已配置的虚拟环境位于工作区根目录 `.venv-arm5dof-sim`，依赖清单为
`requirements-sim.txt`。从本目录执行：

```powershell
& 'D:\robot_new\.venv-arm5dof-sim\Scripts\python.exe' run_real_examples_in_sim.py dance
& 'D:\robot_new\.venv-arm5dof-sim\Scripts\python.exe' run_real_examples_in_sim.py transport
```

最简单的 GUI 启动方式：

```powershell
.\run_gui.ps1 dance
.\run_gui.ps1 transport
```

默认显示窗口，并在动作结束后保留 30 秒；例如保留一分钟：

```powershell
.\run_gui.ps1 dance -Hold 60
```

如需自动化验证，可显式使用无界面模式：

```powershell
& 'D:\robot_new\.venv-arm5dof-sim\Scripts\python.exe' run_real_examples_in_sim.py dance --headless
```

仿真 `home` 已同步为实机配置的 `[150, 0, 200, None, pi]`，并采用同一份
末端 Z 误差修正。场景读取实机 `T_arm2ws.txt`、`119 x 159 mm` 工作台尺寸和
`28 mm` 色块高度；工作台、坐标轴、抓取点和四个颜色放置点按实机坐标放置。

`transport` 中的 28-mm 色块是动态刚体：夹爪闭合后，色块会绑定到
`tool_center_frame` 随机械臂移动；夹爪打开后，会在原 Notebook 的放置点解除
绑定。该绑定是确定性教学仿真，不是基于指尖接触力的抓取成功率验证。源代码未
保存每次视觉检测到的真实色块中心，因此初始色块的 XY 是固定抓取点的参考值。

搬运入口的抓取点使用 `Roll=179.2 deg`，使夹爪以水平的左右方向开合；原始
Notebook 的 `Roll=91.6 deg` 保留在历史文件中，但会使该 URDF 的指爪开合方向
带有竖直分量。
