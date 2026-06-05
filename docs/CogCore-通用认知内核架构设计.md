# CogCore：通用认知内核架构设计文档

> 基于 Artificial PsyArch (AP) 论文核心思想设计的通用智能体认知内核

---

## 1. 系统定位与设计哲学

### 1.1 CogCore 是什么

CogCore 是一个通用认知内核（Universal Cognitive Kernel），不绑定具体应用场景，而是作为底层认知层接入各种上层 Agent 系统。它承担四件事：长期状态维护、可解释记忆、内源感受调制和行动反馈学习。上层系统（LLM、工具链、对话界面）负责语义解释、语言表达和工具调用。

这个分工来自论文的核心判断：LLM 擅长即时生成和语义理解，但在长期状态、记忆连续性和行为调制上有结构性缺陷。CogCore 补的就是这块。

### 1.2 设计原则

**白箱优先。** 每个认知对象都记录来源、能量、匹配路径和处置事件，任何一步变化都可以追溯。不搞黑箱。

**闭环而非流水线。** 行动后果、未处理完的残差、感应目标都回写状态池，影响后续认知。输入-处理-输出不是单程的，而是首尾相接。

**能量即货币。** 所有认知对象用统一的能量体系度量重要性。实能量标记现实证据，虚能量标记内源预测，认知压标记现实与预期之间的张力。

**可衰减、可竞争、可召回。** 状态池不是只增不减的数据库，而是一个动态场——对象会衰减、会竞争注意力、也可以在合适条件下被重新召回。

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    上层 Agent 系统                        │
│  (LLM 解释层 / 对话界面 / 工具链 / 安全审查)              │
└──────────┬──────────────────────────────┬───────────────┘
           │ 外源输入 (stimuli packets)     │ 行动结果 / 教师反馈
           ▼                              ▲
┌─────────────────────────────────────────────────────────┐
│                     CogCore 认知内核                      │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ 感受器层  │→│  状态池   │→│ 注意力    │              │
│  │ Sensors  │  │StatePool │  │Attention │              │
│  └──────────┘  │ 能量账本  │  │  & CAM   │              │
│                └────┬─────┘  └────┬─────┘              │
│                     │              │                     │
│         ┌───────────┼──────────────┼──────────┐        │
│         ▼           ▼              ▼          ▼        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐   │
│  │  HDB     │ │ 感应生长  │ │认知感受   │ │行动节点  │   │
│  │ 查存一体  │ │Induction │ │  CFS     │ │ Action  │   │
│  │          │ │ Growth   │ │  + NT    │ │ Nodes   │   │
│  └──────────┘ └──────────┘ └──────────┘ └─────────┘   │
│         │           │              │          │        │
│         └───────────┴──────────────┴──────────┘        │
│                        │                                │
│              ┌─────────▼─────────┐                     │
│              │  自适应调参器       │                     │
│              │  Adaptive Tuner   │                     │
│              └───────────────────┘                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 核心数据结构

### 3.1 刺激元（StimulusAtom）

系统中所有可参与认知的最小对象。

```
StimulusAtom:
  id:           UUID            # 全局唯一身份
  source:       Enum            # EXTERNAL(外源) | INTERNAL(内源) | ACTION(行动) | FEELING(感受)
  content:      Any             # 载荷内容（文本、向量、结构化数据）
  modality:     str             # "text" | "visual" | "audio" | "tool_state" | ...
  energy:
    real:       float           # 实能量（来自现实证据的激活强度）
    virtual:    float           # 虚能量（来自预测、联想、记忆的激活强度）
  age_ticks:    int             # 在状态池中存活的认知滴答数
  birth_tick:   int             # 创建时的全局 tick 计数
  trace:
    origin:     str             # 来源描述（哪轮输入、哪个工具返回、哪条记忆）
    matched_structures: list    # 命中过的 HDB 结构 ID
    attention_count: int        # 被注意力选中的次数
    action_events: list         # 关联的行动事件
  attributes:   list            # 属性刺激元列表（见下）
```

### 3.2 属性刺激元（AttributeAtom）

带锚点的刺激元，用于解决属性绑定问题。

```
AttributeAtom:
  anchor_id:    UUID            # 绑定到哪个 StimulusAtom
  attr_name:    str             # "color" | "location" | "time" | "intensity" | ...
  attr_value:   Any             # 属性值
  binding_score: float          # 锚点匹配置信度（0.0~1.0）
```

当两个刺激元进入状态池时，如果属性锚点匹配（比如"红色"的锚点与"苹果"共同出现），binding_score 升高，后续匹配时贡献更大。锚点不完全匹配时仍允许弱匹配但降低贡献。

### 3.3 结构（Structure）

HDB 中保存的经验组织单元。

```
Structure:
  id:           UUID
  index_key:    list            # 索引键（共同部分）
  residuals:    list            # 残差列表（不同部分）
  local_db:     dict            # 局部数据库：{子结构索引键 → 子结构ID}
  energy_stats:
    hit_count:  int             # 被命中次数
    last_hit_tick: int          # 最近一次命中的 tick
    avg_activation: float       # 平均激活强度
  episodic_anchors: list        # 情景记忆锚点 ID 列表
  created_tick: int
  depth:        int             # 在 HDB 树中的层级深度
```

### 3.4 情景记忆（EpisodicMemory）

具体经历的快照，作为审计锚点。

```
EpisodicMemory:
  id:           UUID
  tick_range:   (int, int)      # 经历发生的 tick 区间
  stimuli_snapshot: list        # 当时的刺激元 ID 快照
  action_taken:   str           # 执行的行动
  outcome:        str           # 结果（"reward" | "punishment" | "neutral"）
  feeling_snapshot: dict        # 当时的认知感受快照
  structure_refs: list          # 关联的结构 ID
```

### 3.5 行动节点（ActionNode）

```
ActionNode:
  id:           UUID
  name:         str             # 行动名称（如 "query_weather", "send_reminder"）
  drive:        float           # 当前驱动力
  threshold:    float           # 触发阈值
  source:       Enum            # INNATE(先天规则) | LEARNED(后天习得)
  last_executed_tick: int
  execution_count: int
  reward_history: list          # 历史奖励值
  punishment_history: list      # 历史惩罚值
  tool_mapping:   str           # 对应的外部工具标识
  in_pool:        bool          # 是否已作为刺激元进入状态池
```

---

## 4. 模块设计

### 4.1 感受器层（Sensor Layer）

**职责**：将各种来源的原始输入转化为标准的 StimulusAtom 包。

**接口定义**：

```
SensorLayer:
  ingest(raw_input: Any, modality: str, metadata: dict) -> list[StimulusAtom]
  register_sensor(modality: str, parser: Callable) -> None
  get_supported_modalities() -> list[str]
```

**设计要点**：

感受器层不关心内容含义，只负责标准化。每种模态注册一个 parser，parser 的职责是将原始输入拆分为刺激元并赋予初始实能量。

初始实能量的计算规则：`real_energy = base_energy * salience_factor`。base_energy 是该模态的默认能量（可配置），salience_factor 由 parser 根据输入特征计算（如文本长度、信号强度、用户标记的紧急程度等）。

感受器层还负责注入时间戳（birth_tick）和来源追踪（trace.origin），确保后续所有处理都可以溯源。

---

### 4.2 状态池（State Pool）

**职责**：维护当前认知场，管理所有活跃认知对象的能量衰减、竞争和生命周期。

**接口定义**：

```
StatePool:
  add(atom: StimulusAtom) -> None
  get_all() -> list[StimulusAtom]
  get_by_energy(min_energy: float) -> list[StimulusAtom]
  decay() -> None                    # 执行一轮能量衰减
  cleanup(min_energy: float, max_age: int) -> list[StimulusAtom]  # 清理过期对象
  get_energy_summary() -> EnergySummary
  apply_attention_boost(atom_ids: list[UUID], factor: float) -> None
  apply_inhibition(atom_ids: list[UUID], factor: float) -> None
  get_state_report() -> dict         # 用于可审计的状态快照
```

**能量模型**：

> **论文对齐（AP 附录 B）**：
> - 总能量：E(x) = E_r(x) + E_v(x)，其中 E_r 为现实证据、E_v 为内源预测
> - 衰减：E(t+1) = λ·E(t) + I(t) - D(t)
> - 认知压（按对象）：P(i,t) = |E_r(i,t) - E_v(i,t)|

状态池中每个对象的能量遵循以下动态：

