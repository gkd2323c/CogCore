# CogCore 总体计划 — 从认知内核到自迭代智能体

> **本文档** 综合了 `AGENT_BUILD.MD` 的 11 层能力栈、`CogCore-验证矩阵.md` 的 25 项实验、`AGENT_BUILD.MD` §8 的业务场景，把 CogCore 从当前状态推进到"真正能跑生产、且能自我迭代"的完整路径。

---

## 0. 北星目标：自迭代 (Self-Iteration)

**CogCore 的根本目的**不是做一个更聪明的 LLM Agent——LLM 已经够聪明。
是做一个**能读懂自己源码、识别自己的能力缺口、修改自己代码、验证修改、在生产环境热部署、失败时回滚**的认知体。

这跟 CogCore 现有架构的多个已落地设计一脉相承：

| CogCore 现有资产 | 自迭代中的角色 |
|--------------|------------|
| **AdaptiveTuner**（论文 5.5.3）| L0 调参已闭环：Agent 已能调自己的注意预算 / 行动阈值 |
| **ActionSystem + teacher feedback**（论文 5.4.3）| L1 经验沉淀：教师反馈合并机制是可学习的 |
| **LongTermExperienceTools**（write_diary / schedule_task）| 长期记忆可被自迭代用：写"今天发现什么 gap" |
| **17 项实验 + 262 tests** | L11 评测：自迭代需要"测什么过 / 什么不过"的明确判据 |
| **本地优先 + 零外部服务** | 自迭代不依赖云端构建 / 云端 LLM-judge，可在本地闭环跑 |

**自迭代的明确含义**（四层）：

| 层 | 能力 | 示例 |
|---|------|------|
| **L12.1 自检** | 读自己源码、跑自己测试、查 git 历史 | Agent 看到某个 bug → `git log -- <file>` 找到引入 commit |
| **L12.2 自改** | 写补丁、跑测试、git commit | Agent 写 fix → 跑 pytest → commit |
| **L12.3 自部署** | 热重载模块、回滚失败改动 | 修改后 hot-reload → 运行 30 tick 监控 → 失败自动 git revert |
| **L12.4 自学** | 跟踪哪些自改成功、纳入长期记忆 | 写入 diary "哪类改动成功率高" + 在 HDB 中固化为结构记忆 |

**这不是"Agent 写代码给人审"——是 Agent 自己写、自己测、自己部署、自己监控**。人是 supervisor，不是 bottleneck。

### 0.1 自迭代的安全约束（必须配套设计）

自迭代是双刃剑。安全约束跟能力同样重要：

1. **测试闸门**：所有自改必须先过现有测试套件
2. **版本回滚**：每次自改先 git commit，失败立即 revert
3. **变更沙箱**：agent 改的是自己的 `src/cogcore/`，不是 system Python
4. **影响范围限速**：自改前评估 blast radius（影响多少 stage / module / 测试）
5. **可解释性**：所有自改 commit message 必须包含"为什么改"，不能只改不解释
6. **A/B 对照**：关键参数修改采用 dual-run（新旧并存 30 tick），差异显著才落定
7. **人工否决通道**：所有自改推 PR 而非直接 merge（可选，激进模式可自动 merge）

### 0.2 自迭代与 11 层栈的关系

L12 不是单独的"第 12 层"——它是**横切所有 11 层的元能力**：

```
L12 自迭代层 (横切)
  ├── 需要 L0-L1 读自己状态 (L8 观测 + L11 评测)
  ├── 需要 L4 推理 "怎么修" (LLM 规划)
  ├── 需要 L5 工具操作代码 (L12.1-L12.3 工具集)
  ├── 需要 L6 长期记忆 (HDB + 嵌入 + 日记)
  ├── 需要 L7 持久化 (checkpoint 不会因 reload 丢)
  ├── 需要 L8 可观测 (改前快照 + 改后 diff 指标)
  ├── 需要 L9 部署 (hot-reload + 回滚)
  ├── 需要 L10 错误处理 (自改失败也是错误)
  └── 需要 L11 评测 (改动过没过)
```

