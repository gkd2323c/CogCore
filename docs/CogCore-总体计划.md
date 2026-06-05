# CogCore 总体计划 — 从认知内核到生产智能体

> **本文档** 综合了 `AGENT_BUILD.MD` 的 11 层能力栈、`CogCore-验证矩阵.md` 的 25 项实验、`AGENT_BUILD.MD` §8 的业务场景，把 CogCore 从当前状态推进到"真正能跑生产"的完整路径。

---

## 0. 当前位置

```
2026-06-05 现状
├── 阶段 A（图引擎）：✅ 完成
├── 阶段 B（LLM 解释）：✅ 完成（单 LLM，DeepSeek 远程）
├── 阶段 C（工具与记忆）：✅ 完成（HDB + SQLite + 6 工具）
├── 阶段 D（部署与可观测）：⚠️ 部分（CogCoreService 后台）
├── 实验 E01-E17（核心）：✅ 通过
├── 实验 E18-E20（M2.3）：✅ 通过
├── 真实对话验证：✅ Alice 跨 session 记住 + 日记落盘
└── 262 tests 全过
```

**已覆盖**：`L2`（图引擎）+ `L3`（认知层）+ `L4`（单 LLM 解释）+ `L5`（基础工具）+ `L7`（SQLite 持久化）+ `L11`（基础测试）

**未覆盖**：`L1`（应用层）+ `L4`（多 LLM registry + fallback）+ `L5`（MCP 接入）+ `L6`（语义层）+ `L7`（Postgres 升级）+ `L8`（可观测性）+ `L9`（部署基础设施）+ `L10`（错误处理层）+ `L11`（evals/）

---

## 1. 完整智能体能力栈（来自 AGENT_BUILD.MD §3）

```
┌──────────────────────────────────────────────────────────────┐
│                       完整智能体能力栈                          │
│                                                              │
│  L1  应用层    ─── FastAPI / WebSocket / Studio     ❌ 未开始  │
│  L2  图引擎    ─── LangGraph StateGraph            ✅ 完成    │
│  L3  认知层    ─── CogCore 9 模块 + 25 实验        ✅ 17/25   │
│  L4  解释层    ─── LLMRegistry + circular fallback ⚠️ 单 LLM │
│  L5  工具层    ─── LangChain Tools + MCP           ⚠️ 6 工具 │
│  L6  记忆层    ─── HDB + pgvector + mem0           ⚠️ HDB only│
│  L7  持久化    ─── PostgresSaver + Store + Alembic  ⚠️ SQLite│
│  L8  可观测性  ─── Langfuse / LangSmith + Prom     ❌ 未开始  │
│  L9  部署层    ─── Docker + Compose + JWT + slowapi ❌ 未开始 │
│  L10 错误处理  ─── RetryPolicy + fallback + 教师门控 ⚠️ 内部有│
│  L11 测试      ─── evals/ + unit + integration     ⚠️ 262 unit│
└──────────────────────────────────────────────────────────────┘
                                                  ★ = 强项
                                                  ⚠ = 部分
                                                  ❌ = 缺
```

---

## 2. 三阶段路线（M3 → M5）

### 阶段总览

| 阶段 | 主题 | 11 层覆盖目标 | 时间估计 | 实验 |
|------|------|--------------|---------|------|
| **M3** | 智能体能力补全 | L1 + L4(多LLM) + L5(MCP) + L10 | 1 周 | E21-E22 |
| **M4** | 持久化与可观测 | L6 + L7(升级) + L8 + L11(evals) | 1 周 | E23 |
| **M5** | 部署与多场景 | L1(完善) + L9 + 5 业务场景 | 1-2 周 | E24-E25 |

---

### 阶段 M3 — 智能体能力补全（目标：让 Agent 真能干活）

**L 层覆盖**：`L1`（基础 FastAPI）+ `L4`（多 LLM）+ `L5`（MCP 接入）+ `L10`（错误处理）

#### M3.1 — FastAPI 接入（`L1`）

**目标**：把 CogCore 暴露成 HTTP/WebSocket 服务，可被任何客户端调用。

