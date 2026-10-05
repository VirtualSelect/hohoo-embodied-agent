# E14 · 恢复链中的完成契约

复用 E13 phase-aware 控制与 E11 当前有效性判定。8 个固定 MuJoCo 场景，每条物理轨迹上并排观察三个判定器：历史放置、当前放置、具备执行资格的当前完成。不是 24 次独立物理实验。

`python -m unittest discover -s experiments/vl01_qualified_completion -p test_completion.py`
`python experiments/vl01_qualified_completion/run.py --out evidence/qualified-completion-your-run`
`python experiments/vl01_qualified_completion/audit.py evidence/qualified-completion-your-run`

release intent 是控制指令，不是硬件执行确认。ABORTED 为终态；物理落入盒子不能反向恢复执行资格。瞬时坏观测仍会撤销当前有效性，未解决感知噪声或真机安全问题。完整 VL01、M4/M5 未完成。

## 2026-10-05 实测归档

8回合、48,000行控制记录、4,800状态；下降松爪物理通过但执行已终止，推动后历史完成仍在而当前有效性失效。

[配套文章](https://huhohoo.com/docs/embodied-ai/mujoco-qualified-completion)。图表脚本为 plot.py；原始记录和独立审计见 evidence 目录。