```
E_total(t) = E_real(t) + E_virtual(t)

衰减规则：
  E_real(t+1) = λ_real * E_real(t) + I_external(t)
  E_virtual(t+1) = λ_virtual * E_virtual(t) + I_induction(t) + I_recall(t)

其中：
  λ_real: 实能量衰减系数（默认 0.85）
  λ_virtual: 虚能量衰减系数（默认 0.75，比实能量衰减更快）
  I_external: 外源输入注入的实能量
  I_induction: 感应生长注入的虚能量
  I_recall: 记忆召回注入的虚能量
```

**认知压（Cognitive Pressure）**：

认知压不是某个对象的属性，而是状态池级别的全局信号：

```
P_cognitive = Σ|E_real(hit) - E_virtual(predicted)| / N_active

含义：当前刺激与已有预测之间的总差异，归一化到活跃对象数。
认知压高 → 现实与预期偏差大 → 触发违和感
认知压低且下降 → 预期被验证 → 触发正确感
```

**状态池容量管理**：

状态池有软上限 `max_atoms`（默认 200）。当活跃对象超过上限时，按能量从低到高淘汰，但情景记忆锚点关联的对象有豁免权。自适应调参器可以在过载时主动收紧衰减和注意力预算。

---

### 4.3 全息深度数据库（HDB）

**职责**：保存经验结构，支持"查存一体"——当前刺激进入时，一边尝试命中已有结构，一边根据残差差异决定是否写入新结构。理解和学习发生在同一路径。

**接口定义**：

```
HDB:
  lookup(stimuli: list[StimulusAtom]) -> LookupResult
  store(stimuli: list[StimulusAtom], residual: Any) -> Structure
  get_structure(structure_id: UUID) -> Structure
  get_local_db(structure_id: UUID) -> dict
  get_episodic(anchor_id: UUID) -> EpisodicMemory
  write_episodic(memory: EpisodicMemory) -> None
  decay_unused(max_age_ticks: int, min_hit_count: int) -> int  # 清理长期未命中结构
  get_hdb_report() -> dict   # 结构统计、最近命中、深度分布
```

**查存一体的具体流程**：

```
输入：当前轮刺激元列表 S = [s1, s2, ..., sn]

步骤 1：索引匹配
  用 S 的内容作为查询键，在 HDB 中查找已有结构
  命中集合 H = {struct | struct.index_key 与 S 有共同部分}
  对每个命中结构计算匹配分数：
    match_score = |intersection(index_key, S)| / |union(index_key, S)|

步骤 2：残差计算
  对每个命中结构，计算当前输入与结构索引的差异：
    residual = S - intersection(index_key, S)
  如果 residual 不为空，说明当前输入包含了结构未曾经历的新内容

步骤 3：局部生长
  如果 match_score > growth_threshold（默认 0.3）：
    在命中结构的 local_db 中，以 residual 为键创建或更新子结构
    子结构继承父结构的部分能量统计
  如果 match_score < growth_threshold：
    创建新结构，以 S 的共同部分为索引键，residual 为初始残差

步骤 4：情景锚定
  如果本轮包含行动事件或显著认知感受，写入情景记忆
  情景记忆引用当前命中的所有结构 ID

返回：LookupResult
  matched_structures: list[Structure]   # 命中的结构
  match_scores: dict[UUID, float]       # 每个结构的匹配分数
  new_structures: list[Structure]       # 本轮新建的结构
  residuals_written: int                # 写入的残差数量
  episodic_anchor: UUID | None          # 如果创建了情景记忆
```

**局部索引的关键设计**：

HDB 不是全局平铺的。每个结构有自己的 local_db，保存从该结构出发的下一步可能路径。这意味着"好"在"你好"之后和在"天气好"之后可以是不同的子结构，各有自己的历史统计。系统从当前命中的结构出发，可以直接跳转到相关的局部经验，不需要全局扫描。

---

### 4.4 感应生长（Induction Growth）

**职责**：从状态池中的当前对象出发，沿 HDB 的局部结构展开有限的预测图景。

> **论文对齐（AP 附录 B）**：
> - 感应生长预算：ΔE_v(y) = B(g) · w(y|g) · κ
> - 其中 g 为源结构，y 为目标，w(y|g) 是局部数据库权重，κ 是疲劳/调制因子
> - 形式上：源结构 g 把虚能量按权重分配给目标 y，分配受疲劳、近期性和注意力调制

**接口定义**：

```
InductionGrowth:
  expand(source_atoms: list[StimulusAtom], hdb: HDB) -> list[StimulusAtom]
  get_expansion_report() -> dict  # 展开深度、节点数、剪枝次数
```

**展开规则**：

```
输入：源刺激元列表 source_atoms，HDB 引用

对每个源刺激元 s：
  1. 在 HDB 中查找 s 命中的结构 struct
  2. 遍历 struct.local_db 中的子结构：
     - 子结构获得虚能量：E_virtual = s.E_total * spread_factor * weight
       其中 spread_factor 默认 0.8，weight 是该子结构的历史命中权重
     - 如果子结构还有自己的 local_db，继续下一层展开：
       E_virtual_next = E_virtual * spread_factor（逐层衰减）
     - 展开终止条件：
       a. 到达最大深度 max_depth（默认 3）
       b. 虚能量低于 min_energy（默认 0.05）
       c. 命中情景记忆锚点（已知的完整经历，不再推测）
       d. 总展开节点数超过 budget（默认 50）

输出：所有展开产生的虚拟刺激元列表
  这些刺激元 source = INTERNAL，energy.virtual > 0，energy.real = 0
  它们被注入状态池，参与后续的注意力竞争
```

感应生长本质上是"受控的联想"。它让系统不仅处理当前输入，还能基于历史经验预测接下来可能发生什么。展开深度和能量的逐层衰减防止了无限联想。

---

### 4.5 注意力与当前注意记忆体（Attention & CAM）

**职责**：从状态池中选择少量高价值对象，形成"当前注意记忆体"（CAM），并将其转化为内源刺激回注系统。

> **论文对齐（AP 附录 B）**：
> - 注意力评分：score = f(E, P, R, F, CFS, NT)
> - 其中 E=能量、P=认知压、R=奖惩相关、F=新鲜度、CFS=认知感受、NT=递质调制
> - 论文明确警告：不宜退化成固定 top-N，需要保留多通道加权的可解释性

**接口定义**：

```
Attention:
  select(pool: StatePool, config: AttentionConfig) -> CurrentAttentionMemory
  get_selection_report() -> dict  # 选中了哪些、为什么选中
```

**选择机制**：

注意力不是简单地"选能量最高的 N 个"，而是有预算的能量调制：

```
注意力配置 AttentionConfig:
  budget: int               # 最多选多少个对象（默认 10）
  weights:
    energy: float           # 能量权重（默认 0.3）
    recency: float          # 近因权重（默认 0.2）
    reward_relevance: float # 奖惩相关权重（默认 0.2）
    novelty: float          # 新鲜度权重（默认 0.15）
    feeling_intensity: float# 认知感受强度权重（默认 0.15）

对每个候选对象计算综合得分：
  score = w_energy * normalized_energy
        + w_recency * recency_score（基于 age_ticks 的指数衰减）
        + w_reward * reward_relevance（是否关联历史奖惩）
        + w_novelty * novelty_score（首次出现或低频出现的对象得分更高）
        + w_feeling * feeling_intensity（关联的认知感受强度）

按 score 降序排列，取前 budget 个。

重复抑制：
  如果某个对象在上一轮已经被选中，本轮得分乘以 repeat_penalty（默认 0.5）
  连续选中 3 次后乘以 fatigue_penalty（默认 0.2）
```

**CAM 回注**：

选出的 CAM 对象被转化为内源刺激（source = INTERNAL），以虚能量形式重新注入状态池。这使得被注意到的内容可以继续诱发联想、参与下一轮的感应生长。这是 AP 形成"想法持续发展"的关键回路。

---

### 4.6 认知感受系统（CFS）

**职责**：让系统感知自身的处理状态，产生功能化的感受信号，这些信号可以进入状态池参与后续认知。

**接口定义**：

```
CognitiveFeelingSystem:
  evaluate(pool_state: EnergySummary, hdb_result: LookupResult, 
           action_result: ActionResult | None) -> list[StimulusAtom]
  get_feeling_report() -> dict
```

**感受类型与触发条件**：

