# CogCore M3 规划 — 智能体能力补全

> **目标**：让 Agent 真能干活。
> **L 层覆盖**：`L1`（基础 FastAPI）+ `L4`（多 LLM）+ `L5`（MCP 接入）+ `L10`（错误处理）+ `L12.1`/`L12.2`（代码自检/自改）
>
> **上游上下文**：[CogCore-总体计划.md §2](./CogCore-总体计划.md)
> **下游**：[CogCore-M4-规划.md](./CogCore-M4-规划.md)
> **状态**：✅ **全部完成** (2026-06-06, 7 子阶段, 138 测试)

---

## M3 进度表

| 子阶段 | 主题 | L 层 | 测试 | 状态 |
|--------|------|------|------|------|
| **M3.1** | FastAPI 接入 | L1 | 13 | ✅ |
| **M3.2** | LLMRegistry + circular fallback | L4 | 14 | ✅ |
| **M3.3** | MCP 工具接入 | L5 | 15 | ✅ |
| **M3.4** | 错误处理层 | L10 | 20 | ✅ |
| **M3.5** | 代码感知工具集 (L12.1+L12.2) | L12 | 50 | ✅ |
| **M3.6** | 自迭代元循环 (L12.3) | L12 | 16 | ✅ |
| **M3.7** | 实验 E21-E22 (L12 价值验证) | 实验 | 10 | ✅ |
| **合计** | | | **138** | |

---

## 关键设计原则

1. **零 Docker / 零 Postgres / 零 Langfuse** — `pip install cogcore` → `python -m cogcore serve`
2. **本地优先** — Ollama / SQLite / OpenAI 兼容协议
3. **MCP 自己实现 JSON-RPC 客户端** — 避免引 `mcp` 包保持依赖最小
4. **自迭代是北星** — L12 跨 M3-M5, 4 子层 (L12.1 自检 / L12.2 自改 / L12.3 元循环 / L12.4 evals 闭环)
5. **安全闸门内置** — `self_modify_safety.py` 5 重闸门 (路径 / 命令 / pytest args / commit msg / 路径越界)

---

## M3.1 — FastAPI 接入 (`L1`)

**目标**：把 CogCore 暴露成 HTTP/WebSocket 服务，可被任何客户端调用。

**交付**：
- `app/main.py`：FastAPI 应用入口
- `app/api/v1/chat.py`：`POST /v1/chat` 端点
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

## M3.2 — LLMRegistry + circular fallback (`L4` 升级)

**目标**：多 LLM 轮转，单个失败自动切下一个。

**交付**：
- `src/cogcore/llm_registry.py`：
  - `LLMRegistry`：管理多个 `LLMBridge` 实例
  - `LLMService`：调用入口，按顺序尝试
  - `circular fallback`：第一失败 → 第二 → ... → 第一（健康）
- `config.toml` 多 LLM 段
- `scripts/test_llm_fallback.py`：故障注入（mock 一家挂掉）

**测试**：
- `tests/test_llm_registry.py`：注册、轮转、回退
- `tests/test_circular_fallback.py`：3 个 provider 中 1 个挂掉，能切换

**退出条件**：3 个 mock LLM 轮转，1 个永久失败后继续用剩下的

---

## M3.3 — MCP 工具接入 (`L5` 升级)

**目标**：CogCore Agent 能加载并调用 MCP server 的工具。

**交付**：
- `src/cogcore/mcp_adapter.py`：
  - `MCPAdapter`：连接 MCP server，列出工具，注册到 ToolRegistry
  - `mcp://` 协议支持（自实现 JSON-RPC over stdio, 不引 `mcp` 包）
- `tests/mock_mcp_server.py`：3 工具 (echo/add/reverse) 测试桩
- `scripts/test_mcp_integration.py`：接 Brave Search / Firecrawl MCP server

**关键设计**：
- stdlib subprocess + JSON-RPC, newline-delimited
- MCPClient._request 默认 timeout 60s（用户反馈 30s 太短）
- 失败检测：`[LLM Error: ...]` 字符串前缀

**测试**：
- `tests/test_mcp_adapter.py`：mock MCP server 协议
- 集成测试：接 Firecrawl MCP，搜 "CogCore"

**退出条件**：ToolRegistry 中能列出 MCP 工具 + Agent 实际调用

---

## M3.4 — 错误处理层 (`L10` 补全)

**目标**：节点级重试 + 模型级 fallback + 系统级教师门控三层联动。

**交付**：
- `src/cogcore/retry.py`：`with_retry(node_fn, max_attempts=3, backoff=tenacity)` 包装器
- `graph.py` 中所有 10 个 stage 节点默认包 retry
- 文档：M3.4-RFC.md 三层错误处理设计

**三层错误处理**：
- **L1 retry** — 节点失败重试 3 次, 仅 retry transient (ConnectionError, TimeoutError, OSError)
- **L2 LLM fallback** — LLMRegistry 切下一个 provider
- **L3 教师门控** — sustained anomaly 时人工审批

**测试**：
- `tests/test_retry.py`：节点失败 → 重试 3 次 → 放弃
- `tests/test_three_layer_errors.py`：三层联动
- 集成测试：LLM 调用超时 → fallback 到第二个 provider

**退出条件**：3 层错误处理有完整测试覆盖

---

## M3.5 — 代码感知工具集 (`L12.1` 自检 + `L12.2` 自改) ✅

