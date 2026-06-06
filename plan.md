# CogCore M5 执行计划 — 部署与多场景

> **目标**：让 Agent 真能用。`python -m cogcore serve` 一个进程起步。
> **L 层覆盖**：L1（完善）+ L9（部署）+ 5 业务场景
> **上游**：M4 全部完成（473 passed / 5 skipped）
> **设计不变量**：零 Docker / 零外部服务（除可选远程 LLM）

---

## 子阶段总览

| 子阶段 | L 层 | 阻塞主路径？ | 核心交付 | 预估测试 |
|--------|------|------------|----------|---------|
| **M5.1** 单进程部署 | L9 | 是 | `python -m cogcore serve` CLI + 热重载 + 数据目录 | 8 |
| **M5.2** JWT + slowapi | L9 | 否 | JWT 签发/校验 + 速率限制 + 结构化日志 | 10 |
| **M5.3** 5 业务场景 | L1 | 是 | 人工干预 + 多 Agent 协作 + 长期陪伴 | 15 |
| **M5.4** 实验 E24-E25 | 实验 | 否 | 多模态感受器 + 叙事质量盲评 | 6 |

**执行顺序**：M5.1 → M5.2 → M5.3 → M5.4
**关键路径**：M5.1 serve CLI → M5.3 业务场景 3（人工干预）→ M5.3 场景 5（长期陪伴）→ M5.4 E24

---

## M5.1 — 单进程部署（L9）

### 目标
`python -m cogcore serve` 一个进程起步，支持开发/生产/后台三种模式。

### 交付清单

#### 1. `src/cogcore/serve.py` — CLI 入口
```python
# 支持命令：
python -m cogcore serve              # 默认 127.0.0.1:8000
python -m cogcore serve --port 8080 --host 0.0.0.0
python -m cogcore serve --reload   # 开发热重载
python -m cogcore serve --data-dir ~/.cogcore
python -m cogcore serve --workers 1  # 多进程（可选，默认 1）
```

实现要点：
- 用 `argparse` 解析参数
- 调用 `uvicorn.run()` 启动 FastAPI
- `--reload` 时传 `reload=True`（开发模式）
- `--data-dir` 设置 `COGCORE_SERVICE_DATA_DIR` 环境变量后启动
- 优雅关闭：捕获 SIGINT/SIGTERM，调用 `service.stop()`

#### 2. `pyproject.toml` 更新
```toml
[project.scripts]
cogcore = "cogcore.serve:main"
```
安装后可直接：`cogcore serve`

#### 3. `app/main.py` 升级
- 版本号 `0.3.0` → `0.5.0`
- 增加 `/health` 端点（如果还没有）
- 增加启动时日志：打印 CogCore 版本 + 数据目录 + 持久化后端

#### 4. `scripts/install-service.sh`（可选，Linux/macOS）
- systemd user service 模板
- 不阻塞主路径，M5.1 退出后可做

#### 5. `scripts/install-service.ps1`（可选，Windows）
- NSSM / Task Scheduler 注册模板
- 不阻塞主路径

### 测试清单（8 个）

| 测试 | 文件 | 内容 |
|------|------|------|
| serve CLI 参数解析 | `tests/test_serve.py` | `--port`, `--host`, `--reload`, `--data-dir` 都能正确解析 |
| serve 启动 FastAPI | `tests/test_serve.py` | mock uvicorn.run，验证参数传递 |
| serve 设置环境变量 | `tests/test_serve.py` | `--data-dir` 设置 COGCORE_SERVICE_DATA_DIR |
| health 端点 | `tests/test_api.py` | `/health` 返回 `{status: ok, version, tick_count}` |
| 启动日志 | `tests/test_api.py` | 启动时打印版本和数据目录 |
| 优雅关闭 | `tests/test_serve.py` | SIGINT 触发 service.stop() |
| 数据目录创建 | `tests/test_serve.py` | 自动创建 ~/.cogcore |
| 端到端 | `tests/test_api.py` | `python -m cogcore serve &` → curl /health → kill |

