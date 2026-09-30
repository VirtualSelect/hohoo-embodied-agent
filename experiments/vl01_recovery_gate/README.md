# E5：通信恢复后的重新验收

复用 VL01 场景，比较锁存停止、收到消息就恢复、重新验收后规划剩余路径。协议在首次正式运行前冻结于 protocol.json。

```powershell
.venv/Scripts/python experiments/vl01_recovery_gate/test_gate.py
.venv/Scripts/python experiments/vl01_recovery_gate/run.py --out evidence/recovery-20260930
.venv/Scripts/python experiments/vl01_recovery_gate/audit.py evidence/recovery-20260930
```

18个固定条件回合，每格一次，不随机重复。关节控制和物理照常运行；hold只保持目标，不冻结状态。重新验收使用仿真真值包，不包含视觉、ROS2或硬件安全认证。暂时没有真实机器人。本目录比较策略组合，不能把策略间差异归因于单一条件。

抓取证据要求：双侧接触、方块高于0.12米、方块与夹爪中心距离小于0.05米；阈值只适用于该教学场景。100毫秒连续新观测通过后，从当前夹爪实测位置重新生成路径；不直接续用积压动作。600毫秒恢复期限优先于同一tick的成功判定。详见��结协议。
