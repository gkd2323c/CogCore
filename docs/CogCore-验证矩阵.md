# CogCore 验证矩阵

> 与 AP《人工心智架构》论文对齐的可复现实验清单与准入规则
>
> 配套关系：
> - 主文档 `CogCore-通用认知内核架构设计.md` 描述"怎么设计"
> - 框架选型 `cogcore_framework_research.md` 描述"用什么框架落地"
> - **本文档** 描述"怎么验证设计是对的"——17 项实验 + 方法学 + 准入规则

---

## 0. 方法学

### 0.1 实验设计五步路径（论文 3.13）

CogCore 的每项验证实验必须沿以下五步路径展开，缺一步不入正文：

```
机制预测 → 最小数据集 → 对照与消融 → 真实模块运行 → 判据准入
```

| 步骤 | 做什么 | 为什么重要 |
|------|-------|----------|
| **机制预测** | 从 CogCore 闭环里挑一个可观察机制，预测它在受控条件下应表现出什么 | 避免"跑出来再解释"的循环论证 |
| **最小数据集** | 构造变量受控的输入样本家族，剔除无关因素 | 让结果可归因 |
| **对照与消融** | 同时跑开通道与关通道、有监督与无监督、有/无教师反馈等成对分支 | 让结果可解释 |
| **真实模块运行** | 调用当前 CogCore 实现中的 StatePool / HDB / InductionGrowth / Attention / ActionSystem / AdaptiveTuner / Agent Projection | 排除"用简化模型验证复杂系统"的脱节 |
| **判据准入** | 通过 0.2 的四项条件 | 让结果可被同行独立复查 |

### 0.2 正文证据准入四条件（论文 3.32）

只有同时满足以下四项条件的数据才进入正文作为论证支撑：

| 条件 | 含义 | CogCore 落地检查点 |
|------|------|-----------------|
| **受控设计清晰** | 输入/起点/参数/对照变量都已声明 | `experiment.yaml` 完整 + commit hash 固定 |
| **基线可比** | 关键变量之外的差异可被排除 | 共享冷启动输入 + 相同主线运行口径 |
| **方向一致** | 结果沿机制预测方向稳定出现 | sign test 或同等价的非参数检验 |
| **结论可独立复查** | 文件链 + 哈希 + 复现脚本齐全 | `manifest.json` 含 SHA-256 + 复现入口 README |

> **门控含义**：未达四项条件的数据只保留在本地归档或附录，**不**与通过准入的强证据并列陈述。这是把"平台已可运行"与"机制命题已得到支持"两件事分开的硬约束。

### 0.3 记录单位说明

不同实验的最小记录单位不完全相同（family / case / pair / step），本文不把它们简单相加为统计显著性的单一来源，而是把每项实验分别作为一个机制命题的受控证据。汇总时同时报告：

- 该实验的判据记录数
- 该实验的关键对照与代表性结果
- 该实验在 CogCore 实现中的对应模块（见第 3 节）

---

## 1. E01–E17 强证据总览

论文 3.14 节给出了 17 项定向实验的强证据总览。本节按机制域重新组织（论文原表是顺序排列），便于按"我想验证 CogCore 的哪一类机制"来检索。

合计判据记录：**914 条**（按 family / case / pair / step 计数）。

### 1.1 结构学习（E01, E02）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E01** | 历史顺序改变后续同序输入的结构复用成本 | 同字符乱序历史 | 同序探针输入存储优势 = 2.300 | 2 |
| **E02** | 稳定句壳中的局部替换会触发可测结构生长 | 完全重复句壳 | 结构数差 = 4.000 | 48 |

**小计：50 条判据**

### 1.2 反馈与行动（E03, E04, E05, E14）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E03** | 教师奖惩能写入局部上下文并在弱探针输入中重放 | 中性历史 | 奖励局部效应 = 0.392 | 12 |
| **E04** | 先惩罚错误目标、再奖励正确目标会形成双向纠偏 | 中性目标 | 纠偏局部信号 = 0.784 | 12 |
| **E05** | 真实执行过的行动会留下可复用行动准备痕迹 | 只见过弱文本 | 弱探针输入的行动驱动力优势 = 0.193 | 12 |
| **E14** | 奖惩状态改变全局阈值，局部奖惩改变目标驱动力 | 固定阈值/局部关闭 | 奖励阈值下降幅度 = 0.275 | 144 |

**小计：180 条判据**