### 退出条件
- `python -m cogcore serve` 能启动，curl `/health` 通
- `cogcore serve`（pip 安装后）也能启动
- 8 个测试全部通过

---

## M5.2 — JWT + slowapi（L9 补全）

### 目标
基础生产安全：身份验证 + 速率限制 + 结构化请求日志。

### 交付清单

#### 1. `app/auth/jwt.py` — JWT 签发/校验
```python
class JWTAuth:
    def create_token(user_id: str, expires_hours: int = 24) -> str
    def verify_token(token: str) -> dict  # 失败抛 HTTPException 401
```
- 密钥从 `config.toml` `[auth] secret = "..."` 读取，缺省用随机生成 + 警告
- 算法：HS256
- 不引入 `python-jose`（额外依赖），用 `PyJWT`（轻量）

#### 2. `app/middleware/rate_limit.py` — 速率限制
- 用 `slowapi` 库（已确认可用）
- 全局限制：100 req/min
- `/chat` 端点单独限制：30 req/min
- 超限返回 429 + `Retry-After` 头

#### 3. `app/middleware/logging.py` — 结构化请求日志
```python
class StructuredLoggingMiddleware:
    # 每请求记录：ts, method, path, status, duration_ms, client_ip
    # 输出到 stdout（systemd/journald 会收集）
```
- 格式：JSON Lines（`{"ts": "...", "method": "POST", "path": "/chat", ...}`）
- 不引入文件日志轮转（systemd 处理）

#### 4. `app/main.py` 集成
- 注册 JWT 依赖：`Depends(get_current_user)`
- 注册 slowapi 中间件
- 注册结构化日志中间件
- 公开端点（/health）免 JWT，其余需认证

### 测试清单（10 个）

| 测试 | 文件 | 内容 |
|------|------|------|
| JWT 签发 | `tests/test_auth.py` | create_token 返回非空字符串 |
| JWT 校验通过 | `tests/test_auth.py` | verify_token 返回 payload |
| JWT 校验失败 | `tests/test_auth.py` | 过期/篡改 token 抛 401 |
| 无 JWT 访问受保护端点 | `tests/test_auth.py` | 返回 401 |
| 速率限制触发 | `tests/test_rate_limit.py` | 31 次请求后第 31 次返回 429 |
| 速率限制头 | `tests/test_rate_limit.py` | 429 响应带 Retry-After |
| 结构化日志格式 | `tests/test_logging.py` | 输出为合法 JSON |
| 结构化日志字段 | `tests/test_logging.py` | 含 method, path, status, duration_ms |
| health 免认证 | `tests/test_auth.py` | /health 无 JWT 也能访问 |
| 集成：JWT + rate limit + log | `tests/test_api.py` | 一个请求走完全链路 |

### 退出条件
- 带 JWT 的请求能访问 /chat，不带返回 401
- 31 次 /chat 请求后触发 429
- 请求日志是合法 JSON Lines
- 10 个测试全部通过

---

## M5.3 — 5 业务场景（L1 完善）

### 目标
从"有 API"到"能跑真实业务"。

### 场景现状

| # | 场景 | 状态 | 需做 |
|---|------|------|------|
| 1 | 基础对话 | ✅ 已有 | 无需改动 |
| 2 | 工具调用 | ✅ 已有 | 无需改动 |
| 3 | **人工干预 (HITL)** | ❌ | 加 `interrupt_before` + 教师门控 |
| 4 | **多 Agent 协作** | ❌ | 多 CogCore 实例 + Store 共享 |
| 5 | **长期陪伴** | ⚠️ | 加定时任务 + 长期事实 |

### 场景 3 — 人工干预（HITL）

**交付**：
- `app/api/v1/hitl.py` — 新端点
  - `POST /hitl/request` — 提交人工干预请求（挂起 Agent）
  - `GET /hitl/pending` — 查看待处理请求列表
  - `POST /hitl/respond/{request_id}` — 人工回复，恢复 Agent
