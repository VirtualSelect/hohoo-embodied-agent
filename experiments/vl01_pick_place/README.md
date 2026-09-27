# VL01 / 第一轮：目标偏了，为什么抓不到？

这是自主编写的教学级笛卡尔夹爪场景，不是商业机械臂模型。三个平移关节 + 两个夹指关节，通过 MuJoCo 位置执行器和接触摩擦夹取一个 40 mm 红色方块，再放入蓝色盒子。代码不使用粘附约束、物体传送、VLM、LLM、ROS2 或学习策略。

## 运行（仓库根目录）

已实际验证：Windows x64、Python 3.12、MuJoCo 3.3.7。初次安装需网络，之后无模型 API、无需下载权重。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s experiments/vl01_pick_place -p test_contract.py
.\.venv\Scripts\python.exe experiments/vl01_pick_place/run.py --out outputs/my-first-run --render
.\.venv\Scripts\python.exe experiments/vl01_pick_place/analyze.py outputs/my-first-run
```

Linux/macOS 使用 Python 3.12，将解释器路径替换为 `.venv/bin/python`；这些系统尚未实际验证。纯物理检查去掉 `--render`；渲染需要可用 OpenGL 环境。输出目录必须不存在，脚本拒绝覆盖已有记录。完整协议为 protocol.json，重复执行前先检查它。

## 看懂代码

| 文件 | 职责 |
| --- | --- |
| scene.xml | 物体、盒子、关节、执行器、摩擦和相机 |
| protocol.json | 运行前固定的条件和成功判定 |
| run.py | 9 阶段控制、真实物理步进、记录和原始视频 |
| analyze.py | 只读取保存的 CSV，复核结果并画图 |
| replay.py | 以保存的状态渲染轨迹，不重新跑策略 |
| test_contract.py | 防止把“到达目标”或“没有松手”误算成功 |

坐标均为世界系，米为单位，+z 向上。手掌基点在 z=0.16 m，因而 `z` 关节目标是“期望世界高度减 0.16”，不是直接把世界高度塞进关节控制量。夹指的正位移都表示向内，左右轴方向相反。位置执行器接收关节目标，并不直接把物体坐标改成目标。

## 实验协议与边界

- 仅拾取目标 x 偏移改变：0、0.025、0.05 m。放置点始终固定。
- 每组重复三次，初始条件完全一致，无随机化；这是确定性重复性检查，不能计算面向任意物体的泛化成功率。
- 物理步长 0.002 s；每 10 步保存一次轨迹/状态（50 Hz），视频 25 FPS，单回合 9.2 s。
- 同一时刻的派生位置和接触在 `mj_forward` 后保存，与 post-step qpos 对齐。
- 成功必须曾经抬至 0.10 m 以上；最后 0.5 s 的记录必须全部满足盒内 XY、落定高度、低速度、夹指无接触。
- 最后 0.5 s 按 50 Hz 采样判定，不宣称连续时间上绝无接触。
- 提升高度峰值在 500 Hz 计算；图来自 50 Hz CSV，不能把图上的采样峰值当作更精确的新指标。
- 超过固定时间即结束。MuJoCo 警告、非有限状态不会被当作成功。

控制采用固定阶段时间表；每个关节位置执行器有反馈，但高层策略不会因“没抓住”重新规划。这正是本轮观察到空夹爪继续搬运的原因之一。接触出现不等于夹持稳定，夹持成功不等于放置成功。

## 真实证据

正式记录：`evidence/vl01-20260928-v2/`。manifest 包含实际运行代码提交、文件 SHA256、版本与是否存在未提交更改。第一轮 pilot 用于检查程序；v2 修正记录时序后重新运行，文章引用 v2。

每个回合包含 trajectory.csv、states.jsonl、events.json、summary.json。每组第一回合额外含 episode.mp4 与九张阶段截图；其余回合仍保留完整采样轨迹。summary.json 汇总九次运行，audit.json 独立复核采样轨迹。

```powershell
.\.venv\Scripts\python.exe experiments/vl01_pick_place/replay.py evidence/vl01-20260928-v2/bias-000mm-run-1/states.jsonl --out outputs/replay.mp4
```

重放视频的状态来自记录，它只用于检查轨迹，不是额外一次实验。

## 实测结果（2026-09-28，北京时间）

无偏移三次均满足本协议；25 mm 和 50 mm 偏移的六次均未抬起。无偏移的最终 XY 距离约 0.673 mm，偏移组约 260.337 / 262.063 mm。该距离是方块到盒子中心的距离，不是末端控制精度，也不是对真实机器人重复定位精度的测量。

细节以 JSON / CSV 为准。这里没有训练、视觉感知、随机物体、真实硬件或 Sim2Real 验证。本案例完成不代表 M4/M5 整个里程碑完成。

场景与程序沿用仓库 Apache-2.0；MuJoCo 许可见其官方项目。所有画面均由实际 MuJoCo 运行生成。
