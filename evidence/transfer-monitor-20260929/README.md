# E3 原始证据 · 2026-09-29

运行源代码 c3208d9d475534efbaab3fbe607f7c1276ed9af7，开始时间和环境见manifest.json。27回合均完成记录，无MuJoCo warning。

这是固定场景、固定初始条件的确定性对照；重复用于核对可重复性，不给出泛化成功率。原始输出没有覆盖旧E1/E2记录。

summary.json包含全部条件，audit.json独立核对CSV和状态前缀。monitor-comparison.png由审计脚本从CSV绘制；两段视频由render.py把50Hz坐标投影为XZ平面，不是三维场景渲染。每个图形标记表示一个中心坐标，不表达尺寸、旋转或完整碰撞几何。media.json说明时间采样和hash。

当前会话OpenGL三维渲染失败；不影响无图形物理计算。完整states.jsonl仍可用于后续重放。测试记录见validation.txt，复现说明见../../experiments/vl01_transfer_monitor/README.md。
