# CogCore 技术选型：2025-2026 AI Agent 框架深度调研报告

> 调研时间：2026年6月
> 目标：为 CogCore "认知内核" 系统寻找最适配的底层框架

---

## 一、CogCore 核心需求回顾

| 需求维度 | 具体要求 | CogCore 映射 |
|----------|----------|-------------|
| 图/管线执行 | 基于图的执行模型，阶段间数据流转 | 10阶段认知 tick |
| 持久化状态 | 跨执行周期的状态保持，支持衰减 | 认知状态的累积与遗忘 |
| 自定义状态对象 | 支持自定义数据结构 | 认知池中的复杂认知对象 |
| 工具集成 | 便捷注册和调用外部工具 | Agent 能力扩展 |
| LLM 集成 | 兼容主流 LLM 提供商 | 模型无关性 |
| 可观测性 | 内建追踪/日志 | 认知过程调试与审计 |

---

## 二、主流框架逐一分析

### 1. LangGraph（LangChain 团队）

| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~25K（2026年中），月下载量超 3450 万次，企业级部署最多的编排框架 |
| **核心架构** | **有向状态图（StateGraph）**：节点（Node）= 处理步骤，边（Edge）= 状态流转，条件边（Conditional Edge）= 动态路由 |
| **最新版本** | 持续迭代中，与 LangChain 生态深度绑定 |
| **Python 要求** | Python 3.9+，同时支持 JavaScript/TypeScript |
| **许可证** | MIT |

**状态管理（核心亮点）：**

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
import operator

# 自定义状态 Schema —— 支持 TypedDict 或 Pydantic BaseModel
class CogCoreState(TypedDict):
    messages: Annotated[list, operator.add]  # 带 reducer 的字段（自动合并）
    perception: dict          # 感知结果
    working_memory: list      # 工作记忆
    belief_pool: dict         # 信念池
    tick_count: int           # 当前 tick 计数
    decay_factor: float       # 衰减因子
