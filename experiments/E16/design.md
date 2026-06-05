# E16 多来源属性化接地入口的实验设计说明

## 1. 机制预测与目标
外部多模态感受器、工具状态及传感器生成的属性信号应当保留完整的来源（Source）、模态（Modality）、能量（Energy）及父锚点（Parent）关系。通过实现 StatePool.apply_stimulus_packet 与 StatePool.bind_attribute_node_to_object 两个接地入口，保证这部分属性结构不必退化为一段文字描述，而是以独立且绑定的刺激元形式进入认知状态池，同时通过严格的 role 类型限制（拒绝非 attribute 角色）和锚点检测防止属性在不同实体间交叉污染。
期望预测：在受控条件下，系统能够稳定隔离干扰对象并实现 1.000 的属性入池保真率。

## 2. 变量控制与对照系统
- **packet 多来源绑定**: 将外部输入的静态属性注入目标锚点，并注册独立属性原子到状态池，作为多模态输入基线。
- **packet 错误锚点**: 属性指向干扰对象，目标对象保持静默（用于隔离性检测）。
- **packet 折叠对照**: 只在锚点内记录属性，而不作为独立原子入池。
- **runtime 工具绑定**: 模拟运行期工具反馈并执行动态属性绑定。
- **runtime 错误目标**: 运行时属性绑定到干扰对象，目标对象不受污染。
- **runtime 非法角色**: 将 role 设置为非 "attribute"（例如 "feature"），验证接口的类型拒绝边界。

## 3. 输入样本家族
设计了 12 个同构家族（F01–F12），各自使用独特的属性名、属性值、模态和来源组合，结合 6 个控制分支共 72 个 case 进行穷尽测试。

## 4. 判据与指标
- **属性入池保真率 (attribute_pool_fidelity_rate)**: 72 个 case 必须全部通过（Target = 1.000）。
- **Packet 属性完整性 (packet_fidelity_rate)**: 独立原子的入池、模态、来源、值、能量和 parent 全保真（Target = 1.000）。
- **Runtime 属性完整性 (runtime_fidelity_rate)**: 运行时原子的模态、来源、值、能量和 parent 全保真（Target = 1.000）。
- **错误锚点静默 (wrong_anchor_silent_rate)**: 当指向 distractor 时，目标对象必须完全不受污染（Target = 1.000）。
- **非法角色拒绝 (illegal_role_rejected_rate)**: 伪装角色被接口拒绝（Target = 1.000）。
