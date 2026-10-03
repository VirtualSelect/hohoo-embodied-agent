# E12 / 恢复终止后执行什么

将 E10 的两次恢复预算、400ms 冷却、800ms 截止与 E8 的保持/松爪/松爪后退组合。12 个确定性回合，沿用原场景、传感故障时间表、控制器、最终放置判据。退出不叫恢复成功，不保证真机安全。

```sh
python -m unittest discover -s experiments/vl01_abort_exit -p "test_*.py"
python experiments/vl01_abort_exit/run.py --out evidence/abort-exit-MY-RUN
python experiments/vl01_abort_exit/audit.py evidence/abort-exit-MY-RUN
```

每回合保存 2ms 控制/物理日志、20ms qpos/qvel/ctrl，支持 MuJoCo 重放。lower-silence 是 transfer-only 监控的覆盖盲点，不是故障免疫。只允许通过 actuator 改变演化，不瞬移。审计重算最终放置、故障包时间表、退出目标，并检查同条件三策略在退出前轨迹完全相同。