```
Disharmony（违和感）:
  触发：cognitive_pressure > pressure_high_threshold（默认 0.7）
  能量：与 cognitive_pressure 成正比
  作用：提高后续注意力对异常对象的敏感度

Correctness（正确感）:
  触发：cognitive_pressure 在一轮内下降幅度 > drop_threshold（默认 0.3）
  能量：与下降幅度成正比
  作用：强化当前匹配路径，降低探索倾向

Anticipation（期待）:
  触发：感应生长展开了包含历史奖励信号的结构路径
  能量：与该路径的历史奖励均值成正比
  作用：提高相关行动节点的驱动力

Pressure（压力）:
  触发：连续多轮 cognitive_pressure 持续高于 medium_threshold
  或：行动节点执行后收到惩罚反馈
  能量：与持续时间或惩罚强度成正比
  作用：通过 NT 系统提高行动阈值，使系统更谨慎

Boredom（厌倦）:
  触发：同一类对象连续被注意力选中超过 repeat_limit
  能量：与重复次数成正比
  作用：抑制该类对象的后续得分，推动探索

Relief（释然）:
  触发：高 cognitive_pressure 后出现 correctness 信号
  能量：与之前的 pressure 峰值成正比
  作用：短暂降低行动阈值，允许更积极的响应
```

所有这些感受信号都被包装为 StimulusAtom（source = FEELING），注入状态池。它们不只是日志——它们会参与下一轮的注意力竞争和感应生长，从而影响系统的后续行为。

---

### 4.7 情绪递质系统（NT - Neurotransmitter System）

**职责**：提供比认知感受更慢、更全局的调制信号，影响多个系统参数。

**接口定义**：

```
NeurotransmitterSystem:
  update(feelings: list[StimulusAtom], action_feedback: ActionResult | None) -> None
  get_modulations() -> NTModulations
  get_baseline() -> dict
  reset_to_baseline() -> None
```

**递质通道与调制效果**：

```
NTModulations:
  focus:        float    # [-1.0, 1.0]  正值收窄注意力，负值扩大探索
  arousal:      float    # [-1.0, 1.0]  正值提高整体活跃度，负值降低
  caution:      float    # [0.0, 1.0]   提高行动阈值
  exploration:  float    # [0.0, 1.0]   提高感应生长的展开深度和预算
  fatigue:      float    # [0.0, 1.0]   累积性疲劳，降低所有能量
  stability:    float    # [0.0, 1.0]   降低衰减系数，使状态更持久
```

**调制如何影响其他模块**：

```
focus > 0     → Attention.budget 减少，选中对象更少但更精准
focus < 0     → Attention.budget 增加，允许更多对象进入 CAM
arousal > 0   → 所有 E_real 和 E_virtual 乘以增益因子 (1 + arousal * 0.3)
caution > 0.5 → ActionNode.threshold 乘以 (1 + caution)
exploration > 0.5 → InductionGrowth.max_depth 增加 1-2 层
fatigue > 0.7 → 所有能量注入乘以 (1 - fatigue * 0.5)
stability > 0.5 → λ_real 和 λ_virtual 提高（衰减变慢）
```

**动态规则**：

递质值不是瞬间变化的，而是有惯性的：

```
NT(t+1) = NT_baseline + inertia * (NT(t) - NT_baseline) + impulse(t)

其中 inertia 默认 0.85，impulse 来自当前轮的认知感受和行动反馈。
这意味着递质变化是渐变的，不会因为一次感受就剧烈波动。
```

---

### 4.8 行动节点与反馈学习（Action System）

**职责**：管理可执行意图，将行动后果和奖惩反馈写回认知系统。

> **论文对齐（AP 附录 B）**：
> - 行动触发：drive(a) > threshold(a, NT, CFS)
> - 阈值不仅取决于行动节点自身，还受全局情绪递质（NT）和当前认知感受（CFS）调制
> - 工程含义：奖励状态下阈值下降（更愿尝试），惩罚/压力状态下阈值上升（更谨慎）
> - 必须叠加权限检查和安全审查（见 5.7 节中的 teacher_gate_should_wake）

**接口定义**：

```
ActionSystem:
  register_node(node: ActionNode) -> None
  evaluate_drives(pool: StatePool, nt: NTModulations) -> list[ActionCandidate]
  execute(candidate: ActionCandidate, executor: Callable) -> ActionResult
  process_feedback(result: ActionResult) -> None
  get_action_report() -> dict
```

**驱动力计算**：

```
每个行动节点的当前驱动力：

drive(t) = base_drive + learned_drive + contextual_drive - fatigue_penalty

其中：
  base_drive: 先天或任务规则赋予的初始驱动力
  learned_drive: 来自历史奖惩的累积效应
    learned_drive = Σ(reward_i * decay_factor^(t - t_i)) - Σ(punishment_j * decay_factor^(t - t_j))
  contextual_drive: 来自感应生长的虚能量注入
    如果感应生长展开了包含该行动节点的历史路径，路径的虚能量转化为 contextual_drive
  fatigue_penalty: 短时间内重复执行的疲劳惩罚
    fatigue_penalty = execution_count_recent * fatigue_rate

触发条件：drive(t) > threshold * (1 + NT.caution)
```

**反馈处理**：

```
行动执行后返回 ActionResult：
  outcome: "success" | "failure" | "partial" | "error"
  reward_signal: float     # 正值表示奖励，负值表示惩罚
  feedback_text: str       # 可选的文字反馈
  teacher_labels: dict     # 可选的教师标注

process_feedback 的处理流程：
  1. 将 reward_signal 写入行动节点的 reward/punishment_history
  2. 根据 reward_signal 调整 learned_drive：
     正值 → learned_drive 增加，未来更倾向于执行此行动
     负值 → learned_drive 降低，未来更不倾向于执行
  3. 将行动结果包装为 StimulusAtom（source = ACTION），注入状态池
  4. 如果 reward_signal 显著（绝对值 > 0.5），触发认知感受（Anticipation 或 Pressure）
  5. 将教师标签（如果有）写入 HDB，与当前命中的结构关联
```

**后天学习**：

初始状态下，行动节点只有 base_drive（来自先天规则）。随着系统运行，每次行动的后果都通过 reward_signal 改变 learned_drive。经过多轮交互后，相似语境会通过感应生长为曾经成功的行动节点提供额外的 contextual_drive，为曾经失败的行动节点施加抑制。这就是"行动经验沉淀为认知倾向"的过程。

**教师反馈的延迟合流**（论文 5.7.1）：

很多系统虽然也有"人工纠错"，却只是把纠错结果写进数据库或系统提示，没有真正改变内部认知驱动力。CogCore 采用**延迟合流**而非立即生效：

```
# 接口：action_system.py
def queue_teacher_feedback(labels: dict) -> None:
    """
    暂存教师信号到 feedback_queue。
    labels 含: reward_signal, anchor_note, explanation, target_atom_id
    不立即进入 AP——避免在错误的认知快照上塑形
    """

def merge_pending_teacher_feedback() -> list[TeacherFeedback]:
    """
    在下一轮 tick 开始前、状态池维护后、注意力选择前调用。
    合并到当前 labels，与 Expectation Contract 对齐后注入 HDB。
    论文原型的实现：_queue_teacher_feedback_labels + _merge_pending_teacher_feedback
    """
```

**为什么必须延迟合流**：

- 教师信号一旦立即生效，可能被塑形到错误的 tick 现场上（因为运行时状态是流动的）
- 延迟合流让教师信号与"下一轮"的状态形成稳定的因果对，更像课程学习
- 多次小反馈会累积到教师别名（teacher alias），跨 tick 持续影响局部 drive

**关键设计点**：教师信号**不**只是"记一笔日志"，它会变成 AP 后续可见、可累积、可继续塑形的结构化对象。这是 E03（教师局部塑形）和 E04（教师局部纠偏）能够稳定复现的前置条件。

---

### 4.9 自适应调参器（Adaptive Tuner）

**职责**：维持系统运行在稳定区间，防止过载或停摆。

**接口定义**：

```
AdaptiveTuner:
  assess(pool_state: EnergySummary, nt: NTModulations, 
         attention_stats: dict) -> TunerAdjustments
  apply(adjustments: TunerAdjustments) -> None
  get_tuner_report() -> dict
```

**评估与调整规则**：