**结论**：M3-M5 的所有里程碑都应该**问同一个问题**——"这个能力是否支持自迭代？" 不支持的就要补。

---

## 0.5 设计原则：零 Docker / 零外部服务

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
│  L6  记忆层    ─── HDB + numpy 嵌入 (BLOB)        ⚠️ HDB only │
│  L7  持久化    ─── SQLite + langgraph-checkpoint   ✅ SQLite  │
│  L8  可观测性  ─── JSON trace + sqlite-stats       ❌ 未开始  │
│  L9  部署层    ─── `python -m cogcore serve`       ❌ 未开始  │
│  L10 错误处理  ─── RetryPolicy + fallback + 教师门控 ✅ 完成  │
│  L11 测试      ─── evals/ + unit + integration     ⚠️ 400 unit│
│  L12 自迭代    ─── 自检/自改/自部署/自学 + 安全约束  ✅ L12.1-L12.3│
└──────────────────────────────────────────────────────────────┘
                                                  ★ = 强项
                                                  ⚠ = 部分
                                                  ❌ = 缺
```

---

## 2. 三阶段路线（M3 → M5）

### 阶段总览

| 阶段     | 主题                    | 11 层覆盖目标                                        | 时间估计  | 实验      |
| ------ | --------------------- | ----------------------------------------------- | ----- | ------- |
| **M3** | 智能体能力 + **L12 自迭代起步** | L1 + L4(多LLM) + L5(MCP) + L10 + **L12.1-L12.2** | 1 周   | E21-E22 |
| **M4** | 持久化与可观测 + **自迭代闭环**   | L6 + **L7(优化)** + L8(trace+stats) + L11(evals) + **L12.4** | 1 周   | E23     |
| **M5** | 部署与多场景 + **自迭代应用于业务** | L1(完善) + L9 + 5 业务场景 + **L12 生产验证**             | 1-2 周 | E24-E25 |

---

### 阶段 M3 — 智能体能力补全（目标：让 Agent 真能干活）

**详细规划已拆分** → [CogCore-M3-规划.md](./CogCore-M3-规划.md)
**L 层覆盖**：`L1`（基础 FastAPI）+ `L4`（多 LLM）+ `L5`（MCP 接入）+ `L10`（错误处理）+ `L12.1`/`L12.2`（代码自检/自改）

**M3 进度** (2026-06-06 实际状态):
- M3.1 FastAPI 接入           ✅ 5 端点 + 13 测试
- M3.2 LLMRegistry + fallback  ✅ 14 测试 + 实跑
- M3.3 MCP 工具接入            ✅ 15 测试 + DeepSeek 端到端
- M3.4 错误处理三层            ✅ L1 retry + L2 fallback + L3 gate, 20 测试
- M3.5 代码感知工具集           ✅ 6 code + 5 git + 2 exec + 闸门, 50 测试
- M3.6 自迭代元循环             ✅ 9 步流程 + 5 重安全闸门 + CLI 入口, 16 测试
- M3.7 实验 E21-E22            ✅ E21 奖惩反事实 + E22 自迭代 A/B, 10 测试

> 各子阶段详细交付 / 测试 / 退出准则 参见 [CogCore-M3-规划.md](./CogCore-M3-规划.md)。

---

### 阶段 M4 — 持久化与可观测（目标：让 Agent 真能观测 + 真能自评）

**详细规划已拆分** → [CogCore-M4-规划.md](./CogCore-M4-规划.md)

**L 层覆盖**：`L6`（语义层）+ `L7`（持久化优化）+ `L8`（可观测性）+ `L11`（evals/）

**核心原则**：不引入 Docker / Postgres / Langfuse / Prom / Grafana。`pip install cogcore` → `python -m cogcore serve` 单进程全跑。

**依赖顺序**：

```
M4.2 (SQLite 维护)  ──┐
M4.3a (JSON trace)   ──┼──→ M4.4 (evals + A/B 度量) ──→ M4.5 (E23) ──→ M4.6 (M3.6 集成)
M4.3b (sqlite-stats) ──┘
M4.1 (嵌入) ──────────────────────────────────────────────→ M4.5 (E23)
```

| 子阶段 | L 层 | 阻塞主路径？ | 核心交付 |
|--------|------|------------|----------|
| **M4.2** SQLite 增强 | L7 | 是 (state.db 20MB 无上限) | vacuum / prune_checkpoints(N) / auto_backup / 容量预警 |
| **M4.3a** JSON trace | L8 | 是 (M3.6 元循环需要看"上次改了什么") | `traces/YYYY-MM-DD.jsonl`, 每节点 `{ts,tick,node,duration_ms,status}`, 零依赖 viewer |
| **M4.3b** sqlite-stats | L8 | 是 (度量基础) | counter / gauge / histogram 三种 primitive |
| **M4.4** evals/ | L11 | 是 ("自改是否更好了"的判据) | `evals/<name>/eval.py` 协议 + A/B harness (baseline vs candidate) |
| **M4.1** 嵌入语义层 | L6 | 否 (HDB-only 也能跑) | Ollama (qwen3-embedding:0.6b) / OpenAI / numpy + SQLite BLOB |
| **M4.5** E23 | 实验 | 否 (依赖 M4.1) | 词级/字符级/向量混合感受器 |
| **M4.6** M3.6 集成 | L12.4 | 是 (自迭代闭环) | 把 M4.3 trace + M4.4 evals 喂给 M3.6 元循环, 失败自动 revert |

**M4 进度** (2026-06-06 实际状态):
- M4.2 SQLite 增强           ✅ vacuum / prune / backup / health, 19 测试 (state.db 20MB -> 5.83MB)
- M4.3a JSON trace           ✅ 22 测试, 零依赖 viewer
- M4.3b sqlite-stats         ⏳
- M4.4 evals/ 协议            ⏳
- M4.1 嵌入语义层             ⏳
- M4.5 实验 E23              ⏳
- M4.6 M3.6 集成闭环         ⏳

> 各子阶段详细交付 / 测试 / 退出准则 参见 [CogCore-M4-规划.md](./CogCore-M4-规划.md)。

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

| 场景      | 命令                                                 |
| ------- | -------------------------------------------------- |
| 个人开发    | `python -m cogcore serve`                          |
| 24/7 后台 | `nohup python -m cogcore serve &` / Task Scheduler |
| 局域网多用户  | `--host 0.0.0.0 --port 8000`                       |
| 公网部署    | 反向代理加 nginx + HTTPS（自己选、文档给出模板）                    |

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

| #   | 场景             | hereandnowai 项目 | CogCore 实现                    |
| --- | -------------- | --------------- | ----------------------------- |
| 1   | 基础对话           | project-01      | ✅ 已有（real_chat.py）            |
| 2   | 工具调用           | project-02      | ✅ 已有（6 工具）                    |
| 3   | **人工干预**       | project-03      | ❌ 加 `interrupt_before` + 教师门控 |
| 4   | **多 Agent 协作** | project-05      | ❌ 多 CogCore 实例 + Store 共享     |
| 5   | **长期陪伴**       | project-11/12   | ⚠️ 加定时任务 + mem0 长期事实          |

每个场景对应 `experiments/scenarios/S0X/`。

---

#### M5.4 — 实验 E24-E25

- **E24** 多模态感受器：图像/音频/工具状态统一入池
- **E25** 叙事质量盲评：人工评价候选链连贯性

---

## 2.5 自迭代在 M3-M5 中的关键检查点

每个 M 阶段结束都要回答："这个 Agent 能开始自迭代了吗？"

| 阶段       | 自迭代就绪度检查                                             |
| -------- | ---------------------------------------------------- |
| **M3.5** | 工具齐备: read/write/test/git 都可用 ✅ (6+5+2 工具 + 闸门, 50 测试) |
| **M3.6** | 元循环跑通: dry-run 能生成 diff ✅ (9 步 + 5 重闸门 + CLI, 16 测试) |
| **M3.7** | 自迭代价值验证 ✅ (E21 奖励反事实 + E22 A/B 对照, 10 测试) |
| **M4.3a** | trace 能记录"改了什么 / 改的时长 / 是否成功" (JSONL 追加) ✅        |
| **M4.3b** | stats 能度量"调用次数 / 延迟分布 / 错误率" (counter/gauge/histogram) |
| **M4.4** | evals 套件能评估"这次自改是否比上次好"（A/B 度量）                      |
| **M5.3** | 业务场景 5 (长期陪伴) 中 Agent 实际自迭代过至少 1 次                   |
| **M5.4** | E24/E25 至少一个验证"自迭代产生价值"（如：Agent 自己补了某个测试）            |

---

## 3. 优先级与依赖

```
M3 ───┐
      ├─ M4 ── M5
      │
