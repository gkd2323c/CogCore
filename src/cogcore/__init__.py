"""CogCore 通用认知内核。

基于论文《人工心智架构》（Artificial PsyArch, AP, 2026）的工程化重写。

模块：
    types             基础数据类型（5 个核心数据结构）
    state_pool        状态池
    hdb               全息深度数据库
    induction         感应生长
    attention         注意力与 CAM
    nt                情绪递质
    cfs               认知感受
    action_system     行动系统 + 教师反馈延迟合流
    adaptive_tuner    自适应调参器
    sensors           感受器层
    llm_bridge        LLM 桥接
    tools             工具链
    observability     白箱观测台
    pipeline          10 阶段 tick 流水线

当前阶段：M0.1（骨架）。所有模块内部方法 raise NotImplementedError，
仅 pipeline.run_cycle 调度逻辑完整跑通。

详细接口与设计见 docs/ 下的文档。
"""

__version__ = "0.1.0"
__stage__ = "M0.1-skeleton"
