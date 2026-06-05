# E11 感应能量有限深度扩散受阈值剪枝约束 — 实验设计说明

## 1. 机制预测
感应能量沿 HDB 的结构链（local_db 连线 + transition_weight）扩散时，
传播深度受两个参数约束:
- **阈值 (threshold)**: 能量低于阈值的候选被剪枝
- **宽度上限 (width)**: 每层最多探索的并行分支数

预测: 低阈值 + 宽上限条件下扩散更深，但因能量逐层衰减 (w^n)，
深度被限制在有限值（目标 2.000）。

## 2. 变量控制与对照
- **链式结构**: 5 个节点 A→B→C→D→E，权重统一 0.9
- **参数扫描**: 8 个 threshold (0.01~0.85) × 9 个 width (1~9) = 72 cases
- **深扩散条件**: threshold ≤ 0.15 且 width ≥ 4
- **浅扩散条件**: threshold ≥ 0.40 或 width ≤ 2

## 3. 输入样本
用 `store` 按序列 "alpha/beta/gamma/delta/epsilon" 创建 5 个独立 Structure，
再通过 `local_db` 和 `set_transition_weight` 布线为链。

## 4. 判据
- 深扩散平均最大深度 = 2.000
- 浅扩散平均深度 < 深扩散平均深度（方向性验证）