```

- **State 是全局唯一事实来源**：所有节点共享同一个 State 对象，每个节点返回部分更新，通过 Reducer 函数合并
- **Reducer 模式**：`Annotated[list, operator.add]` 表示该字段用追加方式合并，而非覆盖。这天然支持 CogCore 的"状态累积"需求
- **自定义状态对象**：支持 TypedDict、Pydantic BaseModel、dataclass，字段可存放任意可序列化对象

**持久化（Checkpointer 机制）：**

| 后端 | 适用场景 |
|------|---------|
| `MemorySaver` | 开发/测试，内存中 |
| `SqliteSaver` | 单机持久化 |
| `PostgresSaver` | 生产级持久化 |
| Redis（社区方案） | 高性能缓存场景 |

- **增量序列化**：只保存变化量（delta），不是全量快照
- **时间旅行调试**：可以回溯到任意历史状态，甚至从历史状态分叉出新执行路径
- **自动恢复**：崩溃后从最近的检查点无缝恢复

**Store API（长期记忆）：**

- 与 Checkpoint（线程内短期记忆）不同，Store 是**跨线程/跨会话的全局持久化键值存储**
- 基于 namespace 组织数据，可在任何时间、任何线程中读写
- 生产环境推荐使用 `PostgresStore`
- **这是实现 CogCore "跨周期状态衰减" 的关键 API**：可以将认知对象的衰减状态存入 Store，在后续 tick 中读取并更新

**工具集成：**
- 原生支持 LangChain Tools 生态（数百个预置工具）
- 支持 MCP（Model Context Protocol）集成
- 支持 human-in-the-loop 人机协作模式
- 支持工具调用的条件分支和重试

**LLM 集成：**
- 通过 LangChain 集成层支持所有主流 LLM：OpenAI、Anthropic、Google、Azure、AWS Bedrock、本地模型等
- **完全模型无关**

**可观测性：**
- **LangSmith** 原生集成（LangChain 的可观测性平台）
- 全生命周期追踪：每个节点的输入/输出、LLM 调用、工具调用
- 时间旅行调试：可视化回放状态流转过程
- 仅需 3 行环境变量配置即可接入

**优势：**
- 图执行模型与 CogCore 的 10 阶段 tick **天然对齐**
- 状态管理是**所有框架中最成熟的**：Reducer + Checkpoint + Store 三层架构
- 生产就绪度最高，社区最活跃
- 可观测性开箱即用

**劣势：**
- 学习曲线较陡（概念多：State、Node、Edge、Reducer、Checkpointer、Store）
- 对简单场景过于重量
- LangChain 生态依赖较重，引入 LangGraph 往往意味着引入整个 LangChain 体系

---

### 2. AutoGen / AG2（微软 → 社区分支）

| 维度 | 详情 |
|------|------|
| **GitHub Stars** | AutoGen ~55K（已进入维护模式），AG2 ~4.2K（社区分支） |
| **核心架构** | **多智能体对话模式**：GroupChat 协调、事件驱动、异步优先 |
| **当前状态** | 2025 年底 AutoGen 进入维护模式；微软战略转向 Microsoft Agent Framework（2026.4 GA） |
| **Python 要求** | Python 3.10+ |
| **许可证** | MIT (AG2) / MIT (AutoGen) |

**状态管理：**
- 以对话历史为核心状态，缺乏显式的图级状态管理
- AG2 新版本引入了 session-based state，但与 LangGraph 的图级状态相比仍有差距
- 没有内建的 Checkpoint 机制

**持久化：**
- 对话级持久化有限
- 无跨执行周期的状态快照
- 不支持时间旅行调试

**工具集成：**
- 支持代码执行、函数调用
- 可插拔的编排策略
- 深度 Azure 集成

**LLM 集成：**
- 多模型支持，Azure OpenAI 优先
- 支持本地模型

**可观测性：**
- AG2 提供了实时决策的深度可观测性
- 但不如 LangSmith 成熟

**优势：**
- 多智能体对话/辩论/协商场景的最佳选择
- 事件驱动架构适合实时编排

**劣势：**
- **生态碎片化严重**：AutoGen（维护模式）→ AG2（社区）→ Microsoft Agent Framework（官方继任），三个分支令人困惑
- **不适合 CogCore 的管线执行模型**：对话模式 ≠ 图执行，无法自然映射 10 阶段 tick
- 状态管理能力不足以支撑认知池 + 衰减模型
- 新项目不建议直接使用 AutoGen

---

### 3. OpenAI Agents SDK

| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~19K |
| **核心架构** | **轻量级 Handoff 链**：从 Swarm 项目演化而来，2026 年新增 Durable Execution 和沙盒执行 |
| **最新版本** | 2026.4.15 发布重大更新 |
| **Python 要求** | Python 3.9+（TypeScript 支持追赶中） |
| **许可证** | MIT |

**状态管理：**
- Handoff 上下文传递（Agent 间切换时传递状态）
- 2026 年新增 Snapshotting + Rehydration 实现 Durable Execution
- 状态管理偏向会话级，缺乏 LangGraph 那样的图级全局状态

**持久化：**
- Durable Execution：容器故障时不丢失数据
- 基于快照和重水合机制
- 但不是 LangGraph 那样的细粒度 Checkpoint

**工具集成：**
- 函数调用（Function Calling）
- 文件系统工具、子 Agent 编排
- 可配置的内存管理
- 2026 年新增 MCP 支持

**LLM 集成：**
- **严重偏向 OpenAI 模型**
- 虽然技术上可以接入其他模型，但框架假设你使用 OpenAI
- 这是最大的限制

**可观测性：**
- 内置追踪 API
- 与 OpenAI 平台的监控集成

**优势：**
- 如果团队已经 all-in OpenAI，上手最快
- 沙盒执行安全性好
- Durable Execution 概念有潜力

**劣势：**
- **模型锁定**：不适合需要多 LLM 提供商的场景
- **架构过于简单**：Handoff 链无法自然表达复杂的图执行和并行管线
- 没有 Reducer/状态合并机制
- 没有长期记忆 Store API
- **不适合 CogCore 的多阶段认知 tick 模型**

---

### 4. Smolagents（HuggingFace）

| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~26K |
| **核心架构** | **极简代码 Agent**：整个框架约 1000 行代码，Agent 直接生成 Python 代码片段执行 |
| **Python 要求** | Python 3.10+ |
| **许可证** | Apache 2.0 |

**状态管理：**
- **无内建状态管理**
- 无工作流编排
- 无状态图

**持久化：**
- **无内建持久化机制**
- 需要完全自行实现

**工具集成：**
- 通过 LiteLLM 实现模型无关
- 支持多模态（视觉、音频）
- 工具以 Python 函数形式注册

**LLM 集成：**
- 通过 LiteLLM 支持几乎所有模型
- 模型无关性最强

**可观测性：**
- 极简，几乎没有内建追踪
- 需要外部工具

**优势：**
- 激进的简洁性：1000 行代码完全透明
- 减少 LLM 调用次数（代码执行代替多轮对话）
- 适合学习和原型开发

**劣势：**
- **不适合作为 CogCore 底层框架**：缺乏状态管理、持久化、工作流编排
- 需要从近乎零开始构建所有基础设施
- 没有企业级特性

---

### 5. PydanticAI（Pydantic 团队）

| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~17K |
| **核心架构** | **类型安全 Agent 框架**：将 FastAPI 的开发体验带入 Agent 领域，附带 `pydantic-graph` 子模块用于图工作流 |
| **最新版本** | v1.0.1+（2025 年底正式发布） |
| **Python 要求** | Python 3.9+ |
| **许可证** | MIT |

**状态管理：**
- 基于 Pydantic 模型的强类型状态
- `pydantic-graph` 提供图工作流：节点通过共享可变状态对象传递数据
- 支持并行执行和条件分支（Builder 模式）
- 状态默认无持久化，需手动集成 Temporal 等外部系统

**持久化：**
- **Durable Execution** 通过与 Temporal 集成实现（官方推荐）
- 支持 human-in-the-loop 的进度保持
- 不如 LangGraph 原生 Checkpoint 那样开箱即用

**工具集成：**
- 内建网页搜索、思考工具
- 原生 MCP 支持
- 内置 harness 库

**LLM 集成：**
- **支持 20+ LLM 提供商**
- 模型无关性最好之一
- 类型安全的模型响应验证

**可观测性：**
- Pydantic Logfire（同团队的可观测性产品）原生集成
- 结构化日志

**优势：**
- **类型安全**：编译期捕获错误，IDE 支持最好
- `pydantic-graph` 提供了独立的图工作流引擎
- 与 Temporal 集成可实现强大的 Durable Execution
- 依赖注入模式优雅

**劣势：**
- `pydantic-graph` 相比 LangGraph 的 StateGraph **成熟度不足**
- 没有内建的 Reducer/状态合并机制
- 长期记忆（Store）概念不存在
- 社区规模和生产验证不如 LangGraph

---

### 6. 其他值得关注的框架

#### CrewAI
| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~44.6K（社区热度最高） |
| **核心架构** | **角色化多智能体团队**：研究员、写手、编辑等角色协作 |
| **状态管理** | 抽象优先，缺乏内建 Checkpoint |
| **持久化** | Agent 间通信的持久化控制有限 |
| **适用性** | 适合快速原型（~20 行代码即可运行），但**生产环境常迁移到 LangGraph** |
| **CogCore 适配** | 不推荐：角色化模型与认知管线模型不匹配 |

#### DSPy（Stanford）
| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~25K |
| **核心架构** | **编程式 LLM 优化框架**：用代码模块而非 prompt 来编排 LLM |
| **状态管理** | 模块组合式，无显式图状态 |
| **核心特色** | 自动优化 prompt、Pipeline 编译 |
| **CogCore 适配** | 不推荐：定位是 LLM 编程抽象层，不是执行引擎 |

#### Google ADK（Agent Development Kit）
| 维度 | 详情 |
|------|------|
| **GitHub Stars** | ~11K |
| **核心架构** | 图执行引擎（路由、扇出/扇入、循环） |
| **状态管理** | 自动上下文管理和任务恢复 |
| **持久化** | 内建任务启动和故障处理 |
| **CogCore 适配** | 有潜力但生态绑定 Google Cloud，离开 GCP 价值减弱 |

#### Microsoft Agent Framework（MAF）
| 维度 | 详情 |
|------|------|
| **GitHub Stars** | 新发布，积累中 |
| **核心架构** | 图工作流 API + 可对话 Agent，AutoGen 的精神继任者 |
| **GA 时间** | 2026 年 4 月 3 日 |
| **CogCore 适配** | 太新，生态未成熟，建议观望 |

---

## 三、关键维度横向对比

### 3.1 与 CogCore 需求的匹配度矩阵

| 框架 | 图/管线执行 | 持久化状态+衰减 | 自定义状态对象 | 工具集成 | LLM 集成 | 可观测性 | **综合适配度** |
|------|:---------:|:-------------:|:-----------:|:------:|:------:|:------:|:-----------:|
| **LangGraph** | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★★ | **★★★★★** |
| **PydanticAI** | ★★★★☆ | ★★★☆☆ | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★☆ | **★★★☆☆** |
| **OpenAI SDK** | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ | ★★★☆☆ | **★★☆☆☆** |
| **AG2/AutoGen** | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | **★☆☆☆☆** |
| **Smolagents** | ★☆☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★★ | ★☆☆☆☆ | **★☆☆☆☆** |
| **CrewAI** | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ | **★☆☆☆☆** |
| **DSPy** | ★★★☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ | **★★☆☆☆** |

### 3.2 架构模型与 CogCore 的映射关系

```
CogCore 10 阶段认知 Tick 的理想映射：

