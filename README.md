# Hohoo Embodied Agent

以仿真优先（Simulation First）的方式，从 AI 应用开发逐步走向机器人软件、数据与具身智能。

**当前状态：已完成十二轮 MuJoCo 教学对照，从拾取偏移、观测契约推进到完成状态与终止后的退出动作。各轮保留独立原始证据；完整 Agent、ROS2 与训练路线尚未实现。**

- [学习之旅](https://huhohoo.com/journey)
- [虚拟具身实验室](https://huhohoo.com/journey/virtual-lab)
- [里程碑与实施顺序](ROADMAP.md)

## 目标

逐步验证一个任务：用户说“把桌上的红色方块放进蓝色盒子”，系统在虚拟环境中理解任务、调用工具、控制机器人并记录观测与执行数据。

AI Application、LLM / Multimodal 与 Embodied AI 共同服务于这个项目，不作为互不相关的课程列表。

## 目标架构（待实现）

用户 → 对话界面 → LLM → Agent → 任务规划 → VLM → 机器人工具 → ROS2 → 策略 → 仿真引擎 → 虚拟机器人 → 观测 → 机器人数据平台 → Dataset → LeRobot → 训练

机器人运行闭环：环境 → 观测 → 感知 → 推理/规划 → 策略 → 行动 → 环境。

策略迭代：Episode → Dataset → Training → New Policy。

## 仿真优先

1. MuJoCo：已有教学级笛卡尔夹爪抓取放置实验，后续扩展失败反馈与机器人模型。
2. Gazebo + ROS2：规划系统软件与虚拟传感器实验。
3. ManiSkill：规划策略学习与评估实验。
4. Isaac Sim / Isaac Lab：未来阶段，尚未安装或集成。
5. Sim2Real 与真实机器人：后期验证，不是当前前置条件。

前期不要求购买机器人、机械臂或专用硬件。实际实验前再验证操作系统、依赖版本与算力条件，不承诺任意电脑都能运行所有模拟器。

## 按需生长的代码结构

以下是未来职责划分，不是已经实现的目录或功能：

- `apps/`：后续对话界面与真实数据运行后的数据面板。
- `agent/`：planner、tools、memory、rag。
- `llm/`：prompts、structured-output、multimodal、eval。
- `robotics/`：ROS2、机器人模型与控制。
- `simulation/`：按阶段接入 MuJoCo、Gazebo、ManiSkill、Isaac。
- `data/`：collector、synchronizer、episode、quality、LeRobot 转换代码。
- `policies/`：行为克隆、ACT、SmolVLA 的后续实验。
- `experiments/`、`docs/`：可复现的实验记录和说明。

不提前创建空目录，不强行统一所有模拟器接口。M1 的结构化任务与验证仍按路线推进；独立的 VL01 首个物理案例已先行完成。

## 实践记录要求

每次实验记录问题、假设、环境、步骤、观察、结果、局限、失败与复现方法。观察不等于结论，计划不等于完成。

不提交私密真实数据、模型权重、API Key 或凭证。公开教学仿真产物存放 evidence/，结果附可追溯版本与协议。

## Getting started

A runnable MuJoCo Cartesian-gripper experiment is available in [experiments/vl01_pick_place](experiments/vl01_pick_place/README.md), with nine recorded rollouts in [evidence/vl01-20260928-v2](evidence/vl01-20260928-v2). It uses real simulated contact, not object teleportation. There is no physical robot, ROS2 bridge, learned policy or model API in this experiment.

## 首个可复现实验

- [场景、坐标、命令与结果说明](experiments/vl01_pick_place/README.md)
- [冻结协议](experiments/vl01_pick_place/protocol.json)
- [原始结果与产物](evidence/vl01-20260928-v2)
- [配套文章](https://huhohoo.com/docs/embodied-ai/mujoco-first-pick-place)

2026-09-28，由 Codex 在作者授权下执行。无偏移组三次满足协议；25 / 50 mm 偏移组未抬起方块。重复没有随机化，不作为泛化成功率；不会因此把整个 M4/M5 标为完成。作者个人学习与人工复核另行进行。
## 抓取失败反馈

[第二轮：抓取确认后再搬运](experiments/vl01_grasp_guard/README.md)已完成18个配对回合：失败组取消空手搬运，成功组轨迹保持不变。记录位于 evidence/grasp-guard-20260929。状态来自仿真真值，不代表视觉或真实机器人能力。
## 搬运中的持续监测

[第三轮：持续接触监测](experiments/vl01_transfer_monitor/README.md)已完成27回合。单次空接触报告会触发立即停止，连续三次确认可以容忍；受控松爪后三种策略都未挽回掉落。代码、CSV审计与二维轨迹重放公开，完整M4/M5仍未完成。

## 观测新鲜度与采样间隔

[第四轮：消息到达不代表观测仍然新鲜](experiments/vl01_observation_freshness/README.md)完成45个固定条件回合，分离异常计数、异常持续跨度与60ms年龄检查。旧正常包重送和静默条件均保留真实松爪记录；全部代码、控制日志与独立审计位于 evidence/freshness-20260929。

## 观测恢复后的重新验收

[第五轮](experiments/vl01_recovery_gate/README.md)完成18回合：延迟、乱序、通信间断与旧包重送。收到即恢复在旧包条件下9次恢复中有8次证据不足，却最终完成放置。新观测重新验收策略恢复有效抓取，掉落时保持停止；不实现重抓取。产物见 evidence/recovery-20260930。

## 门控与路径分离

[第六轮：恢复消融](experiments/vl01_recovery_ablation/README.md)将门控与重规划独立组合：30回合、另18回合E5回归，原始记录和独立审计完整归档。重规划降低首次目标跳变，但本矩阵没有观察到放置成功率提升；不能替代新鲜抓取证据。配套文章： https://huhohoo.com/docs/embodied-ai/mujoco-recovery-ablation 。

## 下降阶段的抓取契约

[第七轮：阶段监测](experiments/vl01_phase_contracts/README.md)完成21回合。照搬搬运高度规则会误停正常下降；按阶段检查能检出下降故障，但保持目标仍可能留下手指接触，最终未通过放置。完整矩阵、原始日志、图表与独立审计见[evidence/phase-contracts-20261001](evidence/phase-contracts-20261001/RESULTS.md)。

## 2026-10-03 / E8–E10

[退出动作、释放验收与恢复预算](experiments/vl01_exit_release_budget/README.md)完成32回合，保留96份压缩控制/物理状态/摘要文件与独立审计。E8晚下降松爪消除残留接触，但搬运掉落仍失败；E9持续窗口不能保证完成后的状态不再变化；E10预算限制反复恢复，同时可能终止原本最终能完成的回合。完整M4/M5状态不变。

## 恢复终止后的退出动作

[第十二轮：终止与退出分离](experiments/vl01_abort_exit/README.md)完成12个回合：保持、松爪、松爪后退均未挽回两组中断条件的放置。无故障/下降静默组完成放置，后者同时暴露 transfer-only 监控覆盖边界。保留72,000行控制日志、7,200个可回放状态与三画面对照。退出不是安全认证。