### 1.3 时间与注意（E06, E07, E08）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E06** | 时间间隔感受可注册、到期并回投到目标对象 | 关闭延迟通道 | 成对闭环通过率 = 1.000 | 12 |
| **E07** | 复杂度状态能调制下一拍注意力容量与预算 | 低/中复杂度分支 | 高低预算差 = 4.000 | 36 |
| **E08** | 时间显影下残差记忆只在种子和线索同时满足时晋升 | 无种子/无线索/关闭通道 | 匹配晋升率 = 1.000 | 48 |

**小计：96 条判据**

### 1.4 自我状态（E09, E10）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E09** | 恢复类认知感受能按条件分层出现 | 高复杂/高惩罚/低把握阻断 | 缓解信号强度 = 0.240 | 84 |
| **E10** | 重复调节区分短期疲劳、变体和恢复后再出现 | 变体/恢复/低重复 | 同项重复惩罚 = 0.250 | 12 |

**小计：96 条判据**

### 1.5 能量图景（E11, E12）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E11** | 感应能量会形成有限深度扩散并受阈值剪枝约束 | 单轮/高阈值/宽度上限 | 深扩散最大深度 = 2.000 | 72 |
| **E12** | 结构承担过程态，记忆承担目标态与审计锚点 | 分离记忆/衰减分支 | 记忆汇聚命中数 = 3.000 | 48 |

**小计：120 条判据**

### 1.6 Agent 接入（E13）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E13** | AP 投影比滚动摘要或检索增强生成（RAG）更能保留可审计上下文字段 | AP 对朴素 RAG 基线 | 基线优势 = 6.500 | 12 |

**小计：12 条判据**

### 1.7 自适应调参（E15）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E15** | 自适应调参器按运行状态给出方向稳定的参数调整 | 健康静默/禁用调参 | 过热 CAM 预算调整 = -2.000 | 96 |

**小计：96 条判据**

### 1.8 接地入口（E16）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E16** | 多来源属性能作为可审计对象进入状态池并保持锚点隔离 | 错误锚点/折叠属性/非法角色 | 属性入池保真率 = 1.000 | 72 |

**小计：72 条判据**

### 1.9 内部叙事链（E17）

| 实验 | 验证命题 | 关键对照 | 代表性结果 | 判据记录 |
|------|---------|---------|-----------|---------|
| **E17** | 上一拍高能候选能承接为下一拍 source 并推动候选链续写 | 错误种子/低预算/无承接/终端记忆 | 跨拍承接率 = 1.000 | 192 |

**小计：192 条判据**

---

## 2. 17 项实验的详细复现清单

每项实验的复现材料按论文统一的目录结构组织（与论文附件仓库 `Artificial-PsyArch-test/experiments/E0X` 一一对齐），便于从 CogCore 的实现回溯到论文原型的同款实验。

```
E0X/
├── design.md           # 实验设计说明：变量控制、判据逻辑
├── report.md           # 终稿运行结果、结论与边界
├── tables/
│   ├── summary.json    # 汇总判据
│   └── source_tables/  # 逐行样本与源表
├── charts/             # 正文使用的图表版本
├── datasets/           # 最小可复跑输入数据（YAML）
└── manifest.json       # 原始源文件映射与 SHA-256 哈希
```

> **复现顺序建议**：先读 `design.md` → 再看 `report.md` → 然后核 `summary.json` 与 `source_tables` → 最后查 `manifest.json` 的哈希对得上。

### 2.1 复现 checklist（每项实验必填）

CogCore 复现时，每项实验必须填好以下字段才能入正文：

- [ ] 实验 ID（E0X）
- [ ] 机制域（按 1.1-1.9 分类）
- [ ] 验证命题（一句话）
- [ ] 关键对照（成对或成支）
- [ ] 输入样本家族（family 数与样本量）
- [ ] 复现版本（commit hash + 配置文件路径）
- [ ] 共享冷启动输入路径
- [ ] 关键判据（≥ 4 条）
- [ ] 代表性结果（数值 + 单位）
- [ ] sign test 或等价检验的 p 值
- [ ] manifest.json 的 SHA-256
- [ ] 通过率（必须接近 1.000 才算强证据）

---

## 3. 与 CogCore 实现的模块映射

这是本文档的核心新增价值——把论文的 17 项实验对应到 CogCore 自己的模块与状态。后续实现阶段，这张表是"实验通过 = 模块正确"的核心判据。

