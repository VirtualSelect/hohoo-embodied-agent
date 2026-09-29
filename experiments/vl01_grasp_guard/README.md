# E2：抓取确认后再搬运

复用 VL01 的场景、轨迹、接触与放置判据。唯一控制差异：guarded 在 4 秒抬升结束后，用最近 0.2 秒、50 Hz 的 10 条记录检查方块中心 z > 0.1 m 且每条都有两侧指垫接触；窗口不足、过期或不连续也拒绝。

拒绝后保持当前执行器目标 0.6 秒并终止本回合，不再执行 transfer/lower/release。baseline 只记录同一判断，不应用。不是重新抓取、真机急停或视觉反馈。

0/25/50 mm × baseline/guarded × 3 次 = 18 回合。全部确定性同初始状态，重复仅检查可复现性。状态来自模拟器真值，不等同于真实传感器可观测量。接触检测也不等于夹持力判定。

## 运行

在仓库根目录，使用原有 requirements-lock.txt 环境：

    .venv/Scripts/python.exe -m unittest discover -s experiments/vl01_grasp_guard -p "test_*.py"
    .venv/Scripts/python.exe experiments/vl01_grasp_guard/run.py --out evidence/my-guard-run --render
    .venv/Scripts/python.exe experiments/vl01_grasp_guard/audit.py evidence/my-guard-run

输出目录必须不存在。视频仅每组第 1 回合，25 FPS；CSV 和 qpos/qvel/ctrl 保存状态 50 Hz；物理步进 500 Hz。原实验文件不修改。审计独立重算判定，并验证前 4 秒完全相同、baseline 与旧实验完全相同、成功组全轨迹相同。通过原始状态文件可使用原实验 replay.py 重放，但其场景 hash 清单格式不同；本次以新 CSV 审计和实际执行视频为准。

结果在实际运行后补充。