┌─────────────────────────────────────────────────────┐
│                  CogCore StateGraph                  │
│                                                     │
│  ┌──────┐   ┌──────┐   ┌──────┐       ┌──────┐    │
│  │感知   │──▶│注意   │──▶│推理   │──▶...──▶│行动   │    │
│  │Percep.│   │Attend│   │Reason│       │Act   │    │
│  └──────┘   └──────┘   └──────┘       └──────┘    │
│      │           │           │               │      │
│      └───────────┴───────────┴───────────────┘      │
│              State (Reducer 合并)                    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  Checkpointer: 每个 tick 后自动快照          │    │
│  │  Store: 跨 tick 的长期认知状态 + 衰减        │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

**只有 LangGraph 的 StateGraph 能直接表达这种结构。**

### 3.3 状态管理能力深度对比

| 能力 | LangGraph | PydanticAI | OpenAI SDK | AG2 |
|------|-----------|------------|------------|-----|
| 图级全局状态 | TypedDict/Pydantic + Reducer | pydantic-graph 共享状态 | Handoff 上下文 | 对话历史 |
| 状态合并策略 | Annotated Reducer（自定义函数） | 手动管理 | 无 | 无 |
| 线程内检查点 | 原生（Memory/SQLite/Postgres/Redis） | 需集成 Temporal | Snapshot/Rehydration | 无 |
| 跨线程长期记忆 | Store API（namespace 键值存储） | 无 | 无 | 无 |
| 时间旅行调试 | 原生支持 | 不支持 | 不支持 | 不支持 |
| 增量序列化 | 原生（仅保存 delta） | 不支持 | 部分 | 不支持 |
| 自定义衰减逻辑 | 通过 Reducer + Store 实现 | 需完全自建 | 需完全自建 | 需完全自建 |