- `src/cogcore/hitl.py` — HITL 状态机
  - `HITLRequest`: {id, status(pending/approved/rejected), prompt, response, created_ts}
  - `HITLManager`: 挂起/恢复 tick，对接 `teacher_gate_should_wake`
- 与 `reinforced_agency` 模式联动：人工审批 = 教师门控

**测试**（5 个）：
- 提交干预请求 → Agent 挂起
- 查询待处理列表 → 返回 pending 项
- 人工回复 → Agent 恢复
- 超时自动拒绝 → 返回 rejected
- 与 reinforced_agency 集成 → 教师门控生效

### 场景 4 — 多 Agent 协作

**交付**：
- `src/cogcore/multi_agent.py` — 多 Agent 协调器
  - `AgentPool`: 管理多个 CogCoreService 实例（同进程内）
  - `SharedStore`: 基于 SQLite 的跨 Agent 状态共享（不引入 LangGraph Store 外部依赖）
  - `delegate(task, from_agent, to_agent)`: 任务委派
- `app/api/v1/multi_agent.py` — 端点
  - `POST /agents/spawn` — 创建新 Agent 实例
  - `POST /agents/{id}/delegate` — 委派任务
  - `GET /agents/{id}/status` — 查看状态

**测试**（5 个）：
- 创建 2 个 Agent → 各自独立状态池
- 共享 Store 写入 → 另一 Agent 能读到
- 任务委派 → 目标 Agent 状态池出现任务 atom
- 委派超时 → 返回错误
- 同进程 3 个 Agent 并发 tick → 无数据竞争

### 场景 5 — 长期陪伴

**交付**：
- `src/cogcore/scheduler.py` — 轻量定时任务
  - 不引入 APScheduler（额外依赖），用 threading.Timer 轮询
  - `ScheduledTask`: {id, cron_expr, action, last_run, next_run}
  - `TaskScheduler`: 每分钟检查一次，触发到期任务
- 定时任务类型：
  - `diary_digest`: 每日日记摘要写入
  - `pool_prune`: 自动清理低能量状态对象
  - `health_ping`: 写入 stats 心跳
- `app/api/v1/scheduler.py` — 端点
  - `GET /scheduler/tasks` — 查看任务列表
  - `POST /scheduler/tasks` — 添加定时任务
  - `DELETE /scheduler/tasks/{id}` — 删除

**测试**（5 个）：
- 添加定时任务 → 出现在列表
- 任务到期触发 → action 被执行
- 删除任务 → 不再触发
- 日记摘要任务 → 写入 diary
- 长期运行 10 tick + 2 个定时任务 → 无异常

### 退出条件
- 3 个新场景各 5 个测试通过（共 15 个）
- `experiments/scenarios/S03/` / `S04/` / `S05/` 目录含 design.md + report.md

---

## M5.4 — 实验 E24-E25

### E24 — 多模态感受器

**目标**：图像/音频/工具状态统一入池（属性化入口，不验证实时机器人控制）。

**交付**：
- `src/cogcore/sensors.py` 扩展：
  - `ImageSensor`: 接收 base64 图像 → 提取属性标签（颜色/物体/场景）入池
  - `AudioSensor`: 接收文本转录 → 情绪关键词入池
  - `ToolStateSensor`: 工具执行结果结构化入池
- 与现有 `TextSensor` 并存，统一走 `StimulusAtom` 入池

**测试**（3 个）：
- ImageSensor 处理 base64 → 池中出现 "image_red_car" 类 atom
- AudioSensor 处理转录 → 池中出现情绪关键词
- ToolStateSensor 处理工具结果 → 结构化 atom 可追踪

### E25 — 叙事质量盲评

**目标**：人工（或 LLM-as-judge）评价候选链连贯性。

**交付**：
- `experiments/E25/` — 实验目录
- `narrative_quality.py` — 叙事质量评估器
  - 输入：CogCore 生成的候选链（10 个 tick 的 CAM 序列）
  - 输出：连贯性评分（0-1）+ 断裂点标记
  - 评分维度：主题一致性 / 因果连贯 / 信息增量
