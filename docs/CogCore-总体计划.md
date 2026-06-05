# CogCore 总体计划 — 从认知内核到生产智能体

> **本文档** 综合了 `AGENT_BUILD.MD` 的 11 层能力栈、`CogCore-验证矩阵.md` 的 25 项实验、`AGENT_BUILD.MD` §8 的业务场景，把 CogCore 从当前状态推进到"真正能跑生产"的完整路径。

---

## 0. 设计原则：零 Docker / 零外部服务

**目标用户** 是个人开发者 + 研究者。环境假设 = Python 3.11+ + (可选) 本地 Ollama。
部署假设 = `pip install cogcore` → `python -m cogcore serve` → 完事。

```
数据位置：~/.cogcore/
  cogcore.db       # SQLite 状态
  diary.db         # 日记
  traces/          # JSON 审计日志
  config.toml      # 配置
依赖项：LangGraph + OpenAI SDK + SQLite + Pydantic
外部服务：可选远程 LLM（DeepSeek/OpenAI），可选本地 Ollama
```

**M3-M5 所有设计改动** 都不引入 Docker / Postgres / Prometheus / Grafana。需要更强能力的场景（如多机部署、cluster 调度）属于 M5 之后的扩展，不在当前目标用户范围。

---

## 0.5 当前位置

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

**未覆盖**：`L1`（应用层）+ `L4`（多 LLM registry + fallback）+ `L5`（MCP 接入）+ `L6`（嵌入/语义层）+ `L8`（可观测性）+ `L9`（部署基础设施）+ `L10`（错误处理层）+ `L11`（evals/）

**设计不变量**：
- **不引入 Docker**——所有组件 Python 进程内 / SQLite 文件
- **不引入 Postgres**——SQLite 覆盖 99% 场景
- **不引入 Langfuse / Prom / Grafana**——自写 JSON trace + sqlite-stats 即可
- **不引入 docker-compose**——`python -m cogcore serve` 一个进程起步

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
│  L6  记忆层    ─── HDB + sqlite-vec / 嵌入       ⚠️ HDB only│
│  L7  持久化    ─── SQLite + langgraph-checkpoint   ✅ SQLite  │
│  L8  可观测性  ─── JSON trace + sqlite-stats       ❌ 未开始  │
│  L9  部署层    ─── `python -m cogcore serve`       ❌ 未开始  │
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

**L 层覆盖**：`L6`（语义层）+ `L8`（可观测性）+ `L11`（evals/）

#### M4.1 — 嵌入语义层（`L6`）

**目标**：HDB（结构）之外增加嵌入（语义）双轨记忆。**不引入 pgvector，用 sqlite-vec / numpy**。

**交付**：
- `src/cogcore/embeddings.py`：
  - `EmbeddingProvider`：抽象接口
  - `OllamaEmbeddingProvider`：调 `qwen3-embedding:0.6b`（本地，无需 Docker）
  - `OpenAIEmbeddingProvider`：调 OpenAI text-embedding-3
- `src/cogcore/semantic_store.py`：
  - `SemanticStore`：默认用 numpy + SQLite（向量列存 BLOB）
  - 可选 `sqlite-vec` 扩展（如果装了）
  - 与 HDB 协作：HDB 命中走查存，miss 走相似度
- `config.toml`：选 embedding provider

**参考**：wassim249 `mem0` + pgvector 模式（仅作语义层设计参考，部署方案不同）

**测试**：
- `tests/test_embeddings.py`：本地 Ollama 嵌入
- `tests/test_semantic_store.py`：存 + 查 + 相似度排序

**退出条件**：HDB miss 时能 fallback 到语义查询

---

#### M4.2 — SQLite 增强（`L7` 优化）

**目标**：SQLite 保持不动，**为高频访问路径加索引 + 备份 + 容量预警**。

**交付**：
- `src/cogcore/db_maintenance.py`：
  - `vacuum()`：定期压缩
  - `prune_old_checkpoints(N)`：只保留最近 N 个 LangGraph checkpoint（防止 state.db 无限增长）
  - `auto_backup_to(dir)`：可选手动备份
- `scripts/db_health.py`：状态报告 + 容量预警
- `config.toml`：`[persistence] max_checkpoints=100, auto_vacuum_interval=1000`

**测试**：
- `tests/test_db_maintenance.py`：vacuum、prune、容量预警

**退出条件**：state.db 不会无限增长；OOM 前能发出警告

---

#### M4.3 — JSON trace + sqlite-stats（`L8`）

**目标**：每节点/每 LLM 调用的 trace + 统计。**不引入 Langfuse / Prom / Grafana**。

**交付**：
- `src/cogcore/observatory.py`：
  - `JSONTracer`：每节点输出 `{ts, tick, node, duration_ms, status}` 到 `traces/YYYY-MM-DD.jsonl`
  - `SQLiteStats`：写入 `cogcore.db` 的 `stats` 表（counter / gauge / histogram）
  - `CogCoreAuditTrail`：每 tick 10 阶段快照 + SHA-256（论文 5.6.1）
- `scripts/stats_report.py`：从 sqlite-stats 输出 Markdown 报告
- `scripts/trace_viewer.py`：简易 HTML 渲染 JSONL trace（零依赖）

**测试**：
- `tests/test_observatory.py`：trace 写入、stats 累积
- 集成测试：跑 50 tick → 查 stats 表 → 查 trace JSONL