**交付**：
- `app/main.py`：FastAPI 应用入口
- `app/api/v1/chat.py`：`POST /v1/chat` 端点（接收 message + thread_id，返回 response）
- `app/api/v1/ws.py`：`/v1/ws/{thread_id}` WebSocket 端点（流式）
- `app/api/v1/status.py`：`GET /v1/status` 服务状态
- `app/api/v1/diary.py`：`GET/POST /v1/diary` 日记读写
- `app/deps.py`：依赖注入（service / bridge / registry 单例）

**参考**：[wassim249/fastapi-langgraph-agent-production-ready-template](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) `app/api/` 结构

**测试**：
- `tests/test_api_chat.py`：HTTP 端点对话流
- `tests/test_api_ws.py`：WebSocket 双向流
- `tests/test_api_status.py`：状态查询

**退出条件**：5 个端点 + 集成测试，curl 跑通对话

---

#### M3.2 — LLMRegistry + circular fallback（`L4` 升级）

**目标**：多 LLM 轮转，单个失败自动切下一个。

**交付**：
- `src/cogcore/llm_registry.py`：
  - `LLMRegistry`：管理多个 `LLMBridge` 实例
  - `LLMService`：调用入口，按顺序尝试
  - `circular fallback`：第一失败 → 第二 → ... → 第一（健康）
- `config.toml` 多 LLM 段：
  ```toml
  [[llm.providers]]
  name = "deepseek"
  endpoint = "https://api.deepseek.com/v1"
  model = "deepseek-chat"
  priority = 1

  [[llm.providers]]
  name = "ollama"
  endpoint = "http://127.0.0.1:11434/v1"
  model = "qwen3.5:latest"
  priority = 2
  ```
- `scripts/test_llm_fallback.py`：故障注入（mock 一家挂掉）

**参考**：wassim249 `app/services/llm/`

**测试**：
- `tests/test_llm_registry.py`：注册、轮转、回退
- `tests/test_circular_fallback.py`：3 个 provider 中 1 个挂掉，能切换

**退出条件**：3 个 mock LLM 轮转，1 个永久失败后继续用剩下的

---

#### M3.3 — MCP 工具接入（`L5` 升级）

**目标**：CogCore Agent 能加载并调用 MCP server 的工具。

**交付**：
- `src/cogcore/mcp_adapter.py`：
  - `MCPAdapter`：连接 MCP server，列出工具，注册到 ToolRegistry
  - `mcp://` 协议支持
- `scripts/test_mcp_integration.py`：接 Brave Search / Firecrawl MCP server
- 配置：`config.toml` 加 `[mcp] servers = ["brave", "firecrawl"]`

**参考**：[wassim249](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template) MCP 部分 + [langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) `src/react_agent/tools.py`

**测试**：
- `tests/test_mcp_adapter.py`：mock MCP server 协议
- 集成测试：接 Firecrawl MCP，搜 "CogCore"

**退出条件**：ToolRegistry 中能列出 MCP 工具 + Agent 实际调用

---

#### M3.4 — 错误处理层（`L10` 补全）

**目标**：节点级重试 + 模型级 fallback + 系统级教师门控三层联动。

**交付**：
- `src/cogcore/retry.py`：`with_retry(node_fn, max_attempts=3, backoff=tenacity)` 包装器
- `graph.py` 中所有 stage 节点默认包 retry
- 文档：M3.4-RFC.md 三层错误处理设计

**参考**：wassim249 RetryPolicy + LLMRegistry circular fallback

**测试**：
- `tests/test_retry.py`：节点失败 → 重试 3 次 → 放弃
- 集成测试：LLM 调用超时 → fallback 到第二个 provider

**退出条件**：3 层错误处理有完整测试覆盖

---

#### M3.5 — 实验 E21-E22

- **E21** 奖惩反事实课程：构造 5 条不同奖励曲线的轨迹，对比 NT 演化路径
- **E22** 时间延迟压力测试：10/50/100 tick 延迟任务的回投准确率

**退出条件**：E21/E22 通过验证矩阵四项准入

---

### 阶段 M4 — 持久化与可观测（目标：让 Agent 真能观测）

**L 层覆盖**：`L6`（语义层）+ `L7`（Postgres 升级）+ `L8`（可观测性）+ `L11`（evals/）