- 用本地 Ollama（qwen3:0.6b）当 judge，不依赖云端

**测试**（3 个）：
- 连贯链评分 > 0.7
- 断裂链评分 < 0.4
- 评分结果可复现（同输入同输出）

### 退出条件
- E24 通过 3 项准入（属性化入口验证）
- E25 通过 3 项准入（叙事质量可测）
- 6 个测试全部通过

---

## 依赖与顺序

```
M5.1 (serve CLI)
  │
  ├─ M5.2 (JWT + slowapi) ── 依赖 M5.1 的 FastAPI 应用
  │
  ├─ M5.3 场景 3 (HITL) ── 依赖 M5.1 的 service 生命周期
  │
  ├─ M5.3 场景 4 (多 Agent) ── 依赖 M5.1 的 deps.py 单例模式
  │
  ├─ M5.3 场景 5 (长期陪伴) ── 依赖 M5.1 的 service 后台 tick
  │
  └─ M5.4 (E24-E25) ── 依赖 M5.3 场景 5 的 scheduler（可选）
```

**可并行**：
- M5.2 和 M5.3 场景 3 可并行（独立功能）
- M5.3 场景 4 和 场景 5 可并行
- M5.4 E24 和 E25 可并行

**阻塞主路径**：M5.1 → M5.3 场景 3 → M5.3 场景 5

---

## 新增文件清单

| 文件 | 所属阶段 | 说明 |
|------|----------|------|
| `src/cogcore/serve.py` | M5.1 | CLI 入口 |
| `tests/test_serve.py` | M5.1 | serve 测试 |
| `app/auth/jwt.py` | M5.2 | JWT 签发/校验 |
| `app/middleware/rate_limit.py` | M5.2 | slowapi 速率限制 |
| `app/middleware/logging.py` | M5.2 | 结构化日志 |
| `tests/test_auth.py` | M5.2 | JWT 测试 |
| `tests/test_rate_limit.py` | M5.2 | 速率限制测试 |
| `tests/test_logging.py` | M5.2 | 日志测试 |
| `src/cogcore/hitl.py` | M5.3 | HITL 状态机 |
| `app/api/v1/hitl.py` | M5.3 | HITL 端点 |
| `tests/test_hitl.py` | M5.3 | HITL 测试 |
| `src/cogcore/multi_agent.py` | M5.3 | 多 Agent 协调器 |
| `app/api/v1/multi_agent.py` | M5.3 | 多 Agent 端点 |
| `tests/test_multi_agent.py` | M5.3 | 多 Agent 测试 |
| `src/cogcore/scheduler.py` | M5.3 | 定时任务调度器 |
| `app/api/v1/scheduler.py` | M5.3 | 调度器端点 |
| `tests/test_scheduler.py` | M5.3 | 调度器测试 |
| `experiments/E24/` | M5.4 | 多模态感受器实验 |
| `experiments/E25/` | M5.4 | 叙事质量盲评实验 |
| `scripts/install-service.sh` | M5.1 可选 | systemd 模板 |
| `scripts/install-service.ps1` | M5.1 可选 | Windows 服务模板 |

---

## 退出准则（M5 整体）

| 指标 | 目标 |
|------|------|
| 测试 | 500+ (473 + 39 新增) |
| M5.1 | `python -m cogcore serve` 启动 + curl /health 通 |
| M5.2 | JWT 认证生效 + 速率限制触发 + 结构化日志输出 |
| M5.3 | 3 个新场景各 5 测试通过，业务场景目录归档 |
| M5.4 | E24 + E25 通过准入 |
| 自迭代 | 业务场景 5 中 Agent 实际自迭代过至少 1 次 |
| 零 Docker | 不引入 Docker / Compose / Postgres |

---

*计划制定于 2026-06-06，基于 M4 全部完成状态（473 passed / 5 skipped）。*