**退出条件**：`python -m cogcore.stats` 一条命令出报告

---

#### M4.4 — evals/ 评测模块（`L11` 升级）

**目标**：用「任务级 + 机制级」评测协议。**不引入 LangSmith Evals（云端依赖）**。

**交付**：
- `evals/` 目录：
  - `evals/E21_reward_curve/eval.py`：不同奖励曲线 → NT 演化路径评估
  - `evals/E22_delayed_reentry/eval.py`：延迟回投准确率评估
  - `evals/agent_quality/eval.py`：对话质量 LLM-as-judge（用本地 Ollama 当 judge）
- `pyproject.toml`：`pytest --evals` 入口
- 报告输出：`evals/reports/E21-2026-06-05.json`

**测试**：跑 evals/ 套件，输出 JSON 报告

**退出条件**：evals/ 套件能 1 键跑 + 输出可对比报告

---

#### M4.5 — 实验 E23

- **E23** 词级/字符级/向量混合：3 种粒度的感受器并存

**退出条件**：E23 通过四项准入

---

### 阶段 M5 — 部署与多场景（目标：让 Agent 真能用）

**L 层覆盖**：`L1`（完善）+ `L9`（部署）+ 5 个业务场景

#### M5.1 — 单进程部署（`L9`）

**目标**：`python -m cogcore serve` 一个进程起步。**不引入 Docker / Compose**。

**交付**：
- `src/cogcore/serve.py`：
  - `python -m cogcore serve --port 8000`：起 FastAPI
  - `--workers N`：多进程（可选，默认 1）
  - `--reload`：开发热重载
  - `--data-dir ~/.cogcore`：数据目录
- `pyproject.toml`：`[project.scripts] cogcore = "cogcore.cli:main"`
- `scripts/install-service.sh` / `install-service.ps1`：systemd / NSSM / Windows 服务注册（可选）
- 文档：单用户 README 启动指南

**部署矩阵**：

| 场景 | 命令 |
|------|------|
| 个人开发 | `python -m cogcore serve` |
| 24/7 后台 | `nohup python -m cogcore serve &` / Task Scheduler |
| 局域网多用户 | `--host 0.0.0.0 --port 8000` |
| 公网部署 | 反向代理加 nginx + HTTPS（自己选、文档给出模板） |

**参考**：wassim249 `Dockerfile` 思路——但用 Python 进程替代容器

**测试**：`python -m cogcore serve &` → 外部 curl 通对话 → kill

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
M4.2 (SQLite 增强) ──→ M4.3 (JSON trace) ──→ M4.4 (evals)
M4.5 (E23) 跟随

M5.1 (单进程部署) ──┐
M5.2 (JWT) ──────→ M5.3 (5 业务场景) ──→ M5.4 (E24-E25)
```

**关键路径**：M3.1 FastAPI → M3.2 多 LLM → M4.1 嵌入 → M4.3 JSON trace → M5.1 `python -m cogcore serve`

**不依赖路径**（如果环境受限可以跳过）：
- M3.3 MCP（需要 MCP server 运行环境）
- M4.1 嵌入（如果用 HDB-only 也能跑）
- M5.3 业务场景 4-5（可选）

---

## 4. 与 AGENT_BUILD.MD §6 阶段 D 的对照

| AGENT_BUILD.MD §6 D 阶段目标 | 落地到本计划 |
|-----------------------------|------------|
| FastAPI chatbot endpoint | M3.1 |
| JWT + slowapi | M5.2 |
| Alembic migration | M4.2 |
| Langfuse + Prom + Grafana | **不采用**——自写 JSON trace + sqlite-stats |
| Prometheus 配置 | M4.3 |
| Docker / Compose | **不采用**——`python -m cogcore serve` |
| evals/ 套件 | M4.4 |

阶段 D 全部分散到 M3-M5 各任务里。

---

## 5. 风险与开放问题

### 5.1 L6 语义层风险
- **依赖**：本机有 Ollama（已确认运行）或愿意调用 OpenAI Embeddings
- **未决**：用 numpy 存储向量还是 sqlite-vec 扩展
- **退路**：HDB-only 也能跑，语义层为可选增强

### 5.2 M5.3 多 Agent 协作
- **依赖**：LangGraph Store 跨实例共享
- **未决**：协作协议是 A2A 还是 A2A-lite
- **退路**：先做单 Agent 多个 CogCore 实例在同一进程（多角色）

### 5.3 M5 高级特性
- **不依赖**：M5.1、M5.2、M5.3 中的 4-5 业务场景、M5.4 都不是阻塞主线的——可以选做
- **必做**：M5.1 单进程部署是最后一道交付门槛

---

## 6. 退出准则（每阶段）

| 阶段 | 硬指标 |
|------|-------|
| **M3** | 5 个 API 端点 + 3+ LLM provider 轮转 + 至少 1 个 MCP server 集成 + 错误处理三层全测 + E21/E22 通过 + 300+ tests |
| **M4** | HDB+嵌入双轨工作 + SQLite 增强（容量可控） + JSON trace + sqlite-stats + evals/ 1 键跑 + E23 通过 + 340+ tests |
| **M5** | `python -m cogcore serve` 启动 + JWT 鉴权 + 5 业务场景至少 4 个能跑 + E24-E25 通过 + 400+ tests |

**所有阶段都零 Docker / 零外部服务**（除可选的远程 LLM 端点）。

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
