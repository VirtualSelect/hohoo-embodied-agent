# E4 · 采样间隔与观测新鲜度

本实验复用VL01原场景、零拾取偏差和E2搬运前确认。`protocol.json`在运行前冻结。

## 问题与控制条件

3个观测间隔（10/20/50 ms）×5个条件×3种策略，共45回合，每格一次确定性运行；不作为概率成功率或独立样本。

- clean：无扰动。
- empty-40ms：从4.8秒开始，40 ms内应发出的包报告空接触；不改变物理接触。
- forced-open：从4.8秒开始强制松爪0.24秒，传送真实模拟接触。
- replay-good：相同松爪，4.8秒起重复送达最后一个旧正常包，保持原序号与捕获时间。
- silence：相同松爪，4.8秒起不再送达包。

策略为count3（连续3个唯一坏观测）、elapsed40（连续坏观测首尾跨度达到40 ms）、fresh60（elapsed40加捕获年龄达到60 ms报警）。新包先更新，再检查年龄；接收时间不刷新捕获时间。重复包不能增加异常计数。控制与看门狗每2 ms运行；观测频率与控制频率分开。

报警只在transfer阶段生效，锁存后保持最后命令目标0.6秒；不是冻结物理状态、硬件急停或恢复。只使用模拟单调时钟，不处理跨设备时钟偏差、恶意时间戳、网络抖动或自然摩擦滑移。

## 复现

在仓库根目录使用Python 3.12及已锁定依赖：

```powershell
.venv/Scripts/python.exe -m unittest discover -s experiments/vl01_observation_freshness -p test_monitor.py -v
.venv/Scripts/python.exe experiments/vl01_observation_freshness/run.py --out outputs/my-freshness
.venv/Scripts/python.exe experiments/vl01_observation_freshness/audit.py outputs/my-freshness
```

输出目录必须不存在。先在干净Git提交上运行，不覆盖旧证据。没有模型API或额外依赖。

`control.csv`逐2ms记录搬运/报警保持阶段的真实模拟接触、包序号、捕获时刻、接收事件、采用状态、年龄和报警。`trajectory.csv`与`states.jsonl`保留原50Hz物理轨迹/状态，用于核对配对前缀和旧基线。`events.json`保留冻结目标；`manifest.json`保存代码版本、环境、协议、源文件哈希。独立audit不导入运行器/监测器，重新计算故障、包、计数、年龄、报警、任务验收和配对前缀，并生成两幅实测图。

策略未报警并不代表安全；已报警也不代表成功放置。图表是日志可视化，不是摄像头或三维录像。

## 本轮结果与展示

45回合证据已保存在 [evidence/freshness-20260929](../../evidence/freshness-20260929)。17项新监测边界测试与原有24项测试通过；独立audit通过45回合、45对状态前缀及9条旧基线比较。

生成用于文章的图例精简版（仅日志可视化，不重跑仿真）：

```powershell
.venv/Scripts/python.exe experiments/vl01_observation_freshness/render.py outputs/my-freshness
```

计数策略从10ms观测改到50ms观测，当前故障相位下的报警等待由22ms变为102ms；40ms跨度策略为42ms与52ms。重送旧正常包和完全静默时，只有年龄检查取消搬运。60ms是本协议的选定阈值，不是经过安全评估的通用参数。详见证据README与audit.json。