```
状态评估（每 N 个 tick 执行一次，默认 N=5）：

情况 1：沉寂（pool 总能量 < low_threshold）
  → 降低衰减系数 λ（使残留信息保持更久）
  → 降低行动阈值（更容易触发行动）
  → 增加 exploration（鼓励联想）

情况 2：过载（活跃对象数 > max_atoms * 0.8）
  → 增加衰减系数 λ（加速淘汰）
  → 减少 attention budget（更严格的选择）
  → 降低 induction growth budget（减少联想展开）

情况 3：认知压持续过高（连续 M 轮 P_cognitive > high_threshold）
  → 增加 attention 对异常对象的权重
  → 提高 exploration（寻找更多可能的解释路径）
  → 如果持续超过 2M 轮，触发 Pressure 认知感受

情况 4：注意力过散（CAM 中对象能量方差 < low_variance_threshold）
  → 增加 attention 的 energy 权重（更偏向高能对象）
  → 减少 attention budget

情况 5：传播过薄（induction growth 展开节点数 < min_spread）
  → 降低 spread_factor 阈值（允许更弱的关联也被展开）
  → 增加 induction budget

所有调整都有幅度上限（max_adjustment），且调整后的参数不能超出安全范围。
调参器不替代学习——它只为学习提供稳定的运行环境。
```

---

## 5. 认知滴答（Cognitive Tick）流水线

一轮认知滴答是 CogCore 的完整处理周期。以下是每个阶段的输入、处理和输出：

```
阶段 1：外源输入接收
  输入：上层系统传入的 raw_input + modality
  处理：SensorLayer.ingest() → 生成 StimulusAtom 列表
  输出：外源刺激元（source=EXTERNAL, energy.real > 0）

阶段 2：状态池维护
  输入：阶段 1 的新刺激元 + 上一轮残留对象
  处理：
    - StatePool.decay()：所有对象按 λ 衰减
    - StatePool.add()：注入新刺激元
    - StatePool.cleanup()：淘汰低于阈值的过期对象
  输出：更新后的状态池

阶段 3：查存一体（HDB）
  输入：当前状态池中的外源刺激元
  处理：HDB.lookup()：匹配已有结构 + 计算残差 + 必要时写入新结构
  输出：LookupResult（命中结构、匹配分数、新建结构）
        命中结构获得虚能量回投到状态池

阶段 4：感应生长
  输入：状态池中的高能对象（外源 + 回投）
  处理：InductionGrowth.expand()：沿 HDB 局部结构展开预测
  输出：虚拟刺激元列表（source=INTERNAL, energy.virtual > 0）注入状态池

阶段 5：认知感受评估
  输入：状态池能量摘要 + HDB 结果 + 上一轮行动反馈
  处理：CFS.evaluate()：计算各类认知感受
  输出：感受刺激元列表（source=FEELING）注入状态池

阶段 6：注意力选择
  输入：状态池中所有活跃对象
  处理：Attention.select()：按综合得分选出 CAM
  输出：CAM 对象转化为内源刺激回注状态池

阶段 7：情绪递质更新
  输入：本轮认知感受 + 行动反馈
  处理：NT.update()：按惯性规则更新各通道调制值
  输出：新的 NTModulations，影响后续所有模块参数

阶段 8：行动评估与执行
  输入：行动节点列表 + 状态池 + NT 调制
  处理：
    - ActionSystem.evaluate_drives()：计算各节点驱动力
    - 如果某节点 drive > threshold：ActionSystem.execute()
    - ActionSystem.process_feedback()：处理行动后果
  输出：行动结果和反馈回写状态池

阶段 9：情景记忆写入
  输入：本轮全部事件（刺激、匹配、行动、感受）
  处理：如果本轮包含显著事件，创建 EpisodicMemory
  输出：情景记忆存入 HDB

阶段 10：自适应调参
  输入：状态池摘要 + NT 状态 + 注意力统计
  处理：AdaptiveTuner.assess()：评估是否需要调参
  输出：参数调整应用到各模块
```

### 5.11 工程主线顺序与代码锚点

上述 10 个阶段是认知层面的"干什么"，但工程实现还需要明确"按什么顺序在哪个代码入口完成"。以下主线直接对应论文 4.7.1 描述的真实 tick 顺序（`observatory/_app.py` 中的 `run_cycle`），是 CogCore 实现的代码级骨架。

| # | 主线阶段 | 代码锚点 | 接收 | 产出 | 对闭环的意义 |
|---|---------|---------|------|------|------------|
| 1 | 总入口 | `run_cycle` | 外源输入、标签、运行配置 | 本轮完整 report + 时间线 | 统一观察入口 |
| 2 | 状态池维护 | `_run_state_pool_maintenance` | 上一轮残留对象 | 衰减/清理/汇总后的当前状态场 | 把时间与竞争真实作用到当前认知场 |
| 3 | 注意快照 | `_build_attention_memory_stub` | 维护后的状态池 | CAM 快照、top items、注意报告 | 显式化"当前最值得在意什么" |
| 4 | 内外源合流 | `build_internal_stimulus_packet` + `merge_stimulus_packets` | 外源刺激包 + 内部碎片 | 合并后的主刺激包 | 让回忆、联想与当前输入同路 |
| 5 | 历史查存 | `run_stimulus_level_retrieval_storage` | 主刺激包 + 残差包 | 命中、结构写入、残差结果 | 历史改变当下处理成本与生长 |
| 6 | 残差回投 | `_insert_residual_tail_memory_projection_to_pool` / `_insert_runtime_residual_package_to_pool` | 残差、记忆投影、运行时包 | 重新入池的后效对象 | 把"本轮没处理完"带到下一轮 |
| 7 | 结构投影与感应 | `_project_runtime_structures` / `_build_induction_source_snapshot` / `_apply_induction_targets` | 高能对象、支持结构、局部目标线索 | 下一轮更易被激活的结构与候选 | 经验复用、预测与行动准备接到一起 |

**为什么每个阶段都不可省略**（论文 4.7.6）：

| 缺失阶段 | 退化 | 不再像 AP 的原因 |
|---------|------|----------------|
| 状态池维护 | 旧激活与新输入混杂，当前注意被历史噪声污染 | 时间、疲劳、竞争和清理不再真实作用于当前认知场 |
| 注意快照 | 系统无法说明此刻真正聚焦什么 | 没有显式的"当前在意对象" |
| HDB 查存一体 | 历史只剩文本回忆，无法改变结构成本与局部生长方向 | 经验不再直接塑形当下 |
| 残差回投 | 未处理完线索只能消散或停留在报告中 | 系统失去持续挂念与后续续写能力 |
| 目标投影 | 本拍结果难以转成下一拍的候选准备 | 主动性与延续性会退化为外部脚本触发 |

这一主线顺序与上面 10 个认知阶段的关系是：**认知阶段定义每一步在认知层面的意义，工程主线定义每一步在代码层面的归属**。两者一一对应，但工程主线是唯一能保证"先做什么后做什么"的实现路径。

### 5.12 与论文原型的差异点

CogCore 是在论文 AP 原型基础上的工程化重写。实现层面需要明确以下差异，避免后续维护者混淆"论文怎么说"和"CogCore 怎么做"：

| 项 | AP 原型（论文） | CogCore |
|---|---|---|
| 拓扑 | 单进程 Python + observatory | 计划采用 LangGraph StateGraph（10 阶段 = 10 节点） |
| 持久化 | 自带 state_pool + HDB 实现 | 短期 Checkpointer + 长期 Store（LangGraph） |
| 状态合并 | 各模块内部维护 | 统一 Reducer 机制（见 6.4） |
| 工具调用 | `LocalToolRegistry.run` | LangGraph `ToolNode` + tool_allowlist |
| 教师反馈 | `_queue_teacher_feedback_labels` + `_merge_pending_teacher_feedback` | `inject_teacher_feedback()` 进入 ActionSystem |
| 观测台 | `observatory/_app.py` 独立 | 保留 Observatory 接口（见 6.3），但底层走 LangSmith/Phoenix |

**接口对齐原则**：CogCore 保留论文中所有外部可观察接口的语义（`run_cycle`、`_build_attention_memory_stub`、`run_stimulus_level_retrieval_storage` 等），但内部实现可替换。这是 4.1 节"工程边界：自由实现不同于任意实现"的具体落地——替换实现不破坏 AP 闭环逻辑。

### 5.13 一轮认知滴答的完整追踪样例

为方便后续调试与白箱审计，以下追踪样例与论文附录 C 完全对齐。每一行都是一次 `run_cycle` 中的实际观察点——不仅记录"做了什么"，还记录"在哪一步可被审计"。