依赖：M3.1 (FastAPI) → M3.2 (多LLM) → M3.3 (MCP)
     M3.4 (错误处理) 横向贯穿

M4.1 (嵌入) ──┐
M4.2 (SQLite 增强) ──→ M4.3a (JSON trace) ──→ M4.4 (evals) ──→ M4.6 (元循环集成)
   M4.3b (sqlite-stats) ─┘                  ├→ M4.1 (嵌入) ──→ M4.5 (E23)

M5.1 (单进程部署) ──┐
M5.2 (JWT) ──────→ M5.3 (5 业务场景) ──→ M5.4 (E24-E25)
```

**关键路径**：M3.1 FastAPI → M3.2 多 LLM → M4.2 SQLite 增强 → M4.3a JSON trace → M4.3b sqlite-stats → M4.4 evals → M4.6 元循环集成 → M5.1 `python -m cogcore serve`

**不依赖路径**（如果环境受限可以跳过）：

- M3.3 MCP（需要 MCP server 运行环境）
- M4.1 嵌入（如果用 HDB-only 也能跑）
- M5.3 业务场景 4-5（可选）

---

## 4. 与 AGENT_BUILD.MD §6 阶段 D 的对照

| AGENT_BUILD.MD §6 D 阶段目标  | 落地到本计划                                |
| ------------------------- | ------------------------------------- |
| FastAPI chatbot endpoint  | M3.1                                  |
| JWT + slowapi             | M5.2                                  |
| Alembic migration         | **不采用**——SQLite 足够, 手动 schema 迁移 |
| Langfuse + Prom + Grafana | **不采用**——自写 JSON trace + sqlite-stats |
| Prometheus 配置             | **不采用**——StatsDB histogram in SQLite |
| Docker / Compose          | **不采用**——`python -m cogcore serve`    |
| sqlite-vec / pgvector      | **不采用**——numpy 嵌入 + SQLite BLOB (N<10K 时更快) |
| evals/ 套件                 | M4.4                                  |

阶段 D 全部分散到 M3-M5 各任务里。

---

## 5. 风险与开放问题

### 5.1 L6 语义层风险

- **依赖**：本机有 Ollama（已确认运行）或愿意调用 OpenAI Embeddings
- **已决**：用 numpy 存储向量 (sqlite-vec 是 native module, 违反"不装 native"铁律)
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

| 阶段     | 硬指标                                                                                                                         |
| ------ | --------------------------------------------------------------------------------------------------------------------------- |
| **M3** | 5 个 API 端点 ✅ + 3+ LLM provider 轮转 ✅ + 至少 1 个 MCP server 集成 ✅ + 错误处理三层全测 ✅ + 代码感知工具齐备 ✅ + 自迭代元循环干跑成功 ✅ + E21/E22 通过 ✅ + 400 tests |
| **M4** | M4.2 ✅ + M4.3a ✅ + M4.3b + M4.4 + M4.6 必做；M4.1 + M4.5 可选；460+ tests (441 当前); 自迭代就绪度表 M4.3a 已打勾 |
| **M5** | `python -m cogcore serve` 启动 + JWT 鉴权 + 5 业务场景至少 4 个能跑 + **业务场景中至少 1 个用过自迭代** + E24-E25 通过 + 420+ tests                     |

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

*最后更新：2026-06-06 (M4.2 + M4.3a 完成, 2/7 子阶段, 441 tests)*
