# CogCore M4 规划 — 持久化与可观测

> **目标**：让 Agent 真能观测 + 真能自评。
> **L 层覆盖**：`L6`（语义层）+ `L7`（持久化优化）+ `L8`（可观测性）+ `L11`（evals/）+ `L12.4`（元循环接入 evals 闭环）
>
> **上游上下文**：[CogCore-总体计划.md §2](./CogCore-总体计划.md)
> **上游依赖**：[CogCore-M3-规划.md](./CogCore-M3-规划.md) (M3.5+M3.6 必备)
> **下游**：[CogCore-M5-规划.md](./CogCore-M5-规划.md) (M5.1 单进程部署依赖 evals 报告)
> **状态**：⏳ **1/7 完成** (M4.2 SQLite 增强, 2026-06-06)

---

## 核心原则

**不引入 Docker / Postgres / Langfuse / Prom / Grafana / pgvector / sqlite-vec**。

`pip install cogcore` → `python -m cogcore serve` 单进程全跑。

为什么不上 sqlite-vec："永远不要自装 native module" 铁律（见 Pinned Memory），用 numpy 足够；N < 10K 时 cosine 距离比 sqlite-vec 还快。

---

## 依赖顺序

```
M4.2 (SQLite 维护)  ──┐
M4.3a (JSON trace)   ──┼──→ M4.4 (evals + A/B 度量) ──→ M4.5 (E23) ──→ M4.6 (M3.6 集成)
M4.3b (sqlite-stats) ──┘
M4.1 (嵌入) ──────────────────────────────────────────────→ M4.5 (E23)
```

## 子阶段总览

| 子阶段 | L 层 | 阻塞主路径？ | 核心交付 | 状态 |
|--------|------|------------|----------|------|
| **M4.2** SQLite 增强 | L7 | 是 (state.db 20MB 无上限) | vacuum / prune_checkpoints(N) / auto_backup / 容量预警 | ✅ 完成 (19 测试) |
| **M4.3a** JSON trace | L8 | 是 (M3.6 元循环需要看"上次改了什么") | `traces/YYYY-MM-DD.jsonl`, 每节点 `{ts,tick,node,duration_ms,status}`, 零依赖 viewer | ⏳ |
| **M4.3b** sqlite-stats | L8 | 是 (度量基础) | counter / gauge / histogram 三种 primitive | ⏳ |
| **M4.4** evals/ | L11 | 是 ("自改是否更好了"的判据) | `evals/<name>/eval.py` 协议 + A/B harness | ⏳ |
| **M4.1** 嵌入语义层 | L6 | 否 (HDB-only 也能跑) | Ollama (qwen3-embedding:0.6b) / OpenAI / numpy + SQLite BLOB | ⏳ |
| **M4.5** E23 | 实验 | 否 (依赖 M4.1) | 词级/字符级/向量混合感受器 | ⏳ |
| **M4.6** M3.6 集成 | L12.4 | 是 (自迭代闭环) | 把 M4.3 trace + M4.4 evals 喂给 M3.6 元循环 | ⏳ |

---

## M4.1 — 嵌入语义层 (`L6`)

**目标**：HDB（结构）之外增加嵌入（语义）双轨记忆。**不引入 pgvector / sqlite-vec，用 numpy + SQLite BLOB**。

**为什么不上 sqlite-vec**："永远不要自装 native module" 铁律（见 Pinned Memory），用 numpy 足够；N < 10K 时 cosine 距离比 sqlite-vec 还快。

**交付**：

- `src/cogcore/embeddings.py`：
  - `EmbeddingProvider`：抽象接口（`embed(text: str) -> list[float]`）
  - `OllamaEmbeddingProvider`：调 `qwen3-embedding:0.6b`（本地，无需 Docker）
  - `OpenAIEmbeddingProvider`：调 OpenAI text-embedding-3
  - `MockEmbeddingProvider`：测试用，确定性 hash-based 向量
- `src/cogcore/semantic_store.py`：
  - `SemanticStore`：默认用 numpy + SQLite（向量列存 BLOB）
  - `add(text, metadata)` / `search(query, top_k=5, threshold=0.7) -> list[(text, score, metadata)]`
  - cosine 距离在 Python 端算