| # | 阶段 | 输入 | 处理 | 输出 / 审计点 |
|---|------|------|------|-------------|
| 1 | **感受器** | 外源文本、时间、反馈 | 转为刺激元、属性、ER/EV | `stimulus packet`（含 trace.origin 与 birth_tick） |
| 2 | **状态池维护** | 上一轮状态 | 衰减、中和、合并、软容量 | `state snapshot`（含总能量、对象数、认知压、半衰期） |
| 3 | **注意力** | 活跃对象 | 评分、增益、抑制、选 CAM | `CAM items`（含 top items、score 分解、抑制原因） |
| 4 | **内源刺激** | CAM | 压缩为可重新认知的刺激包 | `internal stimulus`（source=INTERNAL, energy.virtual > 0） |
| 5 | **刺激级查存一体** | 外源 + 内源 | 匹配、切割、写入、投影 | `ST/EM/residual`（含命中分数、新建结构 id、写入残差） |
| 6 | **感应生长** | 高能结构 | 打开局部数据库，生成 A+B | `growth targets`（含层级深度、传播系数、剪枝次数） |
| 7 | **认知感受** | 状态池指标 | 生成违和、正确、期待、压力等 | `CFS events`（含类别、强度、关联刺激元 id） |
| 8 | **情绪递质** | CFS/奖惩/规则 | 更新慢变量调制 | `NT values`（含各通道当前值、inertia、impulse 贡献） |
| 9 | **行动** | 行动节点与阈值 | drive 竞争、权限检查、执行 | `action events`（含被选节点、最终 drive、实际执行结果） |
| 10 | **自适应调参** | 运行指标 | 微调参数并记录边界 | `tuner events`（含调整前/后值、是否被 max_adjust 截断） |

> **审计原则**：10 个阶段任一可观测缺失都对应一次退化（详见 5.11 表）。运行期诊断脚本应同时检查 10 个输出/审计点是否齐全——不齐全即不视作一次"完整 tick"。

### 5.14 tick 与论文 10 阶段、E01-E17 的对应

为了让验证矩阵（`CogCore-验证矩阵.md`）和工程主线（5.11）形成闭环，下表给出每阶段对应的可观察指标与可触发实验：

| 阶段 | 主要观察指标 | 关联实验 |
|------|------------|---------|
| 1 感受器 | 对象数、初始 ER | E16 |
| 2 状态池维护 | 总能量、认知压、半衰期 | E15 |
| 3 注意力 | CAM 规模、score 分布 | E07, E15 |
| 4 内源刺激 | 内源刺激能量 | E17 |
| 5 查存一体 | 命中分数、新增结构数、残差写入 | E01, E02, E11, E12 |
| 6 感应生长 | 展开深度、传播系数、剪枝次数 | E11, E17 |
| 7 认知感受 | CFS 强度、恢复分层 | E09, E10 |
| 8 情绪递质 | 各通道调制值 | E14, E15 |
| 9 行动 | drive 排序、执行反馈 | E03, E04, E05, E14 |
| 10 自适应调参 | 调整幅度、是否被截断 | E15 |

> 复现某项实验时，应同时报告这 10 个审计点的输出——仅报告实验本身的判据记录而忽略上下游阶段，会丢失"闭环是否真的闭环"的可观察证据。

---

## 6. 外部集成接口

### 6.1 与 LLM 的接口

CogCore 不替代 LLM，而是与 LLM 形成分工。LLM 负责语言表达、复杂参数翻译、网页/工具编排与安全审查；CogCore（AP 层）负责长期状态、注意选择、行动准备度、反馈塑形与教师门控。这一分工被称为 **PA 双层结构**（PsyArch Agent 模式，论文 5.6.1）。

#### 6.1.1 四层职责划分

| 层级 | 职责 | CogCore 入口 | 为什么不能互换 |
|------|------|-------------|---------------|
| **AP 持续状态层** | 维护状态池、注意、记忆投影、行动驱动力、反馈痕迹 | `run_cycle` 前后的 AP tick / `build_recent_tick_report` / `ap_recall` | 保存的是长期状态，不是一次性语言输出 |
| **LLM 解释层** | 把 AP 状态翻译成语言，把语言翻译成意图和工具参数 | `LLMBridge.build_context_packet` / `parse_llm_output` | 擅长表达和泛化，但天然不保存白箱长期状态 |
| **工具执行层** | 调用本地工具、回收结果、再写回状态 | `ToolRegistry.execute_tool` / `ActionSystem.execute` | 决定系统能做什么，但不决定为什么此刻去做 |
| **审查与教师层** | 判断是否应主动打断、是否应发言、工具结果是否安全 | `inject_teacher_feedback` / `teacher_gate_should_wake` | 提供长期方向约束，不是末端补丁 |

#### 6.1.2 一条消息从到达到回复的 5 步真实顺序

这是 PA 主线的精确描述（论文 5.6.2），也是 CogCore 接入 LLM 时代的实现模板：

| 顺序 | 模块 | 输入 | 输出 | 对体验的改善 |
|------|------|------|------|------------|
| 1 | `ingest_adapter_event` / `should_wake` | 私聊/群聊/文本输入事件 | 是否唤醒、唤醒原因 | 避免无关噪声直接打断系统 |
| 2 | `send_message` | 用户文本、上下文、AP 状态 | AP 若干内部 tick + 新快照 | 让回复建立在当前认知现场上 |
| 3 | `LLMBridge.build_context_packet` | tick 报告、工具摘要、注意对象 | 结构化 prompt packet | 减少长提示词堆砌，提高上下文含金量 |
| 4 | LLM 输出 → `_execute_tool_calls` | 工具结果、失败原因、上下文 | 工具结果回写 AP | 让工具结果继续参与后续认知 |
| 5 | 最终回复 / 继续思考 | 更新后的状态与工具回写结果 | 回复、继续思考、静默、睡眠 | 让一次交互可以自然接到下一次 |

> **关键点**：LLM 从一开始就不是直接面对原始聊天记录，而是面对一个经过 AP 过滤、压缩和重构的当前心智快照。模型看到的不只是"最近说了什么"，还包括"哪些对象能量最高""最近哪类行动成功或失败""是否处于高压或高疲劳状态""哪些工具结果刚刚改变了当前判断"。

#### 6.1.3 端到端样例：天气查询

以"北京明天会下雨吗"为例，把一拍主线拆成可观察的环节：

| 阶段 | AP 负责什么 | LLM / 工具负责什么 | 最后回到哪里 |
|------|-----------|------------------|------------|
| 唤醒判定 | 判断当前事件是否值得进入主链 | 无 | 决定是否进入 AP 当前状态场 |
| 内部整理 | 运行若干 tick，形成当前注意、感受和行动倾向 | 无 | 生成可解释的 prompt packet |
| 语言解释 | 提供当前状态材料 | LLM 负责理解、组织与生成 | 输出文本意图、工具意图或继续思考意图 |
| 工具执行 | 决定其结果应如何被吸收和记住 | 本地工具执行、返回结果 | 结果重新写回 AP，进入下一轮判断 |
| 最终行为 | 基于更新后的状态决定回复、沉默或继续思考 | LLM 给出语言表达 | 形成一次可接到下一次的连续交互 |

#### 6.1.4 三种运行模式

按主动性递进，CogCore 支持三种运行模式（论文 5.8.1）：

| 模式 | 当前行为特征 | 典型入口 | 适合的阶段 |
|------|------------|---------|----------|
| `full_silent` | 只在明确触发下响应 | `run_cycle` 中保持静默 | 冷启动、保守验证、低风险部署 |
| `ap_agency` | AP 可基于 wake_drive 主动升起候选 | `run_cycle` + `estimate_wake_drive` | 开始测试主观能动性和后台整理能力 |
| `reinforced_agency` | 主动性还要经过教师门控 | `teacher_gate_should_wake` | 需要长期发展但又重视审查与纠偏 |

工程上对应一个布尔开关 + 一个唤醒评估函数。从 `full_silent` 起步，把长期记忆和工具组织能力跑稳；再开 `ap_agency` 试主观能动性；最后上 `reinforced_agency` 把教师门控加进来。

#### 6.1.5 LLMBridge 接口契约

```
LLMBridge:
  # CogCore → LLM：将认知状态翻译为 LLM 可理解的上下文
  build_context_packet(tick_report: dict, max_tokens: int) -> str
    # 包含：当前注意内容、相关记忆、认知感受摘要、行动倾向
    # LLM 用这个 packet 作为 prompt 的一部分来生成回复

  # LLM → CogCore：将 LLM 输出解析为认知输入
  parse_llm_output(llm_response: str) -> list[StimulusAtom]
    # LLM 的回复也可以作为内源刺激进入状态池

  # 教师反馈（论文 5.7.1：延迟合流而非立即生效）
  queue_teacher_feedback(labels: dict) -> None
    # 暂存到 feedback_queue
  merge_pending_teacher_feedback() -> list[TeacherFeedback]
    # 在下一轮 tick 之前合并到当前 labels，与 expectation contract 对齐
    # 这样教师信号不会只停留在 UI 提示，而会变成 AP 后续可见、可累积的结构化对象

  # 主动唤醒门控（reinforced_agency 模式）
  teacher_gate_should_wake(event: IngestEvent) -> WakeDecision
    # 在主动回复、后台思考和某些边界场景里要求教师判断是否应唤醒
    # 注意：这不是末端过滤器，而是长期发展方向控制的一部分
```

