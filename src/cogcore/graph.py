"""CogCoreStateGraph：把 10 阶段 tick 流水线包装为 LangGraph StateGraph。

接口与 docs/CogCore-通用认知内核架构设计.md §5.11（工程主线顺序）完全对齐。

M0.5 实现：
- 10 个 stage 函数 → 10 个 LangGraph 节点
- in-memory MemorySaver 作为默认 checkpointer
- 模块实例通过闭包注入
- 与 M0.1 run_cycle 行为等价，但支持 LangGraph Studio 可视化 + 自动 patch 合并
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from cogcore.state_schema import CogCoreState
import cogcore.pipeline as pipeline

logger = logging.getLogger(__name__)


def build_cogcore_graph(modules: dict[str, Any] | None = None) -> Any:
    """构造 CogCore StateGraph。

    Args:
        modules: 模块实例字典，可包含：
            - pool: StatePool
            - hdb: HDB
            - cfs: CognitiveFeelingSystem
            - attention: Attention
            - nt_sys: NeurotransmitterSystem
            - action_sys: ActionSystem
            - tuner: AdaptiveTuner
            - sensors: SensorLayer（可选）
            - induction: InductionGrowth（可选）
        缺失的模块会被传 None，相关 stage 会通过 _safe_call 处理

    Returns:
        CompiledStateGraph（可调用 .invoke()）
    """
    modules = modules or {}

    # 默认模块（如果没传就建一个空 stub）
    pool = modules.get("pool")
    hdb = modules.get("hdb")
    cfs = modules.get("cfs")
    attention = modules.get("attention")
    nt_sys = modules.get("nt_sys")
    action_sys = modules.get("action_sys")
    tuner = modules.get("tuner")
    sensors = modules.get("sensors")
    induction = modules.get("induction")

    # 构造图
    graph = StateGraph(CogCoreState)

    # 用 lambda 绑定模块到 stage 函数（LangGraph 节点签名：state -> dict）
    graph.add_node("stage_1_sensor_input",
                   lambda s: pipeline.stage_1_sensor_input(s, sensors))
    graph.add_node("stage_2_state_pool_maintenance",
                   lambda s: pipeline.stage_2_state_pool_maintenance(s, pool))
    graph.add_node("stage_3_hdb_lookup",
                   lambda s: pipeline.stage_3_hdb_lookup(s, hdb))
    graph.add_node("stage_4_induction_growth",
                   lambda s: pipeline.stage_4_induction_growth(s, induction))
    graph.add_node("stage_5_cfs_evaluate",
                   lambda s: pipeline.stage_5_cfs_evaluate(s, cfs))
    graph.add_node("stage_6_attention_select",
                   lambda s: pipeline.stage_6_attention_select(s, attention, pool))
    graph.add_node("stage_7_nt_update",
                   lambda s: pipeline.stage_7_nt_update(s, nt_sys))
    graph.add_node("stage_8_action_evaluate_and_execute",
                   lambda s: pipeline.stage_8_action_evaluate_and_execute(s, action_sys, pool))
    graph.add_node("stage_9_episodic_write",
                   lambda s: pipeline.stage_9_episodic_write(s, hdb))
    graph.add_node("stage_10_adaptive_tune",
                   lambda s: pipeline.stage_10_adaptive_tune(s, tuner))

    # 边：START → 1 → 2 → ... → 10 → END
    graph.add_edge(START, "stage_1_sensor_input")
    graph.add_edge("stage_1_sensor_input", "stage_2_state_pool_maintenance")
    graph.add_edge("stage_2_state_pool_maintenance", "stage_3_hdb_lookup")
    graph.add_edge("stage_3_hdb_lookup", "stage_4_induction_growth")
    graph.add_edge("stage_4_induction_growth", "stage_5_cfs_evaluate")
    graph.add_edge("stage_5_cfs_evaluate", "stage_6_attention_select")
    graph.add_edge("stage_6_attention_select", "stage_7_nt_update")
    graph.add_edge("stage_7_nt_update", "stage_8_action_evaluate_and_execute")
    graph.add_edge("stage_8_action_evaluate_and_execute", "stage_9_episodic_write")
    graph.add_edge("stage_9_episodic_write", "stage_10_adaptive_tune")
    graph.add_edge("stage_10_adaptive_tune", END)

    # 编译（in-memory checkpointer 支持多次 invoke 保持 thread state）
    compiled = graph.compile(checkpointer=MemorySaver())
    logger.info("CogCore StateGraph compiled: 10 nodes + MemorySaver")
    return compiled


def invoke_cogcore(
    graph: Any,
    raw_input: str,
    tick: int = 0,
    thread_id: str = "default",
    modality: str = "text",
) -> dict:
    """调用一次 StateGraph，返回最终 state。

    Args:
        graph: build_cogcore_graph() 返回的编译图
        raw_input: 外源输入
        tick: 全局 tick 计数
        thread_id: 会话 ID（LangGraph checkpointer 用）
        modality: 输入模态

    Returns:
        最终 CogCoreState（作为 dict）
    """
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "tick": tick,
        "raw_input": raw_input,
        "modality": modality,
    }
    result = graph.invoke(initial_state, config=config)
    return result
