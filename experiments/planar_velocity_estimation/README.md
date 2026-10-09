# 位置噪声与速度估计

沿用 planar_reach 的 2 自由度力控场景，禁用障碍。三种观测：时间戳对应的真值速度（仅作乐观参考）、位置差分、时间常数 60ms 的指数平滑差分。所有方法使用相同延迟位置，不额外外推。

```sh
python -m pip install -r requirements-lock.txt
python -m unittest discover -s experiments/planar_velocity_estimation -p 'test_*.py'
python experiments/planar_velocity_estimation/run.py
python experiments/planar_velocity_estimation/audit.py
```

54 回合，固定参数、不看结果调参。轨迹按每个 2ms 物理步写入 csv.gz（无损压缩），包含采样时间、观测、估计速度、原始与限幅控制力、物理位置/速度。独立审计重算估计器、控制力与最后 300ms 的稳定性判定，不能用终点位置一个数替代完整验收。

`protocol.json` 先于运行提交，manifest 记录代码提交、环境及完整源文件/证据哈希。速度 RMSE 是收到样本时，估计速度相对**采样时刻**真值的误差，不是相对当前时刻；oracle 在此指标天然为零，延迟控制仍可能失败。

本例没有机器人手臂、视觉、ROS2、学习策略或硬件结果，也没有完成整个 VL01 里程碑。AI 辅助实现和整理，结论以真实仿真轨迹为准。
