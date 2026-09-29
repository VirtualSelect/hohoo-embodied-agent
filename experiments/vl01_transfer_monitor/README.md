# E3：搬运中的持续接触监测

研究问题：4秒时已经确认抓住，之后松爪怎么办？立即停止与连续异常确认如何权衡？

## 已执行的协议

- 复用 VL01 场景、MuJoCo 3.3.7、0偏移抓取、原有位置执行器和时序，不修改方块位姿。
- 每回合在4秒先通过 E2 高度/双侧接触检查；只在 transfer（4–5.5秒）持续监测。
- 三条件：clean、observation-gap、forced-open。
- observation-gap 在4.802秒这一个50Hz样本上，将传给监测器的接触集合置空；真实接触保留。不是删掉时间戳或模拟网络丢包。
- forced-open 在仿真时间 [4.8,5.04) 秒，将两个夹爪位置目标覆盖为0；这是受控执行器松爪故障，不是自然摩擦滑移。
- 三策略：once（只保留前置门控）、immediate（一个异常）、debounced（连续三个异常）。异常指缺少任一侧接触。
- 正常观测把计数清零；报警锁存。报警后冻结刚发送的目标、继续仿真0.6秒，取消后续阶段。
- 3条件 × 3策略 × 3次确定性重复 = 27回合，没有随机化，不当作独立统计样本。

冻结源代码：c3208d9d475534efbaab3fbe607f7c1276ed9af7；完整证据在 [evidence/transfer-monitor-20260929](../../evidence/transfer-monitor-20260929)。

## 实际观察

| 条件 | once | immediate | debounced |
|---|---|---|---|
| 无扰动 | 3次放置完成 | 3次放置完成 | 3次放置完成 |
| 单次空接触报告 | 3次放置完成 | 3次误停，未完成放置 | 3次放置完成 |
| 持续0.24秒松爪 | 3次继续空手搬运 | 3次取消后续搬运 | 3次取消后续搬运 |

松爪组三种策略均未完成放置，方块最终落到地面。持续监测没有实现重新抓取。

首个异常记录为4.802秒。immediate在同一采样点报警；debounced在4.842秒报警，相比首个异常多40ms（不是从故障物理起点测出的零延迟）。从首个异常到各自回合结束，夹爪水平累计路径分别为132.135 / 11.902 / 22.534mm。三个结束时间不同；这是实际后续路径，不是固定时长的速度指标或硬件制动距离。

## 复现

在仓库根目录，使用现有 requirements.txt / requirements-lock.txt 环境（本轮 Python 3.12.14）：

```powershell
.venv/Scripts/python.exe -m unittest discover -s experiments/vl01_transfer_monitor -p test_monitor.py -v
.venv/Scripts/python.exe experiments/vl01_transfer_monitor/run.py --out outputs/my-transfer-monitor
.venv/Scripts/python.exe experiments/vl01_transfer_monitor/audit.py outputs/my-transfer-monitor
.venv/Scripts/python.exe experiments/vl01_transfer_monitor/render.py outputs/my-transfer-monitor
```

运行目录必须不存在。render也拒绝覆盖已有视频。测试不调用模型，不需要密钥。11项边界测试覆盖连续计数、恢复、单侧缺失、阶段边界和报警锁存。

独立audit不导入runner/monitor：重算27条CSV的故障、观测、计数、报警、目标和结果，核对18对状态前缀；9条无扰动轨迹与上轮完全相同，6条可容忍单次缺失的轨迹与无扰动完全相同；18次重复比较一致。检查不证明真实机器人的安全性。

## 产物与重放

- manifest.json：源码commit、hash、依赖版本、冻结协议；运行时工作区干净。
- 每回合 trajectory.csv / states.jsonl / events.json / summary.json。
- audit.json：独立检查与各CSV校验值；monitor-comparison.png 从CSV生成。
- 两段 trajectory-replay.mp4：50Hz真实坐标的XZ投影；圆形/方形只是中心标记，不是MuJoCo场景画面。
- media.json：帧数、时长、原始CSV与视频hash。
- 本轮OpenGL渲染不可用（WGL/GLAD错误），因此未生成新的三维场景录像；完整 qpos/qvel/ctrl 可在具备OpenGL的环境中，用上一轮 replay.py 重放：

```powershell
.venv/Scripts/python.exe experiments/vl01_grasp_guard/replay.py evidence/transfer-monitor-20260929/forced-open-debounced-run-1/states.jsonl --out outputs/transfer-monitor-3d.mp4
```

三维重放命令本轮未成功验证。CPU坐标视频已经生成；没有用旧录像充当新实验录像。

## 结论边界

本实验只监测搬运阶段；放低、主动释放与退开不使用同一规则。接触信号来自仿真真值，没有视觉、传感器延迟、连续丢包、随机摩擦、学习策略或真机。三次连续阈值仅是对照条件，没有被证明最优。

下一步应在冻结规则下扫描缺失长度/采样间隔，设计观测新鲜度检查，再研究明确的恢复动作；本轮未自动执行这些新实验。

[配套文章](https://huhohoo.com/docs/embodied-ai/mujoco-transfer-monitor)
