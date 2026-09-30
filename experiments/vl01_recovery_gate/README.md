# E5：通信恢复后的重新验收

复用 VL01 场景，比较锁存停止、收到消息就恢复、重新验收后规划剩余路径。协议在正式运行前冻结于提交8142cdb的protocol.json。

```powershell
.venv/Scripts/python experiments/vl01_recovery_gate/test_gate.py
.venv/Scripts/python experiments/vl01_recovery_gate/run.py --out evidence/my-new-run
.venv/Scripts/python experiments/vl01_recovery_gate/audit.py evidence/my-new-run
.venv/Scripts/python experiments/vl01_recovery_gate/render.py evidence/my-new-run
```

18个固定条件回合，每格一次，不随机重复。关节控制和物理照常运行；hold只保持目标，不冻结状态。重新验收使用仿真真值包，不包含视觉、ROS2或硬件安全认证。没有真实机器人。本目录比较策略组合，不能把策略间差异归因于单一条件。

抓取证据要求：双侧接触、方块高于0.12米、方块与夹爪中心距离小于0.05米；阈值只适用于该教学场景。100毫秒连续新观测通过后，从当前夹爪实测位置重新生成路径；不直接续用积压动作。600毫秒恢复期限优先于同一tick的成功判定。

## 已运行结果

原始产物：evidence/recovery-20260930；Python3.12.14、MuJoCo3.3.7、NumPy2.2.6。18项新单元测试通过；18回合独立审计验证12组决策前状态前缀完全相同、两个重新验收窗口、108份原始文件哈希。两张图由实际日志绘制，不是视觉传感器图像。

| 条件 | 锁存停止 | 收到即恢复 | 重新验收 |
|---|---|---|---|
| 无扰动 | 成功 | 成功 | 成功 |
| 固定40ms延迟 | 成功 | 成功 | 成功 |
| 每三包延迟80ms造成乱序 | 成功 | 成功 | 成功 |
| 240ms通信间断 | 中止，未放置 | 恢复1次，成功 | 恢复1次，成功 |
| 间断后重送旧正常包 | 中止，未放置 | 恢复9次，其中8次证据不足；最终成功 | 恢复1次，成功 |
| 间断并受控松爪 | 中止，未放置 | 恢复6次，均证据不足；未放置 | 不恢复，中止 |

证据不足定义为恢复时观测年龄>=60ms或抓取谓词不成立；不是对真实机器人的安全判定。旧包重送条件，首次停止4.842s，收到即恢复5.042s使用4.782s的捕获（已260ms）；重新验收直到5.302s才恢复。仅通信间断时重新验收在5.142s恢复；掉落条件在5.442s结束等待。

确认窗要求capture严格递增、晚于hold、相邻不超过20ms、跨度至少100ms，所有记录仍然新鲜且抓取成立。完成放置不意味着中间恢复决定合理。相反，放置失败也可能是正确执行停止策略。该实验不修复掉落物体，不测试重抓取。

## 证据文件

每回合control.csv（2ms）、trajectory.csv和states.jsonl（20ms）、events.json、replans.json、summary.json。根目录manifest冻结环境/协议/源码指纹；audit.json复核结果和原始文件。旧版本源码在Windows检出为CRLF；跨平台审计需使用同一换行字节，或参考提交新增的portable-audit.py，仅恢复manifest中明确匹配的换行形式到临时目录后执行原审计。不会修改已提交证据。

[配套文章](https://huhohoo.com/docs/embodied-ai/mujoco-recovery-gate)
