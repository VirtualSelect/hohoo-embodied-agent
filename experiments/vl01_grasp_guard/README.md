# E2：抓取确认后再搬运

复用 VL01 的场景、轨迹、接触与放置判据。唯一控制差异：guarded 在 4 秒抬升结束后，用最近 0.2 秒、50 Hz 的 10 条记录检查方块中心 z > 0.1 m 且每条都有两侧指垫接触；窗口不足、过期或不连续也拒绝。

拒绝后保持当前执行器目标 0.6 秒并终止本回合，不再执行 transfer/lower/release。baseline 只记录同一判断，不应用。不是重新抓取、真机急停或视觉反馈。

0/25/50 mm × baseline/guarded × 3 次 = 18 回合。全部确定性同初始状态，重复仅检查可复现性。状态来自模拟器真值，不等同于真实传感器可观测量。接触检测也不等于夹持力判定。

## 运行

在仓库根目录，使用原有 requirements-lock.txt 环境：

    .venv/Scripts/python.exe -m unittest discover -s experiments/vl01_grasp_guard -p "test_*.py"
    .venv/Scripts/python.exe experiments/vl01_grasp_guard/run.py --out evidence/my-guard-run --render
    .venv/Scripts/python.exe experiments/vl01_grasp_guard/audit.py evidence/my-guard-run

输出目录必须不存在。视频仅每组第 1 回合，25 FPS；CSV 和 qpos/qvel/ctrl 保存状态 50 Hz；物理步进 500 Hz。原实验文件不修改。审计独立重算判定，并验证前 4 秒完全相同、baseline 与旧实验完全相同、成功组全轨迹相同。新 replay.py 校验记录中的场景 hash 与 MuJoCo 版本，以 50 FPS 重放保存状态；重放不是一次新的试验。

## 2026-09-29 实际结果

源代码先冻结于 139c89a；18 回合保存在 evidence/grasp-guard-20260929，8 项边界测试通过。
独立审计确认：9 个前缀轨迹完全相同，9 个 baseline CSV 与旧版实验完全相同，3 个成功条件的整个配对轨迹完全相同。

| 偏移 | baseline 完成 | guarded 完成 | guarded 取消搬运 | baseline 判定后水平路程 |
| --- | --- | --- | --- | --- |
| 0 mm | 3/3 | 3/3 | 0/3 | 268.330 mm |
| 25 mm | 0/3 | 0/3 | 3/3 | 246.221 mm |
| 50 mm | 0/3 | 0/3 | 3/3 | 224.722 mm |

拒绝组保持 0.6 秒后结束，总仿真时长 4.6 秒；baseline 9.2 秒。拒绝组判定后水平路程约 10^-8 mm，为数值残余。图中的位移与表中的累计路程是不同指标；此轨迹接近直线，因此数值接近。不声称提高任务成功率或真实硬件安全性。

重放：

    .venv/Scripts/python.exe experiments/vl01_grasp_guard/replay.py evidence/grasp-guard-20260929/guarded-025mm-run-1/states.jsonl --out outputs/guard-replay.mp4

[配套文章](https://huhohoo.com/docs/embodied-ai/mujoco-grasp-guard)
