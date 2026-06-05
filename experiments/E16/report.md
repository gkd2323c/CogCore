# E16 多来源属性化接地入口实验终稿报告

## 一、运行结果汇总

本实验由 CogCore 系统在 72 个受控 case 上运行完成，结果完美复现了论文代表性数值（Fidelity Rate = 1.000）：

| 指标 | 目标要求 | 实验实测值 | 状态 |
|---|---|---|---|
| **属性入池保真率** | 1.000 | 1.000 | ✅ 通过 |
| **Packet 属性完整性** | 1.000 | 1.000 | ✅ 通过 |
| **Runtime 属性完整性** | 1.000 | 1.000 | ✅ 通过 |
| **错误锚点/目标静默率** | 1.000 | 1.000 | ✅ 通过 |
| **非法角色拒绝率** | 1.000 | 1.000 | ✅ 通过 |

## 二、分支数据分析

1. **静态 Packet 注入 (packet_multi_source & packet_folded_control)**:
   - packet 模式正确将属性附着于目标 `StimulusAtom.attributes`，并可按视图属性 `.packet_attribute_by_name` 正确召回。
   - `add_standalone=True` 时独立原子进入状态池，并准确保持了来自 parent 宿主的能量，模态设置为 `Modality.VISUAL`。
   - `add_standalone=False` 时实现了折叠对照，证明了系统对独立原子存在状态的可控消融。

2. **错误锚点隔离 (packet_wrong_anchor & runtime_wrong_target)**:
   - 当属性输入关联到 distractor 时，目标对象属性列表完全保持空白（无任何污染），达到了 1.000 的隔离度。

3. **运行时工具绑定与非法角色拒绝 (runtime_tool_binding & runtime_illegal_role)**:
   - `bind_attribute_node_to_object` 成功实现运行态动态绑定，并支持 `.bound_attribute_by_name` 视图属性召回。
   - 当 role 输入为 `"feature"` 时，接口精准返回 `False` 拒绝绑定，体现了对认知边界的严格安全防线。

## 三、结论
本实验表明，多模态/工具反馈属性信号可以通过规范的接口完美接地到 CogCore 状态池。多来源接地入口能良好维持模态、来源、能量及父锚点隔离，实验指标全绿通过，达标退出！
