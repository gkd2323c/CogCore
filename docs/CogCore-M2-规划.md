# CogCore M2 阶段规划：持续认知服务 + 端到端 Agent

> **阶段定位**：让 CogCore 从一个「被调用的认知内核」变成一个「持续运行的认知服务」。
>
> 前置条件：阶段一（M0, E01-E17）和阶段二（M1, LLM桥接/持久化/工具/模式）已于 2026-06-05 全部完成。

---

## 1. 阶段目标

M0 让 CogCore 有了认知内核，M1 让它能跟 LLM 和工具对话。M2 让它在后台持续运行——自己管理 ticks、自己决定何时醒来、自己维护记忆连续性。

核心转变：**从「被调用的函数」到「持续运行的服务」**。

```
M0 ──── 内核原型     ✅ 认知闭环 + 17 项实验
M1 ──── 应用耦合     ✅ LLM 桥接 + 持久化 + 工具 + 模式
M2 ──── 持续服务     ⏳ 后台运行 + 长程稳定 + 自主维护
```

### 阶段退出条件

| 条件 | 检查点 | 状态 |
|------|--------|------|
| CogCore 可作为后台服务持续运行 | `cogcore_service` 进程可 24h+ 不间断 | ✅ |
| 后台自动写入日记 | 每 100 ticks 至少 1 条自动日记 | ✅ |
| 3000+ tick 长程不发散 | 能量轨迹不无限增长 / 不归零 | ✅ |
| E18-E20 实验全部通过 | 验证矩阵已更新 | ✅ |
| 端到端 Agent 可执行真实工具 | calc / echo / diary 已可用 | ✅ |
| 总测试数 ≥ 260 | 实际 260 | ✅ |

---

## 2. 里程碑总览

```
M2.1 ─── 后台认知服务      持续 tick 调度 + 自动日记 + 进程
M2.2 ─── 端到端 Agent       5 步消息流 + ToolExecutor + CLI/TUI
M2.3 ─── 长程稳定性实验     E18 (3000 tick) + E19 (APT消融) + E20 (CFS/NT消融)
M2.4 ─── 工具箱深化        更多实用工具 + skill_run 协议
```

### 依赖关系

```
M2.1 (后台服务)
  ├── M2.2 (端到端 Agent) ── 需要后台 tick 调度就绪
  │
  └── M2.3 (长程实验) ── 需要后台服务长时间运行
        │
        └── M2.4 (工具箱) ── 独立，可并行
```

---

## 3. M2.1 — 后台认知服务

### 目标

让 CogCore 能作为后台进程持续运行：按间隔自动 tick、监控内部状态、自动写入日记、支持唤醒/休眠。

### 架构

```
CogCoreService
  │
  ├── scheduler: 定时触发 tick（every N seconds）
  ├── wake_controller: 判断是否应主动醒来
  ├── auto_diary: 每 K ticks 自动写日记
  ├── health_monitor: 检查能量轨迹、NT 疲劳
  └── persistence: SQLite 自动保存状态
```

### 交付物

| 文件 | 改动 | 测试数 |
|------|------|--------|
| `src/cogcore/service.py` | CogCoreService 后台服务类 | ~10 |
| `scripts/run_service.py` | 后台服务启动入口 | — |
| `config.toml.example` | 新增 [service] 配置节 | — |
| `tests/test_service.py` | 服务测试 | ~8 |

### 核心接口

```python
class CogCoreService:
    """持续运行的 CogCore 认知服务。"""

    def __init__(self, config_path: str | None = None):
        # 加载配置、初始化模块、构造 graph

    def start(self):
        """启动后台 tick 循环。"""

    def stop(self):
        """优雅停止。"""

    def tick(self) -> dict:
        """执行一次认知 tick。"""

    def inject_input(self, text: str):
        """注入外源输入（会触发立即 tick）。"""

    def get_status(self) -> dict:
        """当前状态报告。"""

    @property
    def running(self) -> bool:
        """是否在运行。"""
```

### 配置

```toml
[service]
# 后台 tick 间隔（秒），0=不自动 tick
tick_interval = 60

# 自动写日记间隔（ticks）
diary_interval = 100

# 状态报告间隔（ticks）
report_interval = 500

# 数据目录
data_dir = "cogcore_data"
```

### 测试要点

- start/stop 不抛异常
- 注入输入后 ticks 增加
- 自动日记在达到间隔时写入
- 状态报告格式稳定

---

## 4. M2.2 — 端到端 Agent

### 目标

实现论文 §6.1.2 的 5 步消息流，让 CogCore 驱动一个完整的 Agent 交互。

### 5 步消息流

```
1. ingest + should_wake
   └─ 判断是否值得进入主链

2. CogCore tick（10 阶段）
   └─ 生成当前认知状态

3. build_context_packet
   └─ 翻译为 LLM prompt

4. LLM → execute_tool_calls
   └─ 工具执行 → 结果回写 CogCore

5. 最终回复 / 继续思考
   └─ 生成回复 → 等待下一轮输入
```

### 交付物

