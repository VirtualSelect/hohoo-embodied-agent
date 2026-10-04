# E13 / 下降阶段的中断与恢复

把阶段观测契约接入已有恢复预算：transfer-only、下降复用搬运高度规则、phase-aware 三种策略；六种冻结条件，共18个12秒回合。终止后一律保持，避免把退出策略和恢复策略混为一个变量。

HOLD 保存被中断的阶段，不能把 hold 当作新的作业阶段重置证据。恢复从测量夹爪位置出发，用0.5秒到达被中断阶段终点，接上剩余阶段。下降不重新升到搬运高度。

```text
python -m unittest discover -s experiments/vl01_phase_recovery -p test_gate.py
python experiments/vl01_phase_recovery/run.py --out evidence/my-run
python experiments/vl01_phase_recovery/audit.py evidence/my-run
```

场景、2ms步长和最终500ms放置验收复用原实验。门控只读取观测包，物理真值仅用于独立结果检查。绝对时间注入传感器间断或松爪故障；同一故障不保证遇到相同阶段，必须结合日志解读。没有在线规划、重抓取、硬件安全证明，完整VL01仍未完成。