---

## 四、最终推荐

### 首选：LangGraph

**LangGraph 是唯一一个在所有六个 CogCore 需求维度上都表现优秀的框架。** 其核心优势在于：

1. **StateGraph 天然映射 10 阶段认知 Tick**
   - 每个认知阶段 = 一个 Node
   - 阶段间数据流转 = Edge + State
   - 条件路由 = Conditional Edge（如：根据认知状态决定跳过或重复某阶段）
   - 循环 = 从末节点回到首节点（认知 tick 的周期性）

2. **Reducer 机制完美适配"状态池"模型**
   - CogCore 的"认知池"可以建模为 State 中的多个字段
   - Annotated Reducer 允许自定义合并策略（追加、覆盖、衰减加权等）
   - 例如：`belief_pool: Annotated[dict, belief_decay_reducer]` 可以实现信念的自动衰减

3. **Checkpoint + Store 双层持久化**
   - Checkpoint：单个认知 tick 内的状态快照，支持崩溃恢复
   - Store：跨多个 tick 的长期认知状态，支持衰减更新
   - 这双层架构与 CogCore 的"短期工作记忆 + 长期认知积累"完全对齐

4. **自定义状态对象**
   - Pydantic BaseModel 作为 State Schema → 类型安全 + 验证
   - 字段可存放任意可序列化的复杂对象（认知向量、信念网络等）

