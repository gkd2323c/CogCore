# CogCore

**通用认知内核（Universal Cognitive Kernel）—— LLM Agent 的持续认知层**

[![阶段](https://img.shields.io/badge/stage-M3-green)]() [![测试](https://img.shields.io/badge/tests-374%20passed-brightgreen)]() [![模块](https://img.shields.io/badge/modules-30-blue)]() [![论文](https://img.shields.io/badge/based%20on-AP%20(2026)-blue)]()

---

## 一句话定位

CogCore 补 LLM 在长期连续性上的结构性缺失：长期状态维护、可解释记忆、内源感受调制、行动反馈学习。它不替代 LLM，而是在 LLM 下面加一层"持续认知的运行时"。

> 基于论文《人工心智架构》（Artificial PsyArch, AP，2026）的工程化重写。

## 当前状态

| 项 | 状态 |
|---|---|
| 设计文档 | ✅ 完成（9 章 + 5 个新章节 + 附录 A）|
| 验证矩阵 | ✅ 完成（17 实验 × CogCore 模块映射）|
| 论文选型 | ✅ 完成（LangGraph 首选，PydanticAI 次选）|
| 代码实现 | ✅ M3.5 阶段完成 (FastAPI + LLM fallback + MCP + 错误处理 + 代码感知工具), 374/374 测试通过 |
| E01-E17 复现 | ✅ **17/17 全部通过**, CogCore 实验已覆盖全部论文实验 |
| E18-E20 实验 | ✅ 3000 tick 稳定 + APT 消融 + CFS/NT 消融全部通过 |
| L1 应用层 | ✅ FastAPI 接入 (5 端点, 真实 DeepSeek 跑通) |
| L4 解释层 | ✅ LLMRegistry + circular fallback (14 测试 + 实跑) |
| L5 工具层 | ✅ MCP 适配器 (15 测试) + 6 默认工具 + 3 long-term + 13 code/git/exec |
| L10 错误处理 | ✅ 三层 (L1 retry + L2 fallback + L3 教师门控, 20 测试) |
| L12 自迭代 | ⏳ M3.5 完成 L12.1 (自检) + L12.2 (自改), 缺 M3.6 元循环 |
| 后台服务 | ✅ CogCoreService 持续 tick + 自动日记 + SQLite 持久化 |
| LLM 集成 | ✅ OpenAI 兼容协议 + Ollama 本地 + end-to-end Agent |
| 持久化 | ✅ SQLite（零 Docker）/ Memory 双路径 |
| 工具系统 | ✅ ToolRegistry + 日记/任务/计算/技能 6 工具 |
| 运行模式 | ✅ full_silent / ap_agency / reinforced_agency 三种 |

> **诚实声明**：所有实验已在 CogCore 上运行并通过验证。部分实验值因实现差异与论文数值不完全重合，但实验设计和判据均对齐论文 3.14 节。完整数据见 `experiments/E01-E17/`。

## 文档导航

| 文档 | 给谁看 | 内容 |
|------|-------|------|
| **[PURPOSE.MD](./PURPOSE.MD)** | 任何人 | 为什么做、解决什么问题、目标、边界、成功标准 |
| **[DESIGN.MD](./DESIGN.MD)** | 架构师/工程师 | 高层架构、四大原则、关键决策、与论文关系 |
| **[AGENT_BUILD.MD](./AGENT_BUILD.MD)** | 想做完整智能体的人 | 4 个参考项目能力地图、11 层能力栈、技术栈、4 阶段实施路线 |
| **[AGENTS.md](./AGENTS.md)** | AI Agent | 项目结构、常用操作、避坑、当前任务 |
| **[docs/CogCore-通用认知内核架构设计.md](./docs/CogCore-通用认知内核架构设计.md)** | 工程师 | 模块设计、接口契约、配置参数、tick 流水线、PA 双层结构、发展路线图（~52KB）|
| **[docs/CogCore-验证矩阵.md](./docs/CogCore-验证矩阵.md)** | 验证者 | 17 项实验、方法学、准入规则、与 CogCore 模块映射 |
| **[docs/cogcore_framework_research.md](./docs/cogcore_framework_research.md)** | 选型者 | LangGraph vs PydanticAI vs OpenAI SDK 等深度对比 |
| **[docs/人工心智架构-论文分析.md](./docs/人工心智架构-论文分析.md)** | 研究者 | AP 论文 113 页的批判性分析 |

## 快速开始

### 我想了解项目做什么

1. 读 [PURPOSE.MD](./PURPOSE.MD)（5 分钟）
2. 读 [DESIGN.MD](./DESIGN.MD)（10 分钟）

### 我想了解架构细节

1. [docs/CogCore-通用认知内核架构设计.md](./docs/CogCore-通用认知内核架构设计.md) 第 1-4 章
2. [docs/cogcore_framework_research.md](./docs/cogcore_framework_research.md)

### 我想复现某个实验

1. 读 [docs/CogCore-验证矩阵.md](./docs/CogCore-验证矩阵.md) 第 0 节方法学
2. 找到目标实验（如 E01），看 `experiments/E01/` 目录
3. 按论文附件仓库 `Artificial-PsyArch-test/experiments/E01` 的同款 design.md / report.md 复现

### 我想参与实现

1. 读 [DESIGN.MD](./DESIGN.MD) 第 3 节关键决策
2. 读 [AGENTS.md](./AGENTS.md) 当前任务
3. 挑一个 M0.x 里程碑开始

## 论文引用

本项目基于以下论文的工程化重写：

```
银子. 人工心智架构：一种面向拟人持续认知闭环的可复现实验原型与工程范式
   [Artificial PsyArch: A Reproducible Prototype and Engineering Paradigm
    for Human-Like Continuous Cognitive Loops]. 2026 年 5 月, 113 页.
```

公开复现附件：
- 原型仓库：https://github.com/ginsonko/Artificial-PsyArch/
- 论文实验附件：https://github.com/ginsonko/Artificial-PsyArch-test-
- PA 双层结构：https://github.com/ginsonko/PsyArch-Agent

## 仓库结构

```
CogCore/
├── PURPOSE.MD                       # 需求文档（5 分钟可读）
├── DESIGN.MD                        # 设计文档（10 分钟可读）
├── AGENTS.md                        # AI Agent 操作手册
├── AGENT_BUILD.MD                   # 从内核到完整 Agent 的桥梁
├── README.md                        # 本文件
├── docs/
│   ├── CogCore-通用认知内核架构设计.md  # 完整架构设计（~52KB）
│   ├── CogCore-验证矩阵.md            # E01-E17 + 准入规则
│   ├── cogcore_framework_research.md  # LangGraph 选型调研
│   └── 人工心智架构-论文分析.md         # AP 论文批判性分析
├── paper/                           # AP 论文原文
├── src/cogcore/                     # 22 个 Python 模块
│   ├── types.py                     # 核心类型（StimulusAtom 等）
│   ├── state_schema.py              # CogCoreState + StateUpdater
│   ├── config.py                    # TOML 配置加载（M1.1）
│   ├── pipeline.py                  # 10 阶段 tick 流水线
│   ├── state_pool.py                # 状态池（M0.2）
│   ├── hdb.py                       # HDB 查存一体（M0.2）
│   ├── induction.py                 # 感应生长
│   ├── sensors.py                   # 感受器（M0.2 TextSensor）
│   ├── cfs.py                       # 认知感受系统（M0.4）
│   ├── nt.py                        # 情绪递质（M0.4）
│   ├── attention.py                 # 注意力（M0.4）
│   ├── adaptive_tuner.py            # 自适应调参器（M0.4）
│   ├── action_system.py             # 行动系统（M0.3）
│   ├── graph.py                     # LangGraph StateGraph（M0.5 + M1.2 SQLite）
│   ├── modes.py                     # PA 运行模式（M1.4）
│   ├── llm_bridge.py                # LLM 桥接 OpenAI SDK（M1.1）
│   ├── tools.py                     # 工具系统（M1.3）
│   ├── run.py                       # CLI 入口（M0.5）
│   ├── main.py                      # M0.1 手动入口
│   └── observability.py             # 可观测性
├── tests/                           # 17 个测试文件 / 228 个测试
│   ├── test_pipeline.py             # 5
│   ├── test_state_pool.py           # 15
│   ├── test_hdb.py                  # 16
│   ├── test_state_schema.py         # 15
│   ├── test_integration.py          # 9
│   ├── test_action_system.py        # 23
│   ├── test_cfs.py                  # 10 (M0.4)
│   ├── test_nt.py                   # 13 (M0.4)
│   ├── test_attention.py            # 9 (M0.4)
│   ├── test_tuner.py                # 12 (M0.4)
│   ├── test_graph.py                # 11 (M0.5)
│   ├── test_config.py               # 12 (M1.1)
│   ├── test_llm_bridge.py           # 16 (M1.1)
│   ├── test_persistence.py          # 7 (M1.2)
│   ├── test_tools.py                # 17 (M1.3)
│   └── test_modes.py                # 12 (M1.4)
├── scripts/                         # 5 个演示脚本
│   ├── demo_run.py                  # M0.1 手动流水线
│   ├── demo_action.py               # M0.3 行动系统
│   ├── demo_modulation.py           # M0.4 调制层
│   ├── demo_langgraph.py            # M0.5 LangGraph
│   └── demo_llm.py                  # M1.1 CogCore→LLM 闭环
├── config.toml                      # 本地配置（.gitignore）
├── config.toml.example              # 配置模板
```

## 许可与贡献

- 论文 AP 的公开复现附件遵循其仓库的许可证
- CogCore 自身代码许可待定（M0 完成时确定）
- 实验数据归档规范见 `docs/CogCore-验证矩阵.md` 第 5 节

---

*本 README 与 4 份门面文档同步于 2026-06-05 CogCore 第 1-3 轮文档补全后。*
