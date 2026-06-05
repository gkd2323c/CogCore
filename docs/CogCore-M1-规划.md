# CogCore M1 阶段规划：应用耦合 + LLM 桥接

> **阶段定位**：把 CogCore 从「认知内核原型」变成「可接入 LLM 和工具的 Agent 底座」。
>
> 前置条件：阶段一（M0.1-M0.9 / E01-E17）已于 2026-06-05 全部完成。

---

## 1. 阶段目标

M1 的核心命题：**CogCore 已经能自己跑认知闭环了，但它怎么跟外面的世界对话？**

阶段目标是把 CogCore 接入：
1. **LLM**（本地 Ollama）——让 LLM 能读 CogCore 状态、能决定下一步做什么
2. **持久化存储**（PostgreSQL）——让认知状态跨会话存活
3. **工具系统**（ToolRegistry）——让 CogCore 能调用外部工具
4. **运行模式**（PA 双层）——让三种主动性能级可切换

### 阶段退出条件

| 条件 | 检查点 |
|------|--------|
| LLM 能读到 CogCore 的 tick 状态 | `build_context_packet` 输出包含全部 8 类审计字段 |
| LLM 回复能回写为 CogCore 内源刺激 | `parse_llm_output` 单次调用成功 |
| CogCore 状态跨会话持久化 | 两次 invoke 在同一 thread_id 下数据不丢 |
| 至少 3 个长期经验工具可用 | `write_diary`, `read_diary`, `schedule_task` 均通过测试 |
| 三种运行模式全部实现 | `full_silent` / `ap_agency` / `reinforced_agency` 可切换 |
| 总测试数 ≥ 210 | 新增 ~50 个测试 |

---

## 2. 与原始路线图的偏差说明

原始 `docs/CogCore-通用认知内核架构设计.md` §10.3 定义了 M1.1-M1.5，但 M0 阶段已提前交付了其中部分内容。下表是重新校准后的对应关系：

| 原始里程碑 | 原始内容 | M0 已交付 | M1 实际工作 |
|-----------|---------|----------|-----------|
| M1.1 | StateGraph 完整搭建 | ✅ 10 节点 + MemorySaver + StateUpdater | ⏳ PostgresSaver/Store 持久化 |
| M1.2 | LLMBridge 完整实现 | ✅ `build_context_packet` 骨架 + `queue_teacher_feedback` | ⏳ `parse_llm_output` + Ollama 集成 + `teacher_gate` |
| M1.3 | tool_allowlist + skill_run | ❌ | ⏳ ToolRegistry + 安全机制 |
| M1.4 | write_diary / read_diary / schedule_task | ❌ | ⏳ 长期经验工具 |
| M1.5 | 教师反馈延迟合流 | ✅ queue/merge 已在 `action_system.py` 实现 | ⏳ LangGraph 节点内生产化集成 |

重新编号为 M1.1-M1.4，每个里程碑都有明确的交付物和测试目标。

---

## 3. 里程碑总览

```
M1.1 — LLM 桥接 + Ollama 接入    高价值，使 CogCore 可对话
M1.2 — Postgres 持久化            生产基础设施
M1.3 — 工具系统                   能力扩展
M1.4 — PA 双层运行模式            工程完整性
```

### 依赖关系

```
M1.2 (Postgres)  ──→  M1.4 (PA 模式需要 stable 持久化)
      │
      ├── M1.1 (LLM Bridge) ──→ 退出条件 #1 (build_context_packet)
      │         │
      │         └── M1.3 (Tools) ──→ 退出条件 #3 (write_diary/read_diary)
      │
      └── (独立)
```

M1.1 和 M1.2 可并行。M1.3 依赖 M1.1 的 `parse_llm_output`。M1.4 依赖 M1.2 的持久化基础。

---

## 4. M1.1 — LLM 桥接 + Ollama 接入

### 目标

让 CogCore 能通过本地 Ollama 与 LLM 对话：把认知状态翻译为 LLM prompt，把 LLM 回复解析为内源刺激。

### 架构

```
User Input
    │
    ▼
CogCore tick (10 stages)
    │
    ▼
build_context_packet(tick_report) ──→ LLM prompt
    │                                       │
    │                                       ▼
    │                                  Ollama API
    │                                       │
    │                                       ▼
    │                              parse_llm_output(response)
    │                                       │
    ▼                                       ▼
CogCore tick (next)  ←──  StimulusAtoms 注入状态池
```

### 交付物