- 与 HDB 协作：`DualStore` 包装 HDB + SemanticStore, HDB 命中走查存, miss 走相似度
- `config.toml`：选 embedding provider (`[embeddings] provider = "ollama" | "openai" | "mock"`)

**测试**：
- `tests/test_embeddings.py`：3 个 provider 都能 embed
- `tests/test_semantic_store.py`：存 + 查 + 相似度排序 + top_k 边界

**退出条件**：HDB miss 时能 fallback 到 SemanticStore, top-1 命中人造同义句

---

## M4.2 — SQLite 增强 (`L7` 优化) ✅ **已完成** (2026-06-06, 19 测试)

**目标**：SQLite 保持不动，**为高频访问路径加索引 + 备份 + 容量预警**。当前 `state.db` 已 20MB 且无限增长。

**交付**（全部完成）：
- ✅ `src/cogcore/db_maintenance.py` (415 行, stdlib only)
  - `vacuum(db_path)`: 压缩 SQLite (VACUUM 命令 + WAL checkpoint)
  - `prune_checkpoints(db_path, keep_last=100)`: 保留每 thread 最近 N 个 checkpoint
    用 rowid + ROW_NUMBER 窗口，严格区分 `thread_id` vs `thread_ts` 列
    max_delete 限制单次删除条数, 防止事务过大
  - `backup_to(db_path, backup_dir)`: sqlite3.Connection.backup() 拿一致性快照
  - `health_check(db_path) -> HealthReport`: 容量 + 表数 + 预警
    `HealthStatus`: OK / WARNING / CRITICAL
  - `full_maintenance()`: backup -> prune -> vacuum -> health 一键
- ✅ `scripts/db_health.py` (CLI, 退出码 0/1/2 对应 OK/WARN/CRITICAL)
  - `--prune --keep N`: 只 prune
  - `--vacuum`: 只 vacuum
  - `--backup dir/`: 备份
  - `--json`: JSON 输出
- ✅ `HealthStatus`, `VacuumResult`, `PruneResult`, `BackupResult`, `HealthReport` dataclass

**测试**: 19 个 (test_db_maintenance.py)
- vacuum (3): 缺文件、size 减少、字段完整
- prune (5): 缺文件、保留 N、noop、错误参数、限 batch、空表
- backup (3): 文件存在、创建嵌套目录、文件名时间戳
- health (5): missing、basic、warn、critical、dict JSON
- full_maintenance (2): pipeline、no-backup

**实测** (cogcore_data/state.db 真实数据, 122 thread, 2808 checkpoint):
```
原始:  20.01 MB / 2808 checkpoint
backup + prune --keep 3 + vacuum:
  backup 13.5MB, 删 1000 checkpoint, vacuum 释放 7.5MB
  终态: 5.83 MB / 808 checkpoint ✅ 71% 减少
```

**退出条件**：
- ✅ `state.db` 不会无限增长 (有 prune + vacuum)
- ✅ OOM 前能发出警告 (HealthStatus.WARNING/CRITICAL, CLI exit code)

---

## M4.3a — JSON trace (`L8`)

**目标**：每节点/每 LLM 调用的 trace。**不引入 Langfuse / Prom / Grafana**。

**交付**：

- `src/cogcore/json_tracer.py`：
  - `JSONTracer(path, node_name)`：context manager / decorator
  - 写入 `traces/YYYY-MM-DD.jsonl`，每行 `{ts, tick, node, duration_ms, status, error?, sha256_input, sha256_output}`
  - 支持 thread_id + tick 多维度聚合
- `scripts/trace_viewer.py`：纯 Python 读 JSONL → 输出表格 HTML（零依赖, 不引 Jinja）

**测试**：

- `tests/test_json_tracer.py`：写入格式正确、SHA-256 校验、viewer 输出 HTML
- 集成测试：跑 50 tick → 查 trace JSONL 验证每节点都有记录

**退出条件**：`python scripts/trace_viewer.py traces/2026-06-06.jsonl` 一条命令出 HTML

---

## M4.3b — sqlite-stats (`L8`)

**目标**：counter / gauge / histogram 三种度量 primitive。**不引 Prometheus**。

**交付**：

