# 二维力控执行器：调参、绕障与观测延迟

这是第二个最小 MuJoCo 场景：两个滑动自由度、单位球形执行器、可关闭障碍物、每轴 ±5 N。不是机械臂、移动机器人、抓取、视觉或真机系统。固定场景不升级 VL01 或 M4/M5。

冻结协议 `protocol.json`，依次比较 PD 阻尼与质量、中心线/带余量绕障、延迟带噪观测与常速度外推。最后0.3秒内位置误差<15mm且速度<40mm/s才算完成；瞬间经过目标不算。噪声组3个种子是固定敏感性样本，不代表总体成功率。外推使用仿真速度，是偏乐观的传感器假设。

仓库根目录安装已有 requirements-lock.txt 后执行（输出目录必须不存在）：
```sh
python experiments/planar_reach/run.py --out outputs/planar-reach
python experiments/planar_reach/audit.py outputs/planar-reach
python experiments/planar_reach/plot.py outputs/planar-reach
```

每2ms保留真值、力、观测捕获时刻和接触，20ms更新控制。三个图来自CSV；没有插值生成实验、模型API或后验删除失败。manifest记录原始文件及源码哈希。run前提交冻结代码，证据另一次提交。
