# 2026-10-07 · 完成观测器时序修复

本次修复已有判定器的边界，不新增场景、机器人、训练或完整里程碑。历史 evidence 保持原样，旧文章的数字仍对应原固定提交。

## E11：先处理同一时刻的新观测

旧实现在 now=旧 capture+age 时先清空连续窗口，再接纳本次新包。20ms 采样、40ms 固定延迟和60ms年龄上限下，即使新包一直有效，也会在每次到达时清空窗口。

现在先检查本次新包；没有新的有效时间戳时才以最后 capture 检查过期。依然拒绝未来、乱序和重放，沉默时仍撤销当前有效性；历史 completed_at 不被擦除。`test_lifecycle.py` 包含连续延迟流与随后沉默的反例。

## E14：释放时刻是捕获时间的下界

Qualified 在每个控制 tick 收到 release intent，记录从 false 变为 true 的 tick；释放前 capture 的延迟包不得参与释放后的验证跨度。持续为 true 时不反复重置边界；新的释放周期从新的边界开始。调用者须逐控制 tick 提供实际意图，不能到收到观测时才补报释放。意图不等于夹爪已物理松开：无手指接触等物理判据仍单独检查。

独立审计同步此契约，E14 同时检查源码指纹。未变更原始轨迹、录像或结论，没有以新测试替换旧实测数据。

```powershell
python -m unittest discover -s experiments/vl01_completion_lifecycle -p test_lifecycle.py -v
python -m unittest discover -s experiments/vl01_qualified_completion -p test_completion.py -v
python experiments/vl01_completion_lifecycle/run.py --out outputs/lifecycle-review
python experiments/vl01_completion_lifecycle/audit.py outputs/lifecycle-review
python experiments/vl01_qualified_completion/run.py --out outputs/qualified-review
python experiments/vl01_qualified_completion/audit.py outputs/qualified-review
```

环境沿用 requirements-lock.txt。数值检查不需要新服务或 API Key；输出目录必须不存在。复现旧文请使用旧文固定提交，这份修正不会追溯改写它。