- `src/cogcore/sqlite_stats.py`：
  - `StatsDB(path)`：3 张表 `counter, gauge, histogram`
  - `incr(name, value=1)` / `set(name, value)` / `observe(name, value)` (P50/P95/P99 在 SQLite 端用 window function 算)
  - `report() -> dict` + `report_markdown()` 输出报告
- `scripts/stats_report.py`：从 sqlite-stats 输出 Markdown 报告

**测试**：

- `tests/test_sqlite_stats.py`：incr/set/observe 正确累加、histogram P50/P95/P99 计算正确

**退出条件**：`python -m cogcore.stats` 一条命令出报告

---

## M4.4 — evals/ 评测模块 (`L11` 升级)

**目标**：用「任务级 + 机制级」评测协议。**不引入 LangSmith Evals（云端依赖）**。

**交付**：

- `evals/` 目录协议：
  - `evals/<name>/eval.py`：接受一个 cogcore 状态, 返回 metrics dict
  - `evals/<name>/test_eval.py`：pytest 可跑
  - `evals/reports/<name>-YYYY-MM-DD.json`：报告存档
  - 必备 3 个 eval:
    - `evals/E21_reward_curve/eval.py`：不同奖励曲线 → NT 演化路径评估
    - `evals/E22_self_iter/eval.py`：自迭代前/后跑同一轨迹, 对比 metrics
    - `evals/agent_quality/eval.py`：对话质量 LLM-as-judge（用本地 Ollama 当 judge）
- `evals/ab_harness.py`：baseline vs candidate, paired diff 输出
- `pyproject.toml`：`pytest --evals` 入口（`[tool.pyproject] markers = ["evals: opt-in"]`）
- 报告输出：`evals/reports/<name>-2026-06-06.json` + 自动 diff 与上次

**测试**：跑 evals/ 套件，输出 JSON 报告

**退出条件**：`pytest --evals` 一键跑全套 evals/, 报告含 diff vs 上次

---

## M4.5 — 实验 E23

- **E23** 词级/字符级/向量混合：3 种粒度的感受器并存, 召回率 > HDB-only baseline

**退出条件**：E23 通过四项准入

---

## M4.6 — M3.6 元循环接入 evals (`L12.4` 闭环)

**目标**：把 M4.3 trace + M4.4 evals 喂给 M3.6 元循环, 让"自改是否更好"成为可测判据。

**交付**：

- `src/cogcore/self_iteration.py` 升级：
  - `evaluate_after_change(loop, before_metrics, after_metrics) -> "accept" | "revert"`
  - 当 eval score 不升反降时, 自动 `git revert` (之前只基于 test 失败 rollback, 现在基于 "evals 评分下降")
  - 记录每次 self-iter 的 `(before, after, decision, reason)` 到 `self_iteration.jsonl`
- `scripts/run_self_iteration.py` 加 `--with-evals` flag 走完整闭环

**测试**：

- `tests/test_self_iteration_ab.py`：构造 before/after metrics, 验证 accept/revert 决策
- 集成测试：故意引入 perf regression → 期望自动 revert

**退出条件**：自迭代闭环跑通, "改-测-evals-决策" 4 步全部自动化

---

## M4 退出准则

| 指标 | 目标 | 实际 |
|------|------|------|
| 测试 | 460+ (60 个新增) | 419 (M4.2 已 +19, 余下 41 待 M4.3a-M4.6) |
| 阻塞子阶段 | M4.2 + M4.3a + M4.3b + M4.4 + M4.6 必做 | M4.2 ✅, 其余 ⏳ |
| 关键路径 | M3.6 元循环接入 evals 后, A/B 决策可工作 | 待 M4.6 |
| 实验 | E23 通过 (依赖 M4.1) | 待 M4.1+M4.5 |
| 不引入 | Docker / Postgres / pgvector / sqlite-vec / Langfuse / Prom / Grafana | 0 依赖 ✅ |
| 自迭代就绪度表 | M4.3a / M4.3b / M4.4 三行都打勾 | 待 |

**执行顺序**：M4.2 ✅ → M4.3a → M4.3b → M4.4 → M4.1 → M4.5 (含 E23) → M4.6

---

*最后更新：2026-06-06 (M4.2 完成, 1/7 子阶段)*
