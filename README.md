# Hohoo Embodied Agent

以仿真优先（Simulation First）的方式，从 AI 应用开发逐步走向机器人软件、数据与具身智能。

**当前状态：项目初始化与学习规划。尚无机器人控制代码、仿真实验、数据集或训练结果。**

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

1. MuJoCo：规划机器人基础、控制、抓取与放置实验。
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

不提前创建空目录，不强行统一所有模拟器接口。第一步从 M1 的结构化任务与验证开始。

## 实践记录要求

每次实验记录问题、假设、环境、步骤、观察、结果、局限、失败与复现方法。观察不等于结论，计划不等于完成。

真实数据、模型权重、API Key 和凭证不提交到仓库。结果与指标必须附可追溯证据。

## Getting started

This repository currently contains planning documents only. There is no runnable robot demo or simulator integration yet. Implementation will follow the milestones in [ROADMAP.md](ROADMAP.md), starting with validated structured robot tasks and fake tools.