### 6.2 与工具链的接口

```
ToolRegistry:
  register_tool(name: str, func: Callable, schema: dict) -> None
  execute_tool(name: str, params: dict) -> ToolResult
  get_available_tools() -> list[str]

# 行动节点通过 tool_mapping 字段关联到具体工具
# ActionSystem.execute() 内部调用 ToolRegistry.execute_tool()
# 工具返回结果被包装为 StimulusAtom 注入状态池
```

#### 6.2.1 长期经验工具（论文 5.7.2）

以下工具不是普通"日志读写"，而是把长期经验做成可操作的认知资源。它们都遵循统一模式：**调用本身会进入状态池、可以被记忆、被反馈塑形**。

| 能力 | CogCore 接口 | 作用 | 为什么对 CogCore 重要 |
|------|------------|------|--------------------|
| **写日记** | `write_diary(title, content, importance) -> diary_id` | 沉淀长期经历与可回看素材 | 经验结构化保存，不在上下文里漂走 |
| **读日记** | `read_diary(query, k) -> list[DiaryEntry]` | 把过去经验重新带入当前思考 | 让回忆成为状态驱动的一部分 |
| **建定时任务** | `schedule_task(trigger, action_ref, period) -> task_id` | 让"未来会再想起这件事"成为闭环一部分 | 把承诺、提醒和未来行动接回系统 |
| **查/删任务** | `list_tasks() / cancel_task(task_id)` | 避免任务堆积 | 防止主动性与噪声双增 |
| **工具白名单** | `tool_allowlist: set[str]` | 限制可调用工具 | 能力扩展与安全边界绑定 |
| **技能开关** | `skill_run(skill_id) -> bool` | 查询 Skills 是否开启 | 为技能包协议化接入做探针 |

**日记不是普通日志**：保留标题、内容、重要度更新时间等结构化字段；CogCore 把它作为高 importance 的输入，进入状态池后可被感应生长、注意、行动节点竞争。

**定时任务不是闹钟外挂**：能重新唤醒 AP，把过去的承诺带回到当前状态场。这是 E06（时间间隔感受）能够通过复现的关键基础设施。

**技能包共享不只是提示词复制**（论文 5.7.4）：

| 传统"技能包" | CogCore 视角 |
|--------------|------------|
| 复制一段提示模板 | 复制一段可运行的经验组织方式 |
| 经验无法沉淀 | 工具边界 + 白名单 + 日记模板 + 任务规则 + 教师判断习惯 + 反馈经验都成为技能包的一部分 |
| 新实例学的是"怎么说" | 新实例学的是"在什么状态下应想到这件事、如何判断是否该做、做完后应如何记住结果" |

> **工程含义**：当 CogCore 后续实现技能包共享协议时，每个技能包应包含：适用范围、禁用条件、来源哈希、复核说明，而不只是提示词片段。

#### 6.2.2 安全审查不是末端补丁（论文 5.7.3）

CogCore 的安全性建立在三个相互独立的机制上：

1. **`teacher_gate_should_wake`**：在主动回复、后台思考和某些边界场景里要求教师判断是否应唤醒
2. **`tool_allowlist`**：工具调用受白名单约束，行动能力受边界控制
3. **反馈回写**：高风险路径的工具结果会重新写回 AP，让下一轮系统对这类行动的心理成本发生变化

> **关键判断**：安全与教导不是事后批评，而是发展方向本身的一部分。这也是为什么 E15（自适应调参）必须与教师门控共同验证——单独跑调参器无法证明"系统在安全范围内自适应"。

### 6.3 可观察性接口

```
Observatory:
  get_tick_report(tick: int) -> dict     # 单轮完整报告
  get_state_snapshot() -> dict           # 当前全局状态快照
  get_structure_graph() -> dict          # HDB 结构拓扑图
  get_energy_timeline(ticks: int) -> list # 能量变化时间线
  get_action_log(limit: int) -> list     # 行动日志
  export_experiment_data(path: str) -> None  # 导出实验数据
```

所有报告数据都包含 SHA-256 哈希锚点，确保可追溯。

### 6.4 状态合并与 Reducer 契约（LangGraph 关键陷阱）

> **警告**：本节是 M0.5（LangGraph 集成）阶段的**必读**。未按本节约束写节点函数会导致「脑损伤式」数据丢失——节点返回的 partial update 在合并时会把嵌套对象未声明的子字段静默清空。

**问题本质**：

在 LangGraph 中，节点函数返回的是对 `CogCoreState` 的**部分更新（Updates）**，不是整个新 State。默认情况下，Python 的字典合并会**覆盖整个字段**。CogCore 的状态包含大量嵌套对象（`cam` / `nt_values` / `pool_snapshot` / `hdb_snapshot`），如果节点只返回「我想改的子字段」，其他子字段会被默认合并清空。

**错误示例**（会导致数据丢失）：

```python
def stage_7_nt_update_BAD(state):
    # 只更新 focus，但返回了部分 dict
    # → 整个 nt_values 被覆盖为 {"focus": 0.5}，其他字段（arousal, caution, fatigue...）丢失
    return {"nt_values": {"focus": 0.5}}  # ✗ 脑损伤
```

**两种合规的解决方式**：

**方式 A：Pydantic 模式（推荐）**

CogCore 已全面用 Pydantic，天然适合这种模式。完整定义见 `src/cogcore/state_schema.py`：

```python
from typing import Annotated
from operator import add
from pydantic import BaseModel, Field

class CogCoreState(BaseModel):
    tick: int = 0
    raw_input: str = ""

    # 嵌套对象——默认是整体替换（不会被部分清空）
    pool_snapshot: StatePoolSnapshot = Field(default_factory=StatePoolSnapshot)
    hdb_snapshot: HDBSnapshot = Field(default_factory=HDBSnapshot)
    nt_values: NTModulations = Field(default_factory=NTModulations)
    cam: CurrentAttentionMemory | None = None

    # 列表——用 Annotated + add Reducer 显式累加
    new_atoms: Annotated[list[StimulusAtom], add] = Field(default_factory=list)
    grown_atoms: Annotated[list[StimulusAtom], add] = Field(default_factory=list)
    feeling_signals: Annotated[list[FeelingSignal], add] = Field(default_factory=list)
    stages_log: Annotated[list[str], add] = Field(default_factory=list)
    error_log: Annotated[list[str], add] = Field(default_factory=list)
```

**节点返回的正确模式**：

```python
# 模式 1：嵌套对象返回整个新对象（天然安全）
def stage_7_nt_update_GOOD_1(state):
    new_nt = state.nt_values.model_copy(update={"focus": 0.5})
    return {"nt_values": new_nt}  # ✓ 整体替换


# 模式 2：嵌套对象用 StateUpdater.patch_* 辅助方法（推荐）
def stage_7_nt_update_GOOD_2(state):
    return make_updater(state).patch_nt_values(focus=0.5).to_patch()


# 模式 3：列表 append（add reducer 自动处理）
def stage_1_sensor_input_GOOD(state):
    new_atoms = [...some atoms...]
    return {"new_atoms": new_atoms}  # ✓ add reducer 累加


# 模式 4：链式 StateUpdater（最优雅）
def stage_node(state):
    return (
        make_updater(state)
        .patch_nt_values(focus=0.5)
        .append_atoms([atom_a, atom_b])
        .append_stage("stage_3")
        .to_patch()
    )
```

**方式 B：TypedDict + 显式 Annotated Reducer（备选）**

```python
from typing import TypedDict, Annotated
from operator import add

class CogCoreGraphState(TypedDict, total=False):
    tick: int
    raw_input: str

    # 嵌套对象：默认 replacement（整个对象替换）
    pool_snapshot: StatePoolSnapshot
    nt_values: NTModulations
    cam: CurrentAttentionMemory | None

    # 列表：显式 Annotated + add
    new_atoms: Annotated[list[StimulusAtom], add]
    stages_log: Annotated[list[str], add]
```

**节点返回的正确模式**：返回整个嵌套对象，或只返回 add reducer 字段的增量。

**节点返回的 5 种错误模式**（必须避免）：