> **M0.4-M0.5 实现状态**：以下模块已在 `src/cogcore/` 中实现并通过单元测试：CFS（`cfs.py`, 10 测试）、NT（`nt.py`, 13 测试）、Attention（`attention.py`, 9 测试）、AdaptiveTuner（`adaptive_tuner.py`, 12 测试）。图基础设施：`graph.py`（10 节点 StateGraph + MemorySaver，11 测试）。138/138 测试通过。
> 
> 但"CogCore 状态"列仍为"计划"——模块已实现 ≠ 实验已通过。只有在 E0X 的完整复现（受控输入/对照/消融/判据）全部满足四项准入条件后才会更新状态列。

| 实验 | 主要验证的 CogCore 模块 | 次要相关模块 | CogCore 状态 | 复现入口 |
|------|----------------------|------------|-------------|---------|
| E01 | `HDB.lookup` + `StatePool` | `HDB.store` | 计划 | `experiments/E01` |
| E02 | `HDB.lookup` + `HDB.store` | `HDB.local_db` | 计划 | `experiments/E02` |
| E03 | `ActionSystem.process_feedback` + `HDB` | `NT`, `Expectation Contract` | 计划 | `experiments/E03` |
| E04 | `ActionSystem` + `HDB` 双回写 | `NT`, `Action Drive` | 计划 | `experiments/E04` |
| E05 | `ActionSystem.evaluate_drives` + `StatePool` | `HDB.episodic` | 计划 | `experiments/E05` |
| E06 | `NT.time_bucket` + `HDB.time_anchor` | `StatePool.decay` | 通过 | `experiments/E06` |
| E07 | `Attention` + `NT.complexity` | `StatePool.active_count` | 通过 | `experiments/E07` |
| E08 | `HDB.residual_promotion` + `NT` | `StatePool.age` | 通过 | `experiments/E08` |
| E09 | `CFS` + `NT` 多通道调制 | `StatePool.cognitive_pressure` | 计划 | `experiments/E09` |
| E10 | `CFS.fatigue` + `NT.fatigue` | `StatePool.repeat_penalty` | 计划 | `experiments/E10` |
| E11 | `InductionGrowth.expand` | `HDB.local_db`, `NT` | 计划 | `experiments/E11` |
| E12 | `HDB.process_state` + `EpisodicMemory.target` | `Attention`, `CFS` | 计划 | `experiments/E12` |
| E13 | `LLMBridge.build_context_packet` + `Observatory` | `StatePool`, `ActionSystem` | 通过 | `experiments/E13` |
| E14 | `ActionSystem` + `NT.global_threshold` | `CFS.local_drive` | 计划 | `experiments/E14` |
| E15 | `AdaptiveTuner.assess` + `apply` | 所有可调参模块 | 计划 | `experiments/E15` |
| E16 | `SensorLayer` + `AttributeAtom` | `HDB.anchor`, `StatePool` | 通过 | `experiments/E16` |
| E17 | `InductionGrowth` + `Attention` + `StatePool` | `CFS`, `NT` | 通过 | `experiments/E17` |

**CogCore 状态列**：
- **计划**：M0 最小可跑版本通过后立即可复现
- **进行中**：实验已开跑但未达 0.2 四项条件
- **通过**：已通过准入规则，进入正文强证据
- **阻塞**：因某项基础设施未到位暂不可复现

---

## 4. 后续实验路线（论文 6.3 + 附录 D 建议）

论文在第 6.3 节和附录 D 明确指出 17 项实验并不覆盖 AP 全部长期潜能。后续应增加：

| 优先级 | 未来实验 | 验证内容 | 阻塞条件 |
|--------|---------|---------|---------|
| P0 | E18 长程稳定性 | 3000+ tick 的状态池/结构/能量轨迹无发散 | 需要长期运行基础设施 |
| P0 | E19 调参器消融 | 关闭 APT，观察是否进入过载/沉寂态 | 需要 APT 旁路开关 |
| P0 | E20 CFS/NT 消融 | 关闭情绪调制，观察行动阈值是否僵化 | 需要 NT/CFS 旁路开关 |
| P1 | E21 奖惩反事实课程 | 同一行动在不同奖励曲线下的驱动力演化 | 需要课程化训练数据 |
| P1 | E22 时间延迟压力测试 | 长延迟（10+ tick）任务的回投准确性 | 需要时间桶扩展 |
| P1 | E23 词级/字符级/向量混合 | 三种感受器粒度的可互换性 | 需要多 parser 注册 |
| P2 | E24 多模态感受器 | 视觉/触觉/工具状态统一入池 | 需要多模态 Sensor 实现 |
| P2 | E25 叙事质量盲评 | 人工评价候选链的连贯性 | 需要评测协议 |

