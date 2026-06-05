# AGENT_BUILD.MD — 从 CogCore 到完整智能体

> **这是 CogCore 的"产品化桥接文档"**——回答"如何用 CogCore 认知内核 + 4 个参考项目的能力，打造一个真正可用的完整智能体"。
>
> 适用于：已经读过 [README.md](./README.md) / [PURPOSE.MD](./PURPOSE.MD) / [DESIGN.MD](./DESIGN.MD)，知道 CogCore 是什么，现在要把它"组装"成一个能跑、能用、能部署的 Agent。

---

## 0. 一句话定位

**完整智能体 = LangGraph 图引擎 + CogCore 认知层 + LLM 解释层 + 工具层 + 长期记忆 + 部署基础设施。**

CogCore 已经是认知层；本指南聚焦"剩下的 5 层怎么选、怎么接、怎么落地"。

## 1. 4 个参考项目的能力地图

| 维度 | [wassim249/fastapi-langgraph-agent-production-ready-template](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) | [langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) | [hereandnowai/master-langgraph-workflows-in-python-20-real-world-agent-projects](https://github.com/hereandnowai/master-langgraph-workflows-in-python-20-real-world-agent-projects-by-hereandnow-ai) | [0x-Professor/LangGraph-Practice](https://github.com/0x-Professor/LangGraph-Practice) |
|---|---|---|---|---|
| **定位** | 生产级 FastAPI 后端模板 | 极简 ReAct Agent 模板 | 20 个真实业务场景合集 | 8 种 LangGraph 工作流模式教学 |
| **规模** | ⭐ 2.4k / 🍴 548 | ⭐ 760 / 🍴 688 | ⭐ 38 / 🍴 7 | ⭐ 12 / 🍴 1 |
| **核心贡献** | 完整生产基础设施 | 最小可跑图核心 | 业务场景广度 | 工作流模式深度 |
| **图引擎** | LangGraph + 节点级 RetryPolicy | LangGraph `create_react_agent` | LangGraph v0.5.3 | LangGraph 8 种模式 |
| **状态管理** | StateGraph + Checkpointer + Store | MemorySaver | 按项目（多数 MemorySaver） | MemorySaver + State Persistence |
| **长期记忆** | **mem0 + pgvector** | 无显式 | 各项目自带 | State Persistence 示例 |
| **可观测性** | **Langfuse + Prometheus + Grafana + 结构化日志** | LangSmith | 输出文件 | 无显式 |
| **多 LLM** | **LLMRegistry + LLMService（circular fallback）** | Anthropic / OpenAI 切换 | 统一用 Cerebras | Google Gemini（langgraph-google-genai） |
| **工具** | `@tool` 装饰器 + 动态注册 | MCP 工具 | 各种 | 基础 |
| **部署** | **Docker + Alembic + JWT + slowapi 速率限制** | LangGraph Platform | 单 `python main.py` | 单文件 |
| **测试** | `evals/` 评测 + unit + integration + 烟雾测试 | unit + integration | 无 | `practice.ipynb` |
| **HITL** | 无显式 | 提示可在 tool 前加 interrupt | project-03 有专门实现 | 无 |
| **关键可借鉴** | **生产基础设施完整** | **图核心最简洁** | **业务模板广** | **模式教学清** |

## 2. CogCore 当前缺口（与 4 个项目对比）

| 维度 | CogCore 现状 | wassim249 | react-agent | hereandnowai | 0x-Professor | 缺口 |
|------|------------|-----------|-------------|--------------|---------------|------|
| **图引擎** | 纯 Python `pipeline.run_cycle` | LangGraph | LangGraph | LangGraph | LangGraph | **需要 LangGraph 集成** |
| **状态合并** | 无显式 Reducer | 完整 Reducer | 隐式 | 隐式 | 隐式 | **需要补 Reducer** |
| **持久化** | 内存 stub | Postgres + Alembic | MemorySaver | MemorySaver | MemorySaver | **需要 PostgresSaver + Store** |
| **长期记忆** | 仅 StatePool | mem0 + pgvector | 无 | 各种 | State Persistence | **需要 mem0 或 HDB-as-Memory** |
| **可观测性** | 仅 `Observatory` stub | Langfuse + Prom + Grafana | LangSmith | 输出文件 | 无 | **需要 Langfuse / LangSmith 集成** |
| **多 LLM** | 无 | LLMRegistry | 多 provider | 单一（Cerebras） | 单一（Gemini） | **需要 LLMRegistry 模式** |
| **错误处理** | 无 | RetryPolicy + circular fallback | 无 | 无 | 无 | **需要节点级重试 + 模型回退** |
| **工具集成** | ToolRegistry stub | `@tool` 装饰器 + 动态注册 | MCP tools | 各种 | 基础 | **需要 LangChain Tool 包装** |
| **HITL** | 无 | 无 | 提示可加 interrupt | project-03 | 无 | **可加 interrupt_before** |
| **部署** | 无 | Docker + FastAPI | LangGraph Platform | 无 | 无 | **需要 FastAPI + Docker** |
| **测试** | 5 个烟雾测试 | evals/ + unit + integration | unit + integration | 无 | practice.ipynb | **需要 evals/ 模块 + integration** |
| **业务模板** | 0 个 | 0 个（通用） | 1 个 | **20 个** | 8 个 | **需要从 hereandnowai 提炼通用模式** |

## 3. 完整智能体的"完整"清单

按 4 个项目的能力交叉，得到 11 个必备维度：

```
┌──────────────────────────────────────────────────────────────┐
│                      完整智能体能力栈                          │
│                                                              │
│  L1 应用层 ─── FastAPI / WebSocket / Studio                   │
│  L2 图引擎 ─── LangGraph StateGraph（10 节点 = CogCore 流水线）│
│  L3 认知层 ─── CogCore（StatePool + HDB + 9 模块）★         │
│  L4 解释层 ─── LLMRegistry + LLMService + circular fallback   │
│  L5 工具层 ─── LangChain Tools + MCP + tool_allowlist        │
│  L6 记忆层 ─── HDB（结构）+ pgvector（语义）+ 长期日记/任务    │
│  L7 持久化 ── PostgresSaver + Store + Alembic migration      │
│  L8 可观测性 ─ Langfuse / LangSmith + Prom + Grafana         │
│  L9 部署层 ── Docker + Docker Compose + JWT + slowapi         │
│  L10 错误处理 ─ RetryPolicy + circular fallback + structured │
│  L11 测试 ── evals/ + unit + integration + smoke              │
└──────────────────────────────────────────────────────────────┘
                                                  ★ = CogCore 已就位
```

## 4. CogCore 在完整智能体中的角色

```
        ┌──────────┐   外源输入   ┌──────────────────┐
        │  LLM     │ ─────────▶  │                  │
        │ 解释层    │             │                  │
        │ (Claude  │             │   CogCore        │
        │  Sonnet  │             │   认知层          │
        │  / GPT)  │             │                  │
        └────▲─────┘  行动选择   │  ┌────────────┐  │
             │                  │  │ StatePool  │  │
             │                  │  │ HDB 查存    │  │
             │                  │  │ 感应生长    │  │
             │                  │  │ Attention   │  │
        ┌────┴────┐   工具调用   │  │ CFS/NT/    │  │
        │  Lang-  │ ─────────▶  │  │ ActionSys  │  │
        │  Graph  │             │  └────────────┘  │
        │  工具层  │ ◀─────────  │                  │
        └─────────┘   工具结果   └──────────────────┘
```

**关键不变量**：CogCore 不替代 LangGraph；它是 LangGraph 节点之间的"状态层"。每次 tick，CogCore 给出当前在意的对象（CAM），LLM 基于此决定下一步行动。

## 5. 推荐技术栈

| 层 | 选型 | 理由 |
|---|------|------|
| **L1 应用层** | FastAPI | wassim249 已验证；与 LangGraph 集成成熟 |
| **L2 图引擎** | LangGraph | 4 个项目统一选型；Reducer + Checkpointer + Store 三层架构 |
| **L3 认知层** | **CogCore** | 自研，AP 闭环 |
| **L4 解释层** | LangChain ChatModel + LLMRegistry | 多个项目验证；circular fallback 模式 |
| **L5 工具层** | LangChain `@tool` + MCP | wassim249 + react-agent 双验证 |
| **L6 记忆层** | HDB（结构）+ pgvector（语义）+ mem0（事实） | wassim249 模式；HDB 提供可解释性 |
| **L7 持久化** | PostgresSaver + PostgresStore + Alembic | LangGraph 原生 + wassim249 实践 |
| **L8 可观测性** | Langfuse（自托管可换 LangSmith）+ Prom + Grafana | wassim249 已验证全栈 |
| **L9 部署层** | Docker + Docker Compose | wassim249 标准做法 |
| **L10 错误处理** | tenacity 重试 + LLMRegistry circular fallback | wassim249 实践 |
| **L11 测试** | pytest + LangSmith Evals + custom evaluator | 4 个项目综合 |

## 6. 实施路线（4 阶段）

### 阶段 A：图引擎替换（M0.1 → M0.5）✅ 已完成

**目标**：把 `pipeline.run_cycle` 从纯 Python 转成 LangGraph StateGraph。

**状态**：M0.5 已于 2026-06-05 完成。`src/cogcore/graph.py` 提供 `build_cogcore_graph()`——10 节点 StateGraph + MemorySaver checkpointer。138/138 测试通过。

**起点**：[langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) 的 `src/react_agent/graph.py` 模式

**实际产出**：```
$ python -m cogcore.run "明天上海出门"
CogCore M0.5 (LangGraph 集成版)
输入: '明天上海出门，帮我看看要不要带伞' (modality=text)
=== Tick 0 报告 ===
完成阶段: 10/10
  1. stage_1_sensor_input
  ...
 10. stage_10_adaptive_tune
StatePool: active=1, total_e=1.00
NT: arousal=0.300, caution=0.400
Action: total_executions=1
```

**关键改动**：

```python
# 之前（CogCore M0.1 骨架）
def run_cycle(raw_input, ...) -> TickReportDC:
    for stage_fn in [stage_1, stage_2, ..., stage_10]:
        result = _safe_call(stage_fn, ...)

# 之后（M0.5）
from langgraph.graph import StateGraph, START, END

class CogCoreState(TypedDict):
    tick: int
    new_atoms: list[StimulusAtom]
    cam: CurrentAttentionMemory
    nt_values: NTModulations
    # ... 见 docs/CogCore-验证矩阵.md 第 3 节

graph = StateGraph(CogCoreState)
graph.add_node("perceive", stage_1_sensor_input)
graph.add_node("pool_maintenance", stage_2_state_pool_maintenance)
graph.add_node("hdb_lookup", stage_3_hdb_lookup)
# ... 10 个节点
graph.add_conditional_edges("adapt_tune", should_continue, {"next": "perceive", "end": END})
cogcore = graph.compile(checkpointer=PostgresSaver(...), store=PostgresStore(...))
```

**退出标准**：能用 `cogcore.invoke({"raw_input": "..."})` 跑通 10 阶段，状态可在 LangGraph Studio 可视化。

### 阶段 B：LLM 解释层接入（M1.1 → M1.5）✅ 已完成

**目标**：让 LLM 能读 CogCore 状态、决定行动。

**状态**：M1.1 已于 2026-06-05 完成。`LLMBridge` 通过 OpenAI SDK 连接 Ollama/OpenAI/vLLM，`build_context_packet` 输出 8 类审计字段，`chat_with_state` 实现 CogCore→LLM→CogCore 一步闭环。

**起点**：[wassim249](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) 的 `app/services/llm/` 拆分模式（registry + service）

**关键模块**（在 `src/cogcore/llm_bridge.py` 基础上扩展）：

- `LLMRegistry`：管理多个 LLM 客户端
- `LLMService`：调用入口，带 circular fallback
- `build_context_packet`：把 CogCore tick report 翻译成 LLM prompt
- `parse_llm_output`：把 LLM 输出解析为 StimulusAtom

### 阶段 C：工具与记忆（M1.2 → M1.4）✅ 已完成

**目标**：让 Agent 能用工具、能记住事实。

**状态**：M1.2-M1.4 已全部完成。SQLite 持久化（`build_cogcore_graph_persistent`）零 Docker 依赖；ToolRegistry + LongTermExperienceTools（write_diary/read_diary/schedule_task）全部可用；PA 运行模式（full_silent/ap_agency/reinforced_agency）已实现。

**起点**：[wassim249](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) 的 mem0 + pgvector 模式 + [hereandnowai project-16](https://github.com/hereandnowai/master-langgraph-workflows-in-python-20-real-world-agent-projects-by-hereandnow-ai) 的 Knowledge Base 模式

**关键模块**：
- `ToolRegistry` 扩展为 LangChain `@tool` 包装
- 新增 `mem0_adapter.py`（事实抽取与召回）
- 长期经验工具（write_diary / read_diary / schedule_task）已在主文档 §6.2.1 设计

### 阶段 D：部署与可观测性（M1.5 → M2）

**目标**：从"能跑"到"能生产"。

**起点**：[wassim249](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) 的全套基础设施

**关键交付**：
- `app/api/v1/chatbot.py`（FastAPI 端点）
- `app/core/middleware.py`（JWT + slowapi）
- `alembic/` 迁移
- `grafana/dashboards/` 模板
- `prometheus/` 配置
- `Dockerfile` + `docker-compose.yml`
- `evals/` 评测套件

## 7. 关键架构决策（从 4 个项目吸收的）

### 7.1 LLM 节点 vs 工具节点

**react-agent 模式**（最小图）：
```
[LLM] → [Tools] → [LLM] → ... → [END]
```

**CogCore 扩展模式**（带认知层）：
```
[CogCore tick] → [LLM 决策] → [Tools 执行] → [CogCore 反馈] → [next tick] → ...
```

**决策**：CogCore 不替代 ReAct 循环，而是把每次 ReAct 决策前的"当前状态"组织成可解释的上下文。

### 7.2 长期记忆的双轨

- **结构记忆**：HDB（可解释、查存一体）
- **事实记忆**：mem0 或 pgvector（语义相似）

**决策**：CogCore HDB 是 L1，mem0 是 L2，两者通过 `ActionSystem.process_feedback` 协作。

### 7.3 可观测性分层

- **追踪（trace）**：Langfuse 或 LangSmith（每节点/每 LLM 调用）
- **指标（metrics）**：Prometheus + Grafana（吞吐量、延迟、错误率）
- **审计（audit）**：CogCore Observatory（每 tick 的 10 阶段快照 + SHA-256）

**决策**：所有报告都带 SHA-256 哈希锚点（论文 5.6.1），可跨系统回溯。

### 7.4 错误处理三层

- **节点级**：RetryPolicy（tenacity，max_attempts=3）
- **模型级**：circular fallback（LLMRegistry 轮转）
- **系统级**：教师门控（`teacher_gate_should_wake`）— 论文 5.7.3

**决策**：CogCore 的 adaptive_tuner + 行动系统对长期稳定性负责，前两层处理瞬时错误。

### 7.5 状态合并模式（Pydantic + StateUpdater + Reducer 契约）⚠️ M0.5 必读

⚠️ 关键陷阱：LangGraph 节点返回的是**部分更新（patch）**，默认合并会**覆盖整个嵌套对象**。如果 CogCoreState 包含复杂嵌套（`cam` / `nt_values` / `pool_snapshot`），不显式定义 Reducer 会导致「脑损伤式」数据丢失。

**两种合规模式**：

| 模式 | 适用场景 | 优缺点 |
|------|---------|--------|
| **A. Pydantic + StateUpdater** | 嵌套对象用 Pydantic BaseModel（推荐） | `StateUpdater` 链式调用 + `model_copy(update=...)` 天然安全 |
| **B. TypedDict + Annotated Reducer** | 全部字段用 TypedDict + 显式 `Annotated[list, add]` | 需每个节点手动控制 patch 边界 |

**CogCore 采用 A**（Pydantic 模式）。完整定义见 `src/cogcore/state_schema.py`：

```python
from typing import Annotated
from operator import add
from pydantic import BaseModel, Field

class CogCoreState(BaseModel):
    tick: int = 0
    raw_input: str = ""

    # 嵌套对象——默认整体替换（不会被部分清空）
    nt_values: NTModulations = Field(default_factory=NTModulations)
    cam: CurrentAttentionMemory | None = None
    pool_snapshot: StatePoolSnapshot = Field(default_factory=StatePoolSnapshot)
    hdb_snapshot: HDBSnapshot = Field(default_factory=HDBSnapshot)

    # 列表——用 Annotated + add Reducer 显式累加
    new_atoms: Annotated[list[StimulusAtom], add] = Field(default_factory=list)
    grown_atoms: Annotated[list[StimulusAtom], add] = Field(default_factory=list)
    stages_log: Annotated[list[str], add] = Field(default_factory=list)
    error_log: Annotated[list[str], add] = Field(default_factory=list)
```

**StateUpdater 链式 API（推荐写法）**：

```python
def stage_node(state: CogCoreState) -> dict:
    return (
        make_updater(state)
        .patch_nt_values(focus=0.5)          # 嵌套对象：model_copy 深合并，不预累加
        .append_atoms([atom_a, atom_b])      # 列表：仅记录增量，不与现有 state 拼接
        .append_stage("stage_3_hdb_lookup")  # 列表：仅记录增量
        .to_patch()                           # → 返回 dict，LangGraph 应用 Reducer
    )
```

**节点返回 5 种错误模式必须避免**：

1. ❌ 返回部分嵌套 dict：`{"nt_values": {"focus": 0.5}}`（其他子字段丢失，陷阱 T1）
2. ❌ 字段拼写错误：`{"new_atom": some_atom}`（静默丢失，陷阱 T4）
3. ❌ 返回完整 state：绕过 Reducer（陷阱 T3）
4. ❌ 跨节点修改全局：破坏可重入性（陷阱 T2）
5. ❌ **Fluent API 双重累加**（陷阱 T5，2026-06-05 用户捕获）：
   - 如果辅助方法（如 `state.append_atoms([B])`）返回完整 `CogCoreState` 实例
   - 内部已做 `model_copy(update={"new_atoms": self.new_atoms + [B]})`，返回 `new_atoms = [A, B]`
   - LangGraph 拿到 dict，add reducer 触发 `existing [A] + update [A, B] = [A, A, B]` 💥
   - **100 轮后 `stages_log` 指数膨胀**

**修复**：`StateUpdater` 累积 patch dict（不预累加），`.to_patch()` 返回深拷贝的 dict。

**决策**：所有节点必须返回 `dict[str, Any]`。使用 `make_updater(state).xxx().to_patch()` 风格。

**验证**：
- `tests/test_state_schema.py` 20 个测试（13 patch + 4 Reducer + 3 双重累加反例）
- `docs/CogCore-验证矩阵.md` §7 「已知实现陷阱」 T1-T5
- `docs/CogCore-通用认知内核架构设计.md` §6.4 完整契约 + 陷阱 T5 详细说明

## 8. 业务场景起点（来自 hereandnowai 20 个项目）

按"bitesized"原则，CogCore 的 M1 阶段建议先落地 5 个最常见的业务场景：

| # | 场景 | hereandnowai 项目 | 关键技术点 |
|---|------|-------------------|----------|
| 1 | 基础对话 | project-01 | 单轮 StateGraph + CogCore tick |
| 2 | 工具调用 | project-02 | LangChain @tool + 行动节点 |
| 3 | 人工干预 | project-03 | interrupt_before + 教师门控 |
| 4 | 多 Agent 协作 | project-05 | 多个 CogCore 实例 + Store 共享 |
| 5 | 长期陪伴 | project-11 + project-12 | mem0 + HDB + 定时任务 |

每个场景的复现都对应 `CogCore-验证矩阵.md` 第 4 节中的未来实验（E18-E25）。

## 9. 禁止的事（与 `AGENTS.md` 一致）

- **不修改 CogCore 状态列**：所有 17 个实验标"计划"，未跑通不标"通过"
- **不擅自扩 scope**：see [PURPOSE.MD](./PURPOSE.MD) 第 4 节
- **不带 commit hash 不改"已通过"**：see `docs/CogCore-验证矩阵.md` 第 5.3 节

## 10. 快速验证清单

在开始实施前，确认你能回答：

- [ ] CogCore 9 个核心模块的接口都看过 [DESIGN.MD](./DESIGN.MD) 第 3 节
- [ ] 4 个参考项目的目录结构都浏览过
- [ ] 17 个 E0X 实验的"研究目标"都能复述（见 `docs/CogCore-验证矩阵.md`）
- [ ] 知道 11 层能力栈中 CogCore 只覆盖 L3（见第 3 节）
- [ ] 知道 M0-M2 三阶段路线（见 [docs/CogCore-通用认知内核架构设计.md](./docs/CogCore-通用认知内核架构设计.md) 第 10 章）

回答"是"才能进入实施。

---

## 附录：参考链接

- **CogCore 自有文档**：
  - [PURPOSE.MD](./PURPOSE.MD) — 需求
  - [DESIGN.MD](./DESIGN.MD) — 设计
  - [AGENTS.md](./AGENTS.md) — AI Agent 操作手册
  - [docs/CogCore-通用认知内核架构设计.md](./docs/CogCore-通用认知内核架构设计.md) — 完整架构
  - [docs/CogCore-验证矩阵.md](./docs/CogCore-验证矩阵.md) — 17 实验 + 模块映射
  - [docs/cogcore_framework_research.md](./docs/cogcore_framework_research.md) — LangGraph 选型
  - [docs/人工心智架构-论文分析.md](./docs/人工心智架构-论文分析.md) — AP 论文分析

- **4 个参考项目**：
  - [wassim249/fastapi-langgraph-agent-production-ready-template](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) — 生产基础设施
  - [langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) — 极简图核心
  - [hereandnowai/master-langgraph-workflows-in-python-20-real-world-agent-projects](https://github.com/hereandnowai/master-langgraph-workflows-in-python-20-real-world-agent-projects-by-hereandnow-ai) — 业务场景广度
  - [0x-Professor/LangGraph-Practice](https://github.com/0x-Professor/LangGraph-Practice) — 工作流模式深度

- **底层论文**：
  - [Artificial PsyArch（AP）论文附件仓库](https://github.com/ginsonko/Artificial-PsyArch-test-)

---

*最后更新：2026-06-05（M0.5 LangGraph 集成完成，138 测试全过）*