**目标**：让 Agent 拥有读源码、跑测试、git 操作的工具。**这是自迭代的启动点**。

**交付**（全部完成，2026-06-05）：
- ✅ `src/cogcore/tools_code.py`（6 工具）：read_file / search_code / list_modules / list_tests / find_test_for_module / count_lines
- ✅ `src/cogcore/tools_git.py`（5 工具）：git_status / git_diff / git_log / git_commit / git_revert
- ✅ `src/cogcore/tools_exec.py`（2 工具）：run_tests / run_command
- ✅ `src/cogcore/self_modify_safety.py`：路径 / 命令 / pytest args / commit message / 路径越界 五重闸门

**安全约束**（全部实现）：
- ✅ 路径必须是 `src/cogcore/` / `tests/` / `docs/` / `scripts/` / `experiments/`
- ✅ 不能改 config.toml / pyproject.toml / AGENTS.md 等治理文件
- ✅ pytest 禁止 -k skip / --deselect
- ✅ commit message 必含 [auto-iterate] 标签
- ✅ 拒绝 rm/rmdir/del/mv/format/fork bomb
- ✅ 拒绝 ../ 越界

**测试**：50 个 (test_m35_code_tools.py 14 + test_m35_safety_and_git.py 36)

**MCP 超时**：MCPClient._request 默认 30s → 60s (用户反馈 30s 太短)

---

## M3.6 — 自迭代元循环 (`L12.3` + `L12.4` 起步) ✅

**目标**：把"自检 / 自改 / 自部署 / 自学"组装成可执行的元循环。

**交付**：
- `src/cogcore/self_iteration.py` — `SelfIterateLoop` 类 9 步:
  1. `observe()`：拉当前 tick 状态 + 测试结果
  2. `detect_gap()`：根据 CFS 不协调感 + 评测失败率触发
  3. `plan_fix()`：调 LLM 生成修复计划
  4. `read_source()`：调代码工具读相关源码
  5. `propose_change()`：LLM 写 diff
  6. `test()`：跑 pytest，必须 100% 过
  7. `commit()`：git commit，message 包含 `[auto-iterate]` 标签
  8. `reload()`：热重载被改的 module（importlib.reload + 简单 health check）
  9. `log()`：写入 `self_iteration.jsonl`

- `scripts/run_self_iteration.py`：
  - `--dry-run`：只生成 diff 不 commit
  - `--once`：跑一次
  - `--loop`：持续循环（每 N 秒）
  - `--interval N`：循环间隔

**热重载实现**：
- Python `importlib.reload()`：简单但脆弱
- **推荐**：`importlib.reload` + `run_tests` 验证 + `run_health_check`（跑 5 tick 看指标）

**安全检查点**（每步都验证）：
- `test()` 失败 → 跳过 commit、写错误到日志、保留修改为 untracked
- `reload()` 后 5 tick 内出现 error_log 项 ≥ 3 → 自动 git revert
- 每个 commit message 必须包含 `[auto-iterate]` 标签 + gap ID

**测试**：
- `tests/test_self_iteration.py`：16 个 (mock 仓库 + mock LLM，验证 9 步流程 + 安全回滚 + dry-run)

**退出条件**：`python scripts/run_self_iteration.py --dry-run` 能针对"测试失败率 30%"生成 fix diff（不真改）

---

## M3.7 — 实验 E21-E22 ✅

- **E21** 奖惩反事实课程 (5 条奖励曲线, 100 tick, NT 演化路径对比) ✅
  - linear_asc / plateau_spike / inverse_u / punishment_first / random
  - 判据: arousal_range > 0.1 (paths diverge)
  - 判据: punishment_fatigue >= linear_fatigue (惩罚累积疲劳)
  - 实测: arousal range 0.658, fatigue 0.079 vs 0.0
  - 文件: `experiments/E21/{design.md, report.md, manifest.json, tables/summary.json}`
- **E22** 自迭代 A/B 对照 (M3.6 元循环在 3 个合成失败场景) ✅
  - 3 场景: logic_error / type_error / import_error
  - Branch A: 走完整 9 步元循环
  - Branch B: no-op baseline (只 observe + detect)
  - 判据: detect 一致性 (A 和 B 都 detect)
  - 判据: 合成失败必须 rollback (不偷留 untracked 改动)
  - 实测: 3/3 detect, 3/3 rolled back ✅
  - 文件: `experiments/E22/{design.md, report.md, manifest.json, tables/summary.json}`

**退出条件**: E21/E22 通过验证矩阵四项准入 + 全部 6 个产物文件 SHA-256 记录 ✅

**运行**:
- `python scripts/run_m37_experiments.py` (所有实验, ~3s)
- `python -m pytest tests/test_e21_e22.py -v` (单元测试, < 1s)

---

## M3 退出准则（已满足）

| 指标 | 目标 | 实际 |
|------|------|------|
| 测试 | 138 新增 | 138 ✅ |
| 模块 | 30 → 32 | 32 ✅ |
| 阶段状态 | M3.1-M3.7 全部 ✅ | 全 ✅ |
| E21/E22 | 通过 + SHA-256 记录 | 12 文件 ✅ |
| 自迭代就绪度 | L12.1-L12.3 打勾 | 全 ✅ |
| 不引入 | Docker / Postgres / Langfuse | 0 依赖 ✅ |

---

*最后更新：2026-06-06 (M3 全部完成, 7 子阶段, 138 测试)*