#### M4.1 — pgvector 语义层（`L6`）

**目标**：HDB（结构）之外增加 pgvector（语义）双轨记忆。

**交付**：
- `src/cogcore/embeddings.py`：
  - `EmbeddingProvider`：抽象接口
  - `OllamaEmbeddingProvider`：调 `qwen3-embedding:0.6b`（本地）
  - `OpenAIEmbeddingProvider`：调 OpenAI text-embedding-3
- `src/cogcore/semantic_store.py`：
  - `SemanticStore`：存向量，按相似度查询
  - 与 HDB 协作：HDB 命中走查存，miss 走相似度
- `config.toml`：选 embedding provider

**参考**：wassim249 `mem0` + pgvector 模式

**测试**：
- `tests/test_embeddings.py`：本地 Ollama 嵌入
- `tests/test_semantic_store.py`：存 + 查 + 相似度排序

**退出条件**：HDB miss 时能 fallback 到语义查询

---

#### M4.2 — Postgres 升级（`L7` 升级）

**目标**：SQLite（开发）→ Postgres（生产）。

**交付**：
- `src/cogcore/graph.py`：
  - `build_cogcore_graph_postgres()`：用 `PostgresSaver` + `PostgresStore`
  - 自动迁移到 `alembic/`
- `alembic/` 配置 + 首次 migration
- `docker-compose.yml` 起本地 Postgres

**测试**：
- `tests/test_persistence_postgres.py`：Postgres 路径
- 集成测试：起 Docker Postgres → 跑 100 tick → 重启 → 状态恢复

**退出条件**：Alice 重启 Postgres 还能被记住

---

#### M4.3 — Langfuse 可观测（`L8`）

**目标**：每节点/每 LLM 调用的 trace + 指标 + 审计。

**交付**：
- `src/cogcore/observatory.py`：
  - `LangfuseTracer`：包装每节点 trace
  - `PrometheusExporter`：暴露 `cogcore_ticks_total`、`cogcore_nt_arousal` 等 metric
  - `CogCoreAuditTrail`：每 tick 10 阶段快照 + SHA-256（论文 5.6.1）
- `grafana/dashboards/cogcore.json`：预置 dashboard
- `prometheus/prometheus.yml`：scrape 配置

**参考**：wassim249 Langfuse + Prom + Grafana 全栈

**测试**：
- `tests/test_observatory.py`：trace 写入
- 集成测试：跑 50 tick → 查 Prom metric → 查 Langfuse UI

**退出条件**：可观测 dashboard 真的能看到指标

---

#### M4.4 — evals/ 评测模块（`L11` 升级）

**目标**：用 LangSmith Evals 模式写"机制级"评测。

**交付**：
- `evals/` 目录：
  - `evals/E21_reward_curve/eval.py`：不同奖励曲线 → NT 演化路径评估
  - `evals/E22_delayed_reentry/eval.py`：延迟回投准确率评估
  - `evals/agent_quality/eval.py`：对话质量人工 + LLM-as-judge
- `pyproject.toml`：`pytest --evals` 入口

**测试**：跑 evals/ 套件，输出 JSON 报告

**退出条件**：evals/ 套件能 1 键跑 + 输出可对比报告

---

#### M4.5 — 实验 E23

- **E23** 词级/字符级/向量混合：3 种粒度的感受器并存

**退出条件**：E23 通过四项准入

---

### 阶段 M5 — 部署与多场景（目标：让 Agent 真能用）

**L 层覆盖**：`L1`（完善）+ `L9`（部署）+ 5 个业务场景

#### M5.1 — Docker 化（`L9`）

**目标**：完整可分发的 Docker 镜像 + Compose。

**交付**：
- `Dockerfile`：Python 3.14-slim 基础 + CogCore 依赖
- `docker-compose.yml`：Postgres + Ollama + CogCore
- `nginx/` 反向代理配置
- `.dockerignore`

**参考**：wassim249 `Dockerfile` + `docker-compose.yml`

**测试**：`docker-compose up` → 外部 curl 通对话

---

#### M5.2 — JWT + slowapi（`L9` 补全）

**目标**：基础生产安全。

