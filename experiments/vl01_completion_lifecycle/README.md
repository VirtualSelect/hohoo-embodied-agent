# E11 / 完成事件与当前有效状态

复用VL01物理场景，七种固定条件各运行一次。两种观察器处理同一条物理轨迹，不修改控制器，不将观察器数量当作试验数量。完成事件锁存；当前状态可因新鲜违反而INVALID，因观测过期而UNKNOWN，重新稳定后再次VALID。

```sh
python -m unittest discover -s experiments/vl01_completion_lifecycle -p "test_*.py"
python experiments/vl01_completion_lifecycle/run.py --out evidence/NEW-E11
python experiments/vl01_completion_lifecycle/audit.py evidence/NEW-E11
```

使用仓库已有Python3.12、MuJoCo3.3.7和NumPy2.2.6环境。输出必须为新目录。取样真值与收到的合成故障观测分开保存；一个时钟、固定托盘、没有视觉或硬件安全保证。INVALID后不自动重新抓取；UNKNOWN也不等于物体已失败。