| 文件 | 改动 | 测试数 |
|------|------|--------|
| `src/cogcore/agent.py` | Agent 类——封装 5 步流 | ~8 |
| `src/cogcore/tool_executor.py` | 工具执行器（从 LLM 解析工具调用） | ~5 |
| `tests/test_agent.py` | Agent 测试 | ~8 |
| `scripts/demo_agent.py` | 交互式 Agent demo | — |

### 核心接口

```python
class CogCoreAgent:
    """CogCore 驱动的端到端 Agent。"""

    def __init__(self, config_path: str | None = None):
        ...

    async def process_message(
        self,
        message: str,
        thread_id: str = "default",
    ) -> AgentResponse:
        """处理一条用户消息，返回回复。

        内部执行 5 步流：
        1. should_wake
        2. CogCore tick(s)
        3. build_context_packet
        4. LLM + tool_executor
        5. 格式化回复
        """
```

---

## 5. M2.3 — 长程稳定性实验

### 目标

运行 E18-E20 三项 P0 实验，验证 CogCore 在长时间运行下的稳定性。

### 交付物

| 实验 | 验证内容 | 判据数 | 预计测试 |
|------|---------|--------|---------|
| E18 长程稳定性 | 3000+ tick 能量/结构/情绪不发散 | 待定 | ~5 |
| E19 APT 消融 | 关闭调参器后系统是否过载/沉寂 | 96 | ~3 |
| E20 CFS/NT 消融 | 关闭情绪后行动阈值是否僵化 | 84 | ~3 |

### 设计要点

- E18：运行 3000+ tick，每 100 tick 记录一次状态快照
  - 能量总和不无限增长（< 初始值 × 3）
  - 不归零（> 初始值 × 0.01）
  - NT 各通道不卡在边界（不在 0 或 1 超过 500 tick）
- E19：通过 `AdaptiveTuner` 的旁路开关关闭调参
  - 观察状态池是否进入过载（total_energy 持续 > 阈值）
- E20：通过 `CFS` / `NT` 的旁路开关关闭情绪调制
  - 观察行动阈值是否僵化（多个 action 的 drive 趋同）

---

## 6. M2.4 — 工具箱深化

### 目标

扩展 ToolRegistry，添加更多实用工具，实现 skill_run 协议。

### 新增工具

| 工具 | 功能 | 依赖 |
|------|------|------|
| `web_search` | 联网搜索（Firecrawl/Tavily） | API Key |
| `calc` | Python 表达式计算 | 内置 |
| `note` | 快速记笔记（同 diary 但更轻量） | 无 |
| `skill_run` | 运行动态加载的技能脚本 | API |

### skill_run 协议

```python
# skill_run 协议（论文 5.7.4 简版）
# 技能 = 一段 Python 代码 + schema 声明
# 通过 ToolRegistry 注册为可调用工具

class Skill:
    name: str
    description: str
    code: str  # Python 代码
    schema: dict  # 参数 schema
```

---

## 7. 预估工作量

| 里程碑 | 新增测试 | 核心文件 | 估算 |
|--------|---------|---------|------|
| M2.1 后台服务 | ~18 | `service.py` | 中 |
| M2.2 端到端 Agent | ~16 | `agent.py`, `tool_executor.py` | 中 |
| M2.3 长程实验 | ~11 | `experiments/E18-E20/` | 中 |
| M2.4 工具箱 | ~10 | `tools.py` 扩展 | 小 |
| **总计** | **~55 新增** | **总测试 ~283** | |

---

## 8. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|------|--------|------|------|
| 3000 tick 运行时间太长 | 中 | M2.3 耗费时间 | 3000 tick ≈ 几秒（非实时的 tick），不阻塞 |
| 后台服务进程管理复杂 | 低 | M2.1 延迟 | 用 Python 子进程 + signal 管理，不引入 Supervisor |
| 工具执行安全性 | 低 | M2.4 | calc/skill_run 需沙箱（M2 简版不做沙箱，仅提示警告） |
| 范围蔓延到 M3 内容 | 中 | 延误 | M2.4 只做 3 个新增工具 + skill_run 骨架 |

---

## 9. 与原始路线图的偏差

原始 `docs/CogCore-通用认知内核架构设计.md` §10.4 的 M2 里程碑偏向研究性质（多模态传感器、技能包共享协议）。本计划重新校准为更贴近实用的方向：

| 原始里程碑 | 调整说明 |
|-----------|---------|
| M2.1 full_silent 长期稳定 | → M2.1 后台认知服务（full_silent 模式已在 M1.4 实现） |
| M2.2 ap_agency 主动候选 | → M2.2 端到端 Agent（5 步消息流 + 工具执行器） |
| M2.3 reinforced 教师门控 | → M2.3 长程稳定性实验（E18-E20，教师门控已在 M1.4） |
| M2.4 技能包共享协议 | → M2.4 工具箱深化（保留 skill_run 骨架） |
| M2.5 多模态感受器 | 推迟到 M3（依赖硬件接入） |

---

*CogCore M2 规划 v0.1 | 2026-06-05 | 基于 M0+M1 全部完成的状态规划*
