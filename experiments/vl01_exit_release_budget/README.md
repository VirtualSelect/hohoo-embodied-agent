# E8–E10 / 从报警到退出、释放与有限恢复

复用VL01原场景，32个确定性物理回合：E8五条件×三退出动作；E9五条物理轨迹同时计算两种观察式完成规则；E10四条件×三恢复预算策略。

```sh
python -m unittest discover -s experiments/vl01_exit_release_budget -p "test_*.py"
python experiments/vl01_exit_release_budget/run.py --out evidence/NEW-RUN
python experiments/vl01_exit_release_budget/audit.py evidence/NEW-RUN
```

环境沿用Python3.12、MuJoCo3.3.7、NumPy2.2.6；不安装其他模拟器。运行前冻结协议与代码提交。输出禁止覆盖。控制器只修改actuator目标和协议规定的立方体外力，不修改qpos传送物体。

E8的松爪后退是待测退出动作，不称作安全恢复；E9不影响控制器，单帧与持续窗口在同一物理轨迹评分；E10仍只监测搬运阶段，冷却会改变绝对故障窗口下的暴露时长。完整机器人任务安全、真实硬件与泛化成功率均未验证。
