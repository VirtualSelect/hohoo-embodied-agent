# E7：下降阶段需要什么抓取契约？

先冻结协议，再运行七条件×三策略的21个确定性回合。沿用 VL01 场景与固定时间表，用同一锁存停机处理所有报警，不加入恢复或重规划，隔离监测范围与判据。

| 策略 | 搬运 | 下降 | 主动释放后 |
| --- | --- | --- | --- |
| transfer-only | 双指接触、误差<5cm、高度>12cm、采样年龄<60ms | 不监测 | 不监测 |
| reuse-transfer | 同左 | 照搬搬运规则 | 不监测 |
| phase-aware | 同左 | 双指接触、误差<5cm、采样年龄<60ms；移除搬运高度要求 | 不监测 |

物理步长2ms，观测20ms，连续坏采样跨度40ms才报警；年龄达到60ms即报警。停止决策在物理步之后生效，下一控制步保持当时目标。保持目标不代表冻结物理或安全状态。

条件：无故障、搬运松爪、下降早/晚松爪、下降丢包、旧包重送、一次空接触报告。松爪只修改执行器目标；不得改写物体状态。最终放置独立检查，不以停机与否代替。

## 运行

从仓库根目录，使用已有 Python 3.12 / MuJoCo 3.3.7 环境：

```powershell
python -m unittest discover -s experiments/vl01_phase_contracts -p 'test_monitor.py' -v
# 提交代码与协议后运行，manifest必须记录干净工作区
python experiments/vl01_phase_contracts/run.py --out evidence/my-e7-run
python experiments/vl01_phase_contracts/audit.py evidence/my-e7-run --out evidence/my-e7-run/audit.json
$env:E7_EVIDENCE = (Resolve-Path evidence/my-e7-run).Path
python -m unittest discover -s experiments/vl01_phase_contracts -p 'test_*.py' -v
python experiments/vl01_phase_contracts/plot.py evidence/my-e7-run --out evidence/my-e7-run/figures
```

独立审计器不导入控制器或 MuJoCo，重算阶段时间表、故障注入、包接纳、采样年龄、坏采样跨度、停机时刻、保持目标、放置验收与策略分叉前的状态前缀。它检查记录一致性，不重算接触力，也不证明模拟器无误。

`control.csv`保留每个2ms控制步；`trajectory.csv`和`states.jsonl`保留20ms采样；另有事件、逐格结果、源码和原始文件指纹。审计测试在临时副本中篡改命令、包、事件、结果和状态，验证能发现不一致。所有原始运行均保留，不根据结果调整阈值后覆盖旧证据。

## 边界

每格一次、固定初始状态、单时钟、仿真真值。不是成功率估计，不包含视觉、ROS2、学习策略、重新抓取或真机。移除下降高度阈值不等于证明整个下降安全：任务阶段仍由时间表决定；进入主动释放即停止抓取监测，释放后的安全契约仍未实现。观察和结论分别报告，假设不成立也保留结果。