5. **生产就绪**
   - 企业级部署最多，月下载量 3450 万+
   - LangSmith 提供开箱即用的可观测性
   - 活跃的社区和持续的版本迭代

### 次选方案：自建混合架构

如果团队希望避免 LangChain 生态的重量级依赖，可以考虑：

**PydanticAI (Agent 层) + pydantic-graph (图执行) + Temporal (持久化)**

这种组合的优势：
- 类型安全（Pydantic 原生）
- 依赖更轻
- Temporal 提供工业级 Durable Execution
- 需要从 LangGraph 借鉴 Reducer 和 Store 的设计模式自行实现

但这种方案的开发工作量显著更大，适合有充足工程资源的团队。

### 不推荐的框架

| 框架 | 不推荐原因 |
|------|-----------|
| AutoGen/AG2 | 生态碎片化，对话模型不适合管线执行，已进入维护模式 |
| OpenAI Agents SDK | 模型锁定，架构过于简单，缺乏图执行和状态合并 |
| Smolagents | 极简主义，缺乏所有企业级基础设施 |
| CrewAI | 角色化模型与认知管线不匹配，生产环境常迁移 |
| DSPy | 定位不同（LLM 编程抽象层），不是执行引擎 |

---

## 五、LangGraph 落地 CogCore 的架构蓝图

```
建议的技术栈：

核心执行层:    langgraph (StateGraph + Nodes + Edges)
状态定义层:    pydantic BaseModel (作为 State Schema)
短期持久化:    langgraph.checkpoint.postgres (PostgresSaver)
长期持久化:    langgraph.store.postgres (PostgresStore)
可观测性:      LangSmith (tracing + debugging)
LLM 层:       langchain-openai / langchain-anthropic (模型无关)
工具层:        LangChain Tools + MCP 集成
部署层:        LangGraph Cloud 或自托管 LangGraph Server
```

**认知 Tick 的 LangGraph 实现示例（伪代码）：**