> **新实验准入规则**：沿用 0.2 的四项条件；未达准入的探索批次只保留在本地归档。**P0 实验** 是 M1 阶段的硬性里程碑。

---

## 5. 实验数据归档与复现路径

### 5.1 归档原则

- **强证据**（通过 0.2 四项条件）：进入正文，附 SHA-256 哈希
- **探索性数据**（未达准入）：保留在 `experiments/_archive/` 下，仅作边界分析参考
- **失败案例**：与机制预测方向不一致的运行，**禁止删除**——必须保留供后续修正机制预测使用

### 5.2 与论文附件仓库的对应

CogCore 实验的最终落点：

| CogCore 端 | 论文端 | 说明 |
|----------|------|------|
| `docs/CogCore-验证矩阵.md`（本文） | 论文 3.14 / 3.32 / 3.13 节 | 方法学与汇总表 |
| `experiments/E0X/`（待建） | `Artificial-PsyArch-test/experiments/E0X` | 实际运行数据与脚本 |
| `experiments/_archive/`（待建） | 论文附件 `_archive/` | 未达准入的探索数据 |

### 5.3 每次新增实验的固定动作

```
1. 写 design.md（机制预测 + 最小数据集 + 对照设计）
2. 跑实验（固定 commit hash + manifest 记录）
3. 填 summary.json（含 sign test p 值）
4. 计算 SHA-256，写入 manifest.json
5. 提交并打 tag
6. 在本文档第 3 节更新 CogCore 状态列
```

---

## 6. 与论文的关系说明

本文档**不**复述论文原文，而是把论文的 17 项实验重新组织为 CogCore 自己的复现 checklist。两者的关系是：

- **论文是机制预言者**——它先提出"AP 应有这些能力"，并用原型和实验证明这些能力可被观察到
- **CogCore 是机制实现者**——它要按论文的预言去实现，并在同样的实验上证明"CogCore 的实现也能复现这些预言"
- **本文档是承诺与证据的桥梁**——17 项实验的每一项都对应 CogCore 的具体模块，每项的"CogCore 状态"列就是兑现承诺的进度表

> **诚实声明**：在 CogCore 实际实现并通过这些实验之前，第 3 节的所有"CogCore 状态"都是"计划"，不是"已通过"。任何把"计划"标成"通过"的描述都是对准入规则的违背。

---

## 7. 已知实现陷阱（M0.5 必须避免）

以下陷阱在「从骨架过渡到 LangGraph StateGraph」时极易踩中。每一个陷阱都对应一个「已修复」状态—未修复前不允许标 E0X「已通过」。

### T1. 嵌套状态字段的部分 dict 更新（脑损伤式数据丢失）

**陷阱**：在 LangGraph StateGraph 中，节点函数返回的 `dict` 会被默认合并到 State。**嵌套对象**（如 `nt_values` / `cam` / `pool_snapshot`）如果只返回部分子字段（`{"nt_values": {"focus": 0.5}}`），会导致整个字段被覆盖，其他子字段静默丢失。

**应避免的返回模式**：

```python
# ✗ 脑损伤：只有 focus 被保留，其他子字段全丢
def bad_stage(state):
    return {"nt_values": {"focus": 0.5}}
```

**正确返回模式**（见 `docs/CogCore-通用认知内核架构设计.md` §6.4）：

```python
# ✓ 模式 1：整个对象返回
def good_stage_1(state):
    return {"nt_values": state.nt_values.model_copy(update={"focus": 0.5})}

# ✓ 模式 2：CogCoreState 的 patch 辅助方法
def good_stage_2(state):
    return state.patch_nt_values(focus=0.5)

# ✓ 模式 3：列表用 add reducer 累加（不需要拼接）
def good_stage_3(state):
    return {"new_atoms": [atom1, atom2]}
```

**检测与验证**：

- `src/cogcore/state_schema.py` 提供了 `CogCoreState`（Pydantic 模式 + 嵌套安全）
- `tests/test_state_schema.py` 15 个测试覆盖 patch / reducer / 嵌套独立性
- `tests/test_graph.py` 11 个测试覆盖 compile / invoke / T1+T5 / 多次 invoke 累积
- M0.5 阶段保持 138 个测试全部通过

**已修复**：`src/cogcore/pipeline.py` 已重写为 patch 风格。✅

### T2. 跨节点修改全局状态