| # | 错误 | 示例 | 后果 |
|---|------|------|------|
| 1 | 返回部分嵌套 dict | `{"nt_values": {"focus": 0.5}}` | 整个 nt_values 被覆盖，其他字段丢失 |
| 2 | 拼写错误字段名 | `{"new_atom": some_atom}` | 字段被静默丢弃，无报错 |
| 3 | 返回完整 state | `return state` | 不出错但违背 LangGraph 范式 |
| 4 | 跨节点修改全局状态 | `import cogcore.global_state; global_state.x = 1` | 破坏可重入性，并发场景崩 |
| **5** | **Fluent API 双重累加** | `return state.append_atoms([B])` | **预累加返回后，LangGraph add reducer 再次拼接 → 指数膨胀** |

**自定义 Reducer 示例**（`state_schema.py` 提供）：

```python
def merge_cam(existing, update):
    """CAM 合并：update 总是替换 existing（本轮选择是新的）。"""
    if update is None:
        return existing
    return update

def attention_budget_reducer(existing: int, update: int | None) -> int:
    """注意力预算：clamp 在 [0, 20]。"""
    if update is None:
        return max(0, existing)
    return max(0, min(20, update))
```

**陷阱 T5：Fluent API 双重累加**（2026-06-05 用户捕获）

Pydantic 模式下的「链式调用」辅助方法如果返回完整 `CogCoreState` 实例，会触发 LangGraph Reducer 的**双重累加**：

```python
# 错误：返回完整 State 实例
def stage_node_BAD(state):
    return state.append_atoms([atom_b])
    # patch.new_atoms = [atom_a, atom_b]  # Pydantic 已预累加
    # LangGraph add reducer: existing [atom_a] + update [atom_a, atom_b] = [atom_a, atom_a, atom_b] 💥
```

**修复方案**：`StateUpdater` 累积 patch dict（不预累加），最后 `.to_patch()` 返回 dict。`append_atoms` 在 `StateUpdater` 内**只记录增量**，不与现有 atoms 拼接。

```python
# 正确：返回 patch dict
def stage_node_GOOD(state):
    return make_updater(state).append_atoms([atom_b]).to_patch()
    # patch = {"new_atoms": [atom_b]}  # 单独增量
    # LangGraph add reducer: [atom_a] + [atom_b] = [atom_a, atom_b] ✓
```

**`StateUpdater` 关键设计**：

| 方法 | 返回类型 | 行为 |
|------|---------|------|
| `patch_nt_values(**kwargs)` | `StateUpdater` | 用 `model_copy` 深合并，返回**整个新 nt_values 对象引用**到 patch |
| `append_atoms(atoms)` | `StateUpdater` | **不预累加**——只把 atoms 加到 patch['new_atoms']（同 key 可在 patch 内拼接） |
| `append_stage(name)` | `StateUpdater` | 同上 |
| `to_patch()` | `dict` | 返回**深拷贝**的 patch dict（避免外部修改污染内部状态） |

**检测与验证**：

- `tests/test_state_schema.py::test_state_updater_does_not_preaccumulate` 验证 StateUpdater 不预累加
- `tests/test_state_schema.py::test_pipeline_no_double_accumulation_after_10_stages` 验证 10 轮后 stages_log 恰好 10 条
- `tests/test_state_schema.py::test_langgraph_merge_no_double_accumulation` 验证合并后 [atom_a, atom_b] 不是 [atom_a, atom_a, atom_b]

**M0.5 当前状态**：

- ✅ `src/cogcore/state_schema.py` 已定义 `CogCoreState` + `StateUpdater`（Pydantic）
- ✅ `src/cogcore/pipeline.py` 已用 StateUpdater 链式：每个 stage 返回 `dict[str, Any]`
- ✅ `src/cogcore/graph.py`：`build_cogcore_graph()` 构造 10 节点 StateGraph + MemorySaver checkpointer
- ✅ `pipeline.run_cycle` 已等价替换为 `graph.invoke()`（LangGraph 自动 Reducer 合并 patch）
- ✅ 11 个 graph 测试通过（编译 / invoke / T1+T5 不变量 / 多次 invoke 累积）
- ✅ 138 个测试全过（+11 新测试）

---

## 7. 配置参数总表

| 参数 | 所属模块 | 默认值 | 说明 |
|---|---|---|---|
| λ_real | StatePool | 0.85 | 实能量衰减系数 |
| λ_virtual | StatePool | 0.75 | 虚能量衰减系数 |
| max_atoms | StatePool | 200 | 状态池容量软上限 |
| min_energy_cleanup | StatePool | 0.01 | 清理阈值 |
| growth_threshold | HDB | 0.3 | 结构生长触发阈值 |
| max_depth | HDB | 10 | HDB 树最大深度 |
| spread_factor | InductionGrowth | 0.8 | 能量传播系数 |
| induction_max_depth | InductionGrowth | 3 | 感应展开最大深度 |
| induction_budget | InductionGrowth | 50 | 感应展开节点上限 |
| min_induction_energy | InductionGrowth | 0.05 | 感应最小能量 |
| attention_budget | Attention | 10 | 注意力选择数量 |
| repeat_penalty | Attention | 0.5 | 重复选中惩罚 |
| fatigue_penalty | Attention | 0.2 | 连续选中惩罚 |
| pressure_high | CFS | 0.7 | 违和感触发阈值 |
| pressure_drop | CFS | 0.3 | 正确感触发阈值 |
| nt_inertia | NT | 0.85 | 递质惯性系数 |
| action_fatigue_rate | ActionSystem | 0.1 | 行动疲劳率 |
| tuner_interval | AdaptiveTuner | 5 | 调参评估间隔(tick) |
| tuner_max_adjust | AdaptiveTuner | 0.15 | 单次最大调整幅度 |

---

## 8. 设计取舍说明

**为什么用字符/结构化数据而不是向量作为刺激元？**

当前设计优先考虑可审计性和可复现性。向量表示虽然语义泛化更好，但它是黑箱的——你无法解释两个向量为什么匹配。CogCore 的感受器层是插件式的，未来可以注册向量 parser，但核心匹配和存储机制仍基于可解释的索引和残差。

**为什么 HDB 不用传统向量数据库？**

传统向量数据库做的是全局相似性检索，HDB 做的是局部索引 + 残差写入。区别在于：向量数据库每次都是"从全部历史中找最像的"，HDB 是"从当前命中的局部经验中看下一步可能是什么"。后者更接近人类经验更新的方式，也更适合持续学习。

**为什么认知感受要进入状态池？**

如果感受只是日志标签，它就不能影响后续的注意力和行动。让感受成为可竞争、可记忆的对象，是 AP 区别于"情绪标签 + 规则"方案的关键。一个经历过多次失败后积累了大量 Pressure 感受的系统，其行为模式会与一个只有规则的系统根本不同。

**自适应调参器会不会导致元调参的无限回退？**

调参器本身有固定的安全边界和最大调整幅度，它的参数不由自己调节。这是一个有意的设计限制——调参器的职责是维持运行区间，不是优化性能。性能优化由上层的教师反馈和奖惩学习承担。

---

## 9. 与现有方案的定位对比

| 维度 | LangChain/LlamaIndex | AutoGPT/AgentGPT | CogCore (本设计) |
|---|---|---|---|
| 记忆机制 | 文本摘要或向量检索 | 聊天记录 + 摘要 | 状态池 + HDB 查存一体 + 情景锚点 |
| 情绪处理 | 无或提示词模拟 | 无 | CFS 功能化 + NT 全局调制 |
| 行动反馈 | 工具返回值临时使用 | 反思日志 | 行动节点入池 + 驱动力塑形 + 奖惩回写 |
| 长期状态 | 无（每次调用独立） | 有限（聊天历史） | 状态池 + HDB 跨 tick 持续 |
| 可审计性 | 链式调用日志 | 有限 | 全链路白箱报告 + 哈希锚点 |
| 主动性 | 无（依赖用户输入） | 有限（循环执行） | 行动节点驱动力 + 认知感受 + 阈值调制 |

CogCore 不替代这些框架，而是作为它们可以接入的认知层。LangChain 可以作为 CogCore 的工具链，LLM 可以作为解释层——CogCore 补的是它们都缺的"持续认知状态管理"这一块。

---

## 10. 发展路线图

本节与论文 5.10 节对齐。AP 的长期发展可以分为三步，CogCore 按此三阶段逐步推进。三阶段之间是**递进**关系——后一阶段以前一阶段的强证据为前置条件。

### 10.1 三阶段总览