| 文件 | 改动 | 测试数 |
|------|------|--------|
| `src/cogcore/llm_bridge.py` | 完整实现 4 个接口 | ~8 |
| `src/cogcore/run.py` | 集成 LLM 循环模式 | — |
| `scripts/demo_llm.py` | 端到端 Ollama 对话 demo | — |
| `tests/test_llm_bridge.py` | LLMBridge 单元测试 | ~10 |

### LLMBridge 接口

```python
class LLMBridge:
    def build_context_packet(
        self,
        cogcore_state: CogCoreState,
        max_tokens: int = 4000
    ) -> str:
        """CogCore → LLM：将认知状态翻译为结构化 prompt。

        输出包含：
        - [CURRENT INPUT]: 本轮原始输入
        - [ENERGY STATE]: 状态池能量摘要
        - [NEUROTRANSMITTERS]: NT 各通道值
        - [COGNITIVE FEELINGS]: CFS 活跃信号
        - [ATTENTION FOCUS]: CAM 内容
        - [MEMORY & SOURCES]: HDB 命中结构
        - [ACTION CANDIDATES]: 行动候选与驱动力
        - [PROMPT INSTRUCTIONS]: 行为指令
        """

    def parse_llm_output(
        self,
        llm_response: str,
    ) -> list[StimulusAtom]:
        """LLM → CogCore：将 LLM 回复解析为内源刺激元。

        解析策略：
        - 提取工具调用标记 <tool>name(params)</tool>
        - 提取情绪标记 <feeling>type:intensity</feeling>
        - 剩余文本按词拆分
        """

    def teacher_gate_should_wake(
        self,
        event: dict,
        cogcore_state: CogCoreState,
    ) -> dict:
        """判断是否应主动唤醒（reinforced_agency 模式）。

        返回 WakeDecision: {"should_wake": bool, "reason": str}
        """
```

### 测试要点

- `build_context_packet` 输出包含全部 8 类审计字段（对齐 E13 审计标准）
- `parse_llm_output` 正确提取工具调用和情绪标记
- runtime 不含死循环或死锁（设置 max_turns 上限）
- Ollama 连接失败时优雅降级（不崩溃，返回错误状态）

### 依赖

- Ollama 服务已在本地运行（端口 11434，已验证）
- 模型选择：`qwen3:8b`（本地优先，与现有嵌入服务一致）

---

## 5. M1.2 — Postgres 持久化

### 目标

把 LangGraph 的 `MemorySaver` 替换为 `PostgresSaver`，加入 `Store` 实现跨线程状态共享。

### 交付物

| 文件 | 改动 | 测试数 |
|------|------|--------|
| `docker-compose.yml` | 项目根目录新增 | — |
| `src/cogcore/graph.py` | 加入 PostgresSaver/Store 路径 | ~5 |
| `src/cogcore/store.py` | 新的持久化存储模块 | ~8 |
| `tests/test_persistence.py` | 持久化集成测试 | ~8 |
| `pyproject.toml` | 加 `langgraph-checkpoint-postgres` 依赖 | — |

### 设计要点

```python
# graph.py — 新增生产模式编译路径
def build_cogcore_graph_production(
    modules: dict,
    postgres_uri: str = "postgresql://...",
) -> CompiledStateGraph:
    """使用 PostgresSaver + Store 的生产构图。"""
    checkpointer = PostgresSaver.from_conn_string(postgres_uri)
    store = PostgresStore.from_conn_string(postgres_uri)
    # ... 相同节点定义 ...
    return graph.compile(checkpointer=checkpointer, store=store)

# store.py — 跨线程共享状态
class CogCoreStore:
    """基于 LangGraph Store 的命名空间。
    
    - ("tick", "global") → 全局 tick 计数器
    - ("hdb", thread_id) → 每个线程的 HDB 快照
    - ("config", thread_id) → 每个线程的配置
    """
```

### 测试要点

- invoke 一次后检查 Postgres 中有记录
- 重启进程后在同一 thread_id 下可继续
- `store` 的读写: 写入一个值，读取能取回
- Docker compose 的 `docker compose up -d` 一键启动

---

## 6. M1.3 — 工具系统

### 目标

实现 `ToolRegistry`，把 CogCore 的行动节点（ActionNode）绑定到真实工具函数；注册长期经验工具。

### 交付物

| 文件 | 改动 | 测试数 |
|------|------|--------|
| `src/cogcore/tools.py` | 完整实现 ToolRegistry | ~8 |
| `src/cogcore/tools_diary.py` | write_diary / read_diary | ~5 |
| `src/cogcore/tools_task.py` | schedule_task | ~3 |
| `tests/test_tools.py` | 工具测试 | ~10 |