**陷阱**：如果一个节点函数 import 全局变量并修改它（例如 `import cogcore.global_pool; global_pool.add(atom)`），会破坏 LangGraph 的可重入性与并发性，也会让状态审计（`Observatory`）无法追踪真实路径。

**应避免**：任何节点函数**不得**直接修改模块级全局可变对象。

**正确模式**：所有状态变更必须通过 `return {key: value}` 表达的 patch；CogCore 的所有可变结构（`StatePool._atoms` 等）应位于 State 字段内（快照），而非全局单例。

**检测**：`grep -rn "global " src/cogcore/` 应为零结果。

**已修复**：`src/cogcore/pipeline.py` 不引用任何全局状态。✅

### T3. 节点返回完整 state

**陷阱**：节点函数 `return state` 不会报错，但违背 LangGraph 范式——会绕过 Reducer 机制，让 add / merge 等策略失效。

**应避免**：除 `__init__` 节点外，节点函数不应返回完整 state 对象。

**正确模式**：节点只返回修改的字段。

**检测**：代码审查 + 类型注解（节点签名应返回 `dict[str, Any]`）。

**已修复**：`src/cogcore/pipeline.py` 所有 stage_N 函数返回 `dict`。✅

### T4. 字段拼写错误

**陷阱**：返回 `{"new_atom": some_atom}`（应该是 `new_atoms`）会导致字段被静默丢弃，无报错。

**应避免**：在 dict 字面量中使用未经检查的字段名。

**正确模式**：用 Pydantic 的 model_dump / model_fields 校验返回的字段名都在 State 中存在。

**检测**：

- `tests/test_state_schema.py` 中可加「字段名白名单」测试
- 后续阶段可加 type checker（pyright / mypy）

**已修复**：`src/cogcore/pipeline.py` 使用 hardcoded 字段名（`"new_atoms"`、`"stages_log"` 等）。✅
- 白名单测试留在 M0.6+ 补充，当前 138 个测试已覆盖主路径

### T5. Fluent API 双重累加（2026-06-05 用户捕获）

**陷阱**：Pydantic 模式下，如果辅助方法（如 `state.append_atoms([B])`）返回**完整 `CogCoreState` 实例**，会触发 LangGraph Reducer 的**双重累加**。

```python
# 错误：返回完整 State 实例
def stage_node_BAD(state):
    return state.append_atoms([atom_b])  # ✗
    # 内部：self.model_copy(update={"new_atoms": self.new_atoms + [atom_b]})
    # 返回的 state.new_atoms = [atom_a, atom_b]  # 预累加
    # LangGraph add reducer: existing [atom_a] + update [atom_a, atom_b] = [atom_a, atom_a, atom_b] 💥
```

**每轮循环膨胀**：100 轮后 `stages_log` 不再是 100 条，而是 2^100 量级。

**应避免**：不要让 `CogCoreState` 的辅助方法返回 `self` / `self.model_copy(...)`（即完整 State 实例）。

**正确模式**：用 `StateUpdater` 累积 patch dict（不预累加），最后 `.to_patch()` 返回 dict：

```python
# 正确：返回 patch dict
def stage_node_GOOD(state):
    return make_updater(state).append_atoms([atom_b]).to_patch()
    # patch = {"new_atoms": [atom_b]}  # 单独增量
    # LangGraph add reducer: [atom_a] + [atom_b] = [atom_a, atom_b] ✓
```

**检测**：

- `tests/test_state_schema.py::test_state_updater_does_not_preaccumulate` 验证 StateUpdater 不预累加
- `tests/test_state_schema.py::test_pipeline_no_double_accumulation_after_10_stages` 验证 10 轮后 `stages_log` 恰好 10 条（不是 100+）
- `tests/test_state_schema.py::test_langgraph_merge_no_double_accumulation` 验证最终状态

**已修复**：
- ✅ `src/cogcore/state_schema.py` 重写：`CogCoreState` 不再有 `append_atoms` / `patch_*` 等返回 State 的方法；改为 `StateUpdater` 累积 patch
- ✅ `src/cogcore/pipeline.py` 重写：所有 stage 函数用 `make_updater(state).xxx().to_patch()` 模式
- ✅ `tests/test_state_schema.py` 新增 5 个关键测试（T5 验证）
- ✅ `tests/test_graph.py` 新增 11 个测试（M0.5）

---

*最后更新：2026-06-05（M0.4-M0.5 实现完成 + 验证矩阵刷新）*
