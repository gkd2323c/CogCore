"""CogCoreStateGraph：把 10 阶段 tick 流水线包装为 LangGraph StateGraph。

M0.5 实现 in-memory MemorySaver。
M1.2 新增 SQLite 持久化路径（零 Docker 依赖）。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.store.sqlite import SqliteStore

    _HAS_SQLITE = True
except ImportError:
    SqliteSaver = None  # type: ignore
    SqliteStore = None  # type: ignore
    _HAS_SQLITE = False

from cogcore.state_schema import CogCoreState
import cogcore.pipeline as pipeline

logger = logging.getLogger(__name__)


# ============================================================
# 内部：图定义（内存和 SQLite 共享）
# ============================================================


def _add_nodes_and_edges(graph: StateGraph, modules: dict[str, Any]) -> None:
    """向 graph 添加 10 个节点和顺序边。"""
    pool = modules.get("pool")
    hdb = modules.get("hdb")
    cfs = modules.get("cfs")
    attention = modules.get("attention")
    nt_sys = modules.get("nt_sys")
    action_sys = modules.get("action_sys")
    tuner = modules.get("tuner")
    sensors = modules.get("sensors")
    induction = modules.get("induction")

    graph.add_node("stage_1_sensor_input", lambda s: pipeline.stage_1_sensor_input(s, sensors))
    graph.add_node("stage_2_state_pool_maintenance", lambda s: pipeline.stage_2_state_pool_maintenance(s, pool))
    graph.add_node("stage_3_hdb_lookup", lambda s: pipeline.stage_3_hdb_lookup(s, hdb))
    graph.add_node("stage_4_induction_growth", lambda s: pipeline.stage_4_induction_growth(s, induction))
    graph.add_node("stage_5_cfs_evaluate", lambda s: pipeline.stage_5_cfs_evaluate(s, cfs))
    graph.add_node("stage_6_attention_select", lambda s: pipeline.stage_6_attention_select(s, attention, pool))
    graph.add_node("stage_7_nt_update", lambda s: pipeline.stage_7_nt_update(s, nt_sys))
    graph.add_node("stage_8_action_evaluate_and_execute", lambda s: pipeline.stage_8_action_evaluate_and_execute(s, action_sys, pool))
    graph.add_node("stage_9_episodic_write", lambda s: pipeline.stage_9_episodic_write(s, hdb))
    graph.add_node("stage_10_adaptive_tune", lambda s: pipeline.stage_10_adaptive_tune(s, tuner))

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


# ============================================================
# 路径 A：内存（默认，零依赖）
# ============================================================


def build_cogcore_graph(modules: dict[str, Any] | None = None) -> Any:
    """构造 CogCore StateGraph（in-memory MemorySaver）。

    默认路径，适用于开发、测试和单会话场景。
    """
    modules = modules or {}
    graph = StateGraph(CogCoreState)
    _add_nodes_and_edges(graph, modules)
    compiled = graph.compile(checkpointer=MemorySaver())
    logger.info("CogCore StateGraph compiled: 10 nodes + MemorySaver")
    return compiled


# ============================================================
# 路径 B：SQLite 持久化（M1.2，零 Docker）
# ============================================================


def build_cogcore_graph_persistent(
    modules: dict[str, Any] | None = None,
    sqlite_path: str = "cogcore_state.db",
) -> Any:
    """构造 CogCore StateGraph（SQLite 持久化）。

    使用 SqliteSaver + SqliteStore 替代 MemorySaver。
    不需要 Docker / PostgreSQL——Python 内置 sqlite3 即可。

    Args:
        modules: 模块实例字典
        sqlite_path: SQLite 数据库文件路径
    """
    if not _HAS_SQLITE:
        raise ImportError(
            "langgraph-checkpoint-sqlite 未安装。运行: pip install langgraph-checkpoint-sqlite"
        )

    modules = modules or {}
    graph = StateGraph(CogCoreState)
    _add_nodes_and_edges(graph, modules)

    conn = sqlite3.connect(sqlite_path, check_same_thread=False)

    # 自定义 serializer：预注册 CogCore 自定义类型，避免 msgpack 反序列化警告。
    # 直接传 allowed_msgpack_modules 到构造函数（with_msgpack_allowlist 在默认
    # permissive 模式下是 no-op）。
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from cogcore.types import (
        StimulusAtom,
        StimulusSource,
        Modality,
        FeelingType,
    )
    from cogcore.cfs import FeelingSignal
    from cogcore.attention import CurrentAttentionMemory
    from cogcore.nt import NTModulations
    from cogcore.state_schema import StatePoolSnapshot, HDBSnapshot

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            (cls.__module__, cls.__name__)
            for cls in (
                StatePoolSnapshot,
                HDBSnapshot,
                NTModulations,
                StimulusSource,
                Modality,
                CurrentAttentionMemory,
                StimulusAtom,
                FeelingType,
                FeelingSignal,
            )
        ]
    )

    checkpointer = SqliteSaver(conn, serde=serde)
    store = SqliteStore(conn)

    compiled = graph.compile(checkpointer=checkpointer, store=store)
    logger.info(f"CogCore StateGraph compiled with SQLite: {sqlite_path}")
    return compiled


# ============================================================
# 便捷调用
# ============================================================


def invoke_cogcore(
    graph: Any,
    raw_input: str,
    tick: int = 0,
    thread_id: str = "default",
    modality: str = "text",
) -> dict:
    """调用一次 StateGraph，返回最终 state。"""
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "tick": tick,
        "raw_input": raw_input,
        "modality": modality,
    }
    result = graph.invoke(initial_state, config=config)
    return result