### 接口设计

```python
class ToolRegistry:
    def register(self, name: str, func: Callable, schema: dict) -> None

    def execute(self, name: str, params: dict) -> ToolResult

    def get_available(self) -> list[ToolDescriptor]

    def is_allowed(self, name: str) -> bool  # tool_allowlist
```

### 长期经验工具（论文 5.7.2）

- **write_diary**: 将当前 tick 的重要事件写入 HDB episodic memory
- **read_diary**: 从 HDB 检索历史情景记忆
- **schedule_task**: 注册一个延迟任务到 HDB 的时间桶

### 测试要点

- 注册工具后 execute 返回正确结果
- tool_allowlist 阻止未注册工具
- write_diary → read_diary 闭环
- schedule_task 到期自动投递

---

## 7. M1.4 — PA 双层运行模式

### 目标

实现三种运行模式（`full_silent` / `ap_agency` / `reinforced_agency`），让 CogCore 能从「被动响应」到「主动建议」到「教师门控」递进。

### 交付物

| 文件 | 改动 | 测试数 |
|------|------|--------|
| `src/cogcore/modes.py` | 新模式选择模块 | ~8 |
| `src/cogcore/pipeline.py` | 加入 mode 分支逻辑 | ~3 |
| `tests/test_modes.py` | 模式测试 | ~8 |

### 模式定义

```python
class AgentMode(str, Enum):
    FULL_SILENT = "full_silent"       # 只在明确触发下响应
    AP_AGENCY = "ap_agency"           # AP 可基于 wake_drive 主动升起候选
    REINFORCED_AGENCY = "reinforced_agency"  # 主动性经过教师门控
```

| 模式 | tick 行为 | 唤醒条件 | 适合阶段 |
|------|----------|---------|---------|
| `full_silent` | 10 阶段全部运行但静默等待外源输入 | 有外源输入 | 默认、验证、低风险 |
| `ap_agency` | 额外计算 wake_drive，高于阈值自动发 tick | tick > 0 且 pool 活跃 | 测试主动后台整理 |
| `reinforced_agency` | wake_drive 还需 teacher_gate 审批 | 外源输入 + 教师同意 | 生产，有审查需求 |

---

## 8. 阶段退出条件检查表

以下条件全部满足后 M1 方可标记完成：

- [ ] M1.1: `build_context_packet` 输出包含 8 类审计字段
- [ ] M1.1: `parse_llm_output` 单次调用成功
- [ ] M1.1: Ollama 对话 demo 可运行
- [ ] M1.2: `docker compose up -d` 一键启动 Postgres
- [ ] M1.2: 进程重启后同一 thread_id 数据不丢失
- [ ] M1.3: ToolRegistry 支持 register/execute/allowlist
- [ ] M1.3: write_diary + read_diary 闭环测试通过
- [ ] M1.4: 三种模式均可切换
- [ ] M1.4: LangGraph Studio 可可视化跟踪一次完整 tick
- [ ] 总测试数 ≥ 210
- [ ] 全量测试通过

---

## 9. 预估工作量

| 里程碑 | 预估测试数 | 核心文件 | 估算 |
|--------|----------|---------|------|
| M1.1 LLM 桥接 | ~18 新增 | `llm_bridge.py`, `run.py` | 最大 |
| M1.2 Postgres | ~13 新增 | `graph.py`, `store.py`, `docker-compose.yml` | 中 |
| M1.3 工具系统 | ~18 新增 | `tools.py`, `tools_diary.py` | 中 |
| M1.4 运行模式 | ~11 新增 | `modes.py` | 小 |
| **总计** | **~60 新增** | **总测试 ~220** | |

---

## 10. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|------|--------|------|------|
| Ollama 本地模型质量不足以驱动 Agent | 中 | M1.1 价值降低 | 先用量化版 qwen3:8b 验证链路，可换 API 模型 |
| Postgres 依赖增加部署复杂度 | 低 | M1.2 需用户自行部署 | 保留 MemorySaver 作为轻量回退路径 |
| LangGraph 版本更新导致 API 不兼容 | 低 | 高 | `pyproject.toml` 锁定版本，升级前跑全量测试 |
| Windows 下 Docker 不可用 | 中 | M1.2 阻塞 | 提供 SQLite 作为 Windows 回退持久化方案 |
| 工具系统 scope 蔓延 | 中 | 延误 | M1.3 只做 3 个核心工具，其余放 M2 |

---

*CogCore M1 规划 v0.1 | 2026-06-05 | 基于 M0 阶段全部完成的状态重新校准*
