# E6 恢复门控与剩余路径重规划消融

在 E5 教学级笛卡尔夹爪场景中，独立组合 receipt/revalidate 门控与 wallclock/replan 路径方式，外加 latched 锁存参照。六条件共30个确定性回合，每格一次，seed=null。没有随机成功率、视觉、ROS2、学习策略、重抓取或真实机器人。

## 复现

在仓库根目录使用 Python3.12.14、MuJoCo3.3.7、NumPy2.2.6；绘图使用 Matplotlib3.10.6。建议在独立虚拟环境中安装 requirements-lock.txt。以下 `python` 指该环境解释器：

```sh
python -m unittest discover -s experiments/vl01_recovery_ablation -p 'test_*.py'
python experiments/vl01_recovery_ablation/run.py --out runs/e6-new
python experiments/vl01_recovery_ablation/audit.py runs/e6-new
python experiments/vl01_recovery_ablation/render.py runs/e6-new
```

run.py拒绝覆盖已有目录。先冻结protocol.json和代码，再运行；manifest记录提交、dirty标记、实际运行环境和源码指纹。当前代码复用E5 gate.py并保留其原18项测试；E5源码和证据不改。

## 矩阵与控制

| gate_mode | path_mode | 说明 |
|---|---|---|
| receipt | wallclock | 收到任何合法包后恢复旧墙钟时间轴 |
| receipt | replan | 收到即恢复，从实测夹爪位置重新生成剩余轨迹 |
| revalidate | wallclock | 重新验收后恢复旧墙钟时间轴 |
| revalidate | replan | 重新验收后重规划，即E5完整策略 |
| latched | wallclock | 停止后不恢复 |

条件、故障起点和期限沿用E5。hold保持执行器目标，物理继续；路径重规划包括重新定时，不能将差异仅归因几何。重规划只重建transfer及原lower/release/retreat/settle，并非避障或IK。Gate仅在transfer监测，恢复后进入其他阶段可能不再触发hold，这是继承的范围限制。receipt反复恢复可反复重置路径，未添加冷却或次数上限。

## 日志与独立验收

每格输出control.csv（2ms）、trajectory.csv与states.jsonl（20ms）、events.json、replans.json、summary.json。control记录独立gate/path模式、包龄、目标、实测手部位置以及位置2ms差分速度。事件发生tick的控制仍为hold目标；下一tick才应用恢复后的路径。J为这两tick目标差，E为下一tick目标相对恢复tick实测位置的差。

审计不导入Gate、不重放控制器；从原始日志核对包顺序、新鲜度、确认窗、期限、放置谓词、24组相对latched前缀与12组同门控路径前缀，并输出audit.json和metrics.json。图表来自日志，不是视觉传感器画面。

兼容字段unsupported_resumes仅统计恢复时包龄≥60ms或抓取谓词为假，不代表完整100ms确认窗的全部要求。首次新鲜好包即可使receipt的该计数为0，仍可能缺确认窗；报告须分开解释旧/坏包恢复和完整窗验收。

协议验收与假设支持分开：结构不一致会使审计失败；有效运行中出现跳变比未减半、未完成放置或不支持恢复，应记录为不支持假设，不能删格或修改冻结阈值。重规划起点误差≤1e-9m、首目标E≤1mm、gap/stale-replay同门控J比≤0.5为预定路径门槛；revalidate证据不足恢复数为0，掉落时不恢复；完整策略五个非掉落条件满足原终端放置条件。

最终放置使用原协议最后0.5s：xy每轴距(0.24,0.12)m<45mm，z距0.026m<6mm，速度<0.02m/s、无手指接触，且此前抬升>0.1m。time_to_success由记录中首次持续≥0.5s满足条件的窗口估计，分辨率20ms；不能代替最终结果。

## 状态

结果与环境验证见交付包RESULTS.md。保持完整M4/M5未完成，不将正确中止计为放置成功。

## 2026-09-30 本机接入验证

交付的30回合E6和18回合E5回归归档于 `evidence/recovery-ablation-20260930/`；原 manifest 保留 Linux 环境、基线提交和 dirty=true，未改写成此次归档提交。完整结果见该目录 `RESULTS.md`。

Windows Python 3.12.14、MuJoCo 3.3.7、NumPy 2.2.6：30项单元测试、E6/E5原始记录独立审计通过。本机核验不是新增48回合仿真。跨平台换行使用临时副本恢复到已知SHA256后再审计；不关闭哈希检查，不改写旧证据。

```powershell
.venv/Scripts/python -m unittest discover -s experiments/vl01_recovery_ablation -p 'test_*.py'
.venv/Scripts/python experiments/vl01_recovery_ablation/portable-audit.py evidence/recovery-ablation-20260930/e6-final
.venv/Scripts/python experiments/vl01_recovery_gate/portable-audit.py evidence/recovery-ablation-20260930/e5-regression
.venv/Scripts/python experiments/vl01_recovery_ablation/render.py evidence/recovery-ablation-20260930/e6-final
.venv/Scripts/python experiments/vl01_recovery_ablation/article-figure.py evidence/recovery-ablation-20260930/e6-final
```

两个画图脚本只生成PNG，不修改冻结日志；`article-figure.py` 是归档时新增的展示工具，不属于原仿真运行源码清单。论文式效果图不等于相机录像。