**交付**：
- `app/auth/jwt.py`：JWT 签发/校验
- `app/middleware/rate_limit.py`：slowapi 速率限制
- `app/middleware/logging.py`：结构化请求日志

---

#### M5.3 — 5 个业务场景（来自 AGENT_BUILD.MD §8）

| # | 场景 | hereandnowai 项目 | CogCore 实现 |
|---|------|-------------------|------------|
| 1 | 基础对话 | project-01 | ✅ 已有（real_chat.py） |
| 2 | 工具调用 | project-02 | ✅ 已有（6 工具） |
| 3 | **人工干预** | project-03 | ❌ 加 `interrupt_before` + 教师门控 |
| 4 | **多 Agent 协作** | project-05 | ❌ 多 CogCore 实例 + Store 共享 |
| 5 | **长期陪伴** | project-11/12 | ⚠️ 加定时任务 + mem0 长期事实 |

每个场景对应 `experiments/scenarios/S0X/`。

---

#### M5.4 — 实验 E24-E25

- **E24** 多模态感受器：图像/音频/工具状态统一入池
- **E25** 叙事质量盲评：人工评价候选链连贯性

---

## 3. 优先级与依赖

```
M3 ───┐
      ├─ M4 ── M5
      │
依赖：M3.1 (FastAPI) → M3.2 (多LLM) → M3.3 (MCP)
     M3.4 (错误处理) 横向贯穿

M4.1 (嵌入) ──┐
M4.2 (Postgres) ──→ M4.3 (可观测) ──→ M4.4 (evals)
M4.5 (E23) 跟随

M5.1 (Docker) ──┐
M5.2 (JWT) ──────→ M5.3 (5 业务场景) ──→ M5.4 (E24-E25)
```

**关键路径**：M3.1 FastAPI → M3.2 多 LLM → M4.2 Postgres → M4.3 可观测 → M5.1 Docker

---

## 4. 与 AGENT_BUILD.MD §6 阶段 D 的对照

| AGENT_BUILD.MD §6 D 阶段目标 | 落地到本计划 |
|-----------------------------|------------|
| FastAPI chatbot endpoint | M3.1 |
| JWT + slowapi | M5.2 |
| Alembic migration | M4.2 |
| Grafana dashboards | M4.3 |
| Prometheus 配置 | M4.3 |
| Dockerfile + compose | M5.1 |
| evals/ 套件 | M4.4 |

阶段 D 全部分散到 M3-M5 各任务里。

---

## 5. 风险与开放问题

### 5.1 L6 语义层风险
- **依赖**：本机有 Ollama（已确认运行）或愿意调用 OpenAI Embeddings
- **未决**：pgvector 部署复杂度，可先用本地 SQLite + numpy 顶替

### 5.2 M5.3 多 Agent 协作
- **依赖**：LangGraph Store 跨实例共享
- **未决**：协作协议是 A2A 还是 A2A-lite

### 5.3 M4.2 Postgres 迁移
- **依赖**：用户机器有 Docker 或愿意装 Postgres
- **退路**：保留 SQLite 作为 fallback

---

## 6. 退出准则（每阶段）

| 阶段 | 硬指标 |
|------|-------|
| **M3** | 5 个 API 端点 + 3+ LLM provider 轮转 + 至少 1 个 MCP server 集成 + 错误处理三层全测 + E21/E22 通过 + 300+ tests |
| **M4** | HDB+pgvector 双轨工作 + Postgres 状态恢复 + Langfuse trace + evals/ 1 键跑 + E23 通过 + 340+ tests |
| **M5** | docker-compose up 启动 + JWT 鉴权 + 5 业务场景至少 4 个能跑 + E24-E25 通过 + 400+ tests |

---

## 7. 文档同步

每个阶段结束时同步更新：

- `README.md` 状态表 / 测试数 / 阶段标签
- `AGENTS.md` 段落
- `docs/CogCore-验证矩阵.md` 实验状态列
- `docs/CogCore-通用认知内核架构设计.md` §10.4 阶段表
- `docs/CogCore-通用认知内核架构设计.md` §3 11 层状态标记

---

*最后更新：2026-06-05（M3-M5 路线规划）*