```python
from pydantic import BaseModel, Field
from typing import Annotated, Any
from langgraph.graph import StateGraph, START, END
import operator

# === 自定义认知状态对象 ===
class BeliefObject(BaseModel):
    content: str
    confidence: float
    decay_rate: float
    created_at: float

class CognitiveState(BaseModel):
    """CogCore 认知状态 Schema"""
    # 感知缓冲区
    perception_buffer: list[dict] = Field(default_factory=list)
    # 注意力焦点
    attention_focus: str | None = None
    # 工作记忆
    working_memory: list[dict] = Field(default_factory=list)
    # 信念池
    belief_pool: dict[str, BeliefObject] = Field(default_factory=dict)
    # 情绪状态
    emotional_valence: float = 0.0
    # 行动计划
    action_plan: list[dict] = Field(default_factory=list)
    # Tick 元数据
    tick_number: int = 0
    cumulative_decay: float = 1.0

# === Reducer：自定义合并策略 ===
def belief_merge_reducer(
    existing: dict[str, BeliefObject],
    update: dict[str, BeliefObject]
) -> dict[str, BeliefObject]:
    """信念池合并：新信念加入，旧信念衰减"""
    merged = {k: v for k, v in existing.items()}
    for key, belief in update.items():
        if key in merged:
            # 已有信念：更新置信度
            merged[key].confidence = min(
                1.0,
                merged[key].confidence + belief.confidence * 0.5
            )
        else:
            merged[key] = belief
    # 全局衰减
    for key, belief in merged.items():
        belief.confidence *= belief.decay_rate
    return merged

# === State 定义 ===
class CogCoreGraphState(TypedDict):
    perception_buffer: Annotated[list, operator.add]
    attention_focus: str | None
    working_memory: Annotated[list, working_memory_reducer]
    belief_pool: Annotated[dict, belief_merge_reducer]  # 自定义 Reducer!
    emotional_valence: float
    action_plan: list
    tick_number: int
    cumulative_decay: float

# === 构建认知图 ===
graph = StateGraph(CogCoreGraphState)

# 10 个认知阶段 = 10 个 Node
graph.add_node("perceive", perception_stage)      # 感知
graph.add_node("attend", attention_stage)          # 注意
graph.add_node("encode", encoding_stage)           # 编码
graph.add_node("retrieve", retrieval_stage)        # 检索
graph.add_node("reason", reasoning_stage)          # 推理
graph.add_node("plan", planning_stage)             # 规划
graph.add_node("evaluate", evaluation_stage)       # 评估
graph.add_node("act", action_stage)                # 行动
graph.add_node("reflect", reflection_stage)        # 反思
graph.add_node("consolidate", consolidation_stage) # 巩固

# 边：阶段间流转
graph.add_edge(START, "perceive")
graph.add_edge("perceive", "attend")
graph.add_edge("attend", "encode")
graph.add_edge("encode", "retrieve")
graph.add_edge("retrieve", "reason")
graph.add_edge("reason", "plan")
graph.add_edge("plan", "evaluate")
graph.add_edge("evaluate", "act")
graph.add_edge("act", "reflect")
graph.add_edge("reflect", "consolidate")

# 条件边：巩固后决定是开始新 tick 还是终止
graph.add_conditional_edges(
    "consolidate",
    should_continue_tick,  # 返回 "next_tick" 或 "end"
    {"next_tick": "perceive", "end": END}
)

# === 编译并附加 Checkpointer + Store ===
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
store = PostgresStore.from_conn_string(DATABASE_URL)

cogcore = graph.compile(
    checkpointer=checkpointer,
    store=store
)
```

---

## 六、风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| LangChain 生态过重 | 可以仅使用 `langgraph` 核心包，不依赖完整 LangChain |
| LangSmith 是付费服务 | 可用 Langfuse、Phoenix 等开源替代 |
| LangGraph 版本迭代快，API 可能变化 | 锁定版本，关注 breaking changes |
| Postgres 依赖（生产环境） | 开发阶段用 MemorySaver，部署时用 Postgres |
| 状态对象的序列化复杂度 | 使用 Pydantic BaseModel 确保可序列化 |

---

## 七、结论

**LangGraph 是 CogCore 认知内核系统的最佳底层框架选择。**

它的有向状态图架构、Reducer 状态合并机制、Checkpoint + Store 双层持久化，以及成熟的工具链生态，是目前唯一一个能够自然映射 CogCore 的"状态池 + 管线执行 + 跨周期衰减"模型的框架。

PydanticAI 可作为类型安全层的补充（用 Pydantic BaseModel 定义 CogCore 的 State Schema），但不应替代 LangGraph 作为执行引擎。

建议采用 **LangGraph + Pydantic + PostgresSaver + LangSmith** 的技术栈组合来实施 CogCore。