| 阶段 | 论文原文描述 | CogCore 状态 | 交付物 |
|------|------------|-------------|--------|
| **阶段一** | 当前阶段：把理论闭环做成可运行原型，并通过 E01-E17 建立机制证据 | ✅ **已完成** — M0.1-M0.9 全部完成，E01-E17 全部通过 | `CogCore-验证矩阵.md` 中「E01-E17 CogCore 状态」列已全部转为「通过」 |"E01-E17 CogCore 状态"列全部从「计划」转为「通过」 |
| **阶段二** | 应用耦合阶段：通过 PsyArch Agent 把 AP 接入现有 Agent 生态，替代/增强 RAG、长期记忆、情绪模块、行动反馈 | ✅ **已完成** — M1.1-M1.4 全部完成 | LLM 桥接 + SQLite 持久化 + 工具系统 + PA 运行模式 |
| **阶段三** | AP 核心阶段：让 AP 在更多任务中主导注意、记忆、行动和学习，LLM/视觉/插件成为它的感受器、解释器和执行器 | M2 愿景 | 三种运行模式全部启用（`full_silent` / `ap_agency` / `reinforced_agency`） |

### 10.2 阶段一：机制闭环 + 17 项实验通过

**目标**：在最小可运行 CogCore 上复现论文 E01-E17 的强证据。

**关键里程碑**：

- M0.1 ✅：单进程实现 + 内存持久化，跑通 tick 流水线 10 阶段
- M0.2 ✅：HDB + 感应生长闭环实现（满足 E01, E02, E11, E12）
- M0.3 ✅：行动系统 + 教师反馈延迟合流（满足 E03, E04, E05, E14）
- M0.4 ✅：CFS + NT + Attention + AdaptiveTuner 调制层（满足 E09, E10, E14, E15）
- M0.5 ✅：LangGraph StateGraph 集成（10 节点 + MemorySaver + StateUpdater + 11 测试）
- M0.6 ✅：AP 投影 + RAG 基线对比（满足 E13）
- M0.7 ✅：多模态感受器 + 属性锚点（满足 E16）
- M0.8 ✅：候选链承接（满足 E17）
- M0.9 ✅：时间感受 + 复杂度调制（满足 E06, E07, E08）

**退出条件**：E01-E17 全部通过 `CogCore-验证矩阵.md` 第 0.2 节四项准入条件；914 条判据记录在 CogCore 端可独立复现。

> ✅ **阶段一已于 2026-06-05 完成。** 阶段二规划见 `docs/CogCore-M1-规划.md`。

### 10.3 阶段二：应用耦合 + 接入现有 Agent 生态

**目标**：把 CogCore 作为长期状态核心，替代或增强现有 Agent 项目的四个关键模块：

| 传统 Agent 部件 | 常见问题 | CogCore 耦合后的变化 |
|----------------|---------|---------------------|
| RAG / 向量检索 | 相似不等于此刻重要 | AP 提供状态、能量和反馈权重 |
| 长期记忆摘要 | 压缩后丢失强度、时序和责任关系 | AP 保留结构、情景锚点和行动后果 |
| 情绪/人设提示词 | 容易停留在表达层 | CFS/NT 参与注意力、阈值和调参 |
| 工具调用流水线 | 调用后果散落在日志外 | 行动节点和反馈回写状态池 |

**关键里程碑**：

- M1.1：LangGraph StateGraph 完整搭建（10 节点 + Reducer 机制 + Checkpointer + Store）
- M1.2：LLMBridge 完整实现（6.1.5 接口全部可用）
- M1.3：tool_allowlist + skill_run 协议化
- M1.4：write_diary / read_diary / schedule_task 工具全部接入
- M1.5：教师反馈延迟合流在 LangGraph 节点中贯通

**退出条件**：能在 LangGraph Studio 中可视化跟踪一次完整 tick；E13 在真实 Agent 上下文中通过。

### 10.4 阶段三：AP 主导 + LLM 退到解释层

**目标**：让 CogCore 决定当前应关注什么、应采取什么行动、应请求哪些工具；LLM 退到解释、翻译、审查和复杂工具执行的位置。

**关键里程碑**：

- M2.1：`full_silent` 模式长期稳定运行（E15 验证）
- M2.2：`ap_agency` 模式开启后后台任务能自然升起候选（E06 + E17 联合验证）
- M2.3：`reinforced_agency` 模式教师门控与调参器稳定耦合（E09 + E15 + teacher_gate 联合验证）
- M2.4：技能包共享协议落地（论文 5.7.4）
- M2.5：多模态感受器完整集成（视觉/触觉/工具状态统一入池，E16 扩展）

**退出条件**：E18-E25（见 `CogCore-验证矩阵.md` 第 4 节）通过；3000+ tick 长程稳定性测试不发散。

### 10.5 不做什么

为避免范围蔓延，本设计明确**不**包含以下方向：

- **完整自然语言组织质量评测**：候选链雏形已通过 E17 验证，但开放叙事质量仍属下一阶段重点（论文 6.3 节明确未验证）
- **多模态具身任务的大规模长期训练**：E16 验证了属性化入口，**未**验证具身控制闭环
- **超长时程自我模型稳定性**：3000+ tick 测试是 M2 里程碑
- **技能包大规模迁移效率**：技能包协议是 M2 内容
- **替代 LLM 本体的能力**：CogCore 不替代 LLM，二者分工（见 6.1.1）

> **诚实原则**：上述不做的项目在阶段一/二/三中保持"未通过"状态，不允许把"计划"标成"已通过"。这与 `CogCore-验证矩阵.md` 第 6 节诚实声明一致。

---

## 附录 A 术语对照表

本附录与论文 AP 附录 A 对齐，为后续读者、复现者和协作者提供统一的术语表。术语在本文档首次出现时已尽量给出中文解释。

| 中文术语 | 英文术语 | 缩写 | 说明 |
|----------|---------|------|------|
| 人工心智架构 | Artificial PsyArch | AP | 论文提出的持续拟人认知闭环范式 |
| 谐振认知假说 | Information Resonance Hypothesis | IRH | 输入与内部结构共同部分产生选择性增强的工程假说 |
| 刺激元 | Stimulus Atom | SA | 基础特征或属性单位，最小可参与认知对象 |
| 结构 | Structure | ST | 可复用、可展开的内容组织单元 |
| 情景记忆 | Episodic Memory | EM | 一次具体经历的记录（目标态/审计锚点） |
| 状态池 | State Pool | SP | 当前活跃对象及其能量状态（当前认知场） |
| 当前注意记忆体 | Current Attention Memory | CAM | 注意力本轮选择的对象集合 |
| 实能量 | Real Energy | ER | 现实证据或外源输入的激活 |
| 虚能量 | Virtual Energy | EV | 内源预测、联想或回忆的激活 |
| 认知压 | Cognitive Pressure | CP | ER 与 EV 差异形成的张力 |
| 认知感受信号 | Cognitive Feeling Signals | CFS | 违和、正确、期待、压力等自我状态信号 |
| 情绪递质通道 | Neurotransmitter-like Channels | NT | 功能性慢变量调制通道（影响注意预算/阈值/调参） |
| 行动节点 | Action Node | Action | 可入池并积累驱动力的行动对象 |
| 自适应调参器 | Adaptive Parameter Tuner | APT | 根据指标微调参数的稳定控制层 |
| 查存一体 | Retrieval-Storage in One Pass | — | 理解和学习发生在同一路径（HDB 的核心机制） |
| 感应生长 | Induction Growth | — | 从当前对象展开有限预测图景（受控扩散） |
| 行动节点驱动力 | Action Drive | drive(a) | 行动节点当前被触发的强度（受 NT/CFS 调制） |
| 期待合约 | Expectation Contract | EC | 行动结果与预期匹配的结算机制（论文 3.19） |

> **注 1**：论文原文为「刺激元（SA）」「结构（ST）」「情景记忆（EM）」，本表与论文附录 A 完全对齐，便于跨文档检索。
>
> **注 2**：本表不含 LangGraph 专属术语（Node / Edge / State / Reducer / Checkpointer / Store 等），这些在 `cogcore_framework_research.md` 中有详细说明。
>
> **注 3**：CogCore 与论文 AP 原型不强制一一对应的术语：`行动节点驱动力`（CogCore）≈ `drive(a)`（论文附录 B 公式），CogCore 命名为模块级接口，论文命名为数学符号。

---

*CogCore M0.9 对应修订版本 | 最后更新：2026-06-05（M0.9 时间感受与复杂度调制完成，162 测试全过）*
