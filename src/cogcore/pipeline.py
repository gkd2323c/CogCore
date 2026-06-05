"""认知滴答（Cognitive Tick）流水线：10 阶段调度。

与 docs/CogCore-通用认知内核架构设计.md §5（10 阶段）+ §5.11（工程主线顺序）+ §5.13（追踪样例）完全对齐。

**M0.1 设计原则：节点返回 State Patch 而非修改全局 + 避免 Fluent API 双重累加**

每个 `stage_N_*` 函数都是 LangGraph 节点。节点函数返回 `dict[str, Any]`，
作为对 `CogCoreState` 的**部分更新（patch）**。这是 LangGraph 的核心契约。

⚠️ **三个状态合并陷阱**（见 `state_schema.py` 顶部文档）：

T1. 嵌套字段（如 `nt_values`, `cam`, `pool_snapshot`）必须返回**整个新对象**
    —— 不能返回部分 dict，否则其他子字段被默认合并清空。

T5. Fluent API 双重累加：返回完整 State 实例会触发 Reducer 双重累加。
    `state.append_atoms([B])` 内部已做 `[A] + [B] = [A, B]`，返回后 Reducer
    再次拼接 → `[A] + [A, B] = [A, A, B]`  💥
    修复：用 `StateUpdater` 累积 patch dict（不预累加），最后 `.to_patch()` 返回。

T2/T3/T4. 跨节点全局修改 / 返回完整 state / 字段拼写错误 —— 见 `state_schema.py`。

`_safe_call` 捕获 NotImplementedError 转为日志，让 M0.1 骨架能跑通 10 阶段；
M0.5 把 `run_cycle` 改成 `StateGraph(CogCoreState).compile()` 即可。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from cogcore.action_system import ActionSystem
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention, CurrentAttentionMemory
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.hdb import HDB
from cogcore.induction import InductionGrowth
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool
from cogcore.state_schema import (
    HDBSnapshot,
    StatePoolSnapshot,
    CogCoreState,
    make_updater,
)
from cogcore.types import Outcome, StimulusAtom

logger = logging.getLogger(__name__)


# ============================================================
# Tick 报告（白箱可审计）
# ============================================================


@dataclass
class TickReportDC:
    """一轮 tick 的完整报告（与 CogCoreState.stages_log 互补）。"""

    tick: int = 0
    timestamp: float = 0.0
    stages_completed: list[str] = field(default_factory=list)
    stages_pending: list[str] = field(default_factory=list)
    error_log: list[str] = field(default_factory=list)


# ============================================================
# _safe_call：让 M0.1 骨架不崩
# ============================================================


def _safe_call(stage_name: str, fn, *args, **kwargs):
    """调用一个 stage，捕获 NotImplementedError 转为日志。

    如果 fn 是 None（模块未注入），返回 None 而不报错。
    """
    if fn is None:
        logger.info(f"[{stage_name}] 模块未注入（None）")
        return None
    try:
        result = fn(*args, **kwargs)
        return result
    except NotImplementedError as e:
        logger.info(f"[{stage_name}] {e}")
        return None
    except Exception as e:
        logger.exception(f"[{stage_name}] unexpected error: {e}")
        raise


# ============================================================
# 10 个 Stage 函数（LangGraph 节点接口）
#
# 签名约定：每个 stage 接受 state: CogCoreState 和必要的模块实例，
# 返回 dict[str, Any] 作为对 state 的部分更新（patch）。
#
# 关键：使用 StateUpdater 链式（make_updater）让代码优雅，同时返回 dict
# 避免陷阱 T5（双重累加）。
# ============================================================


def stage_1_sensor_input(
    state: CogCoreState,
    sensors=None,  # SensorLayer 实例
) -> dict:
    """阶段 1：外源输入接收。"""
    from cogcore.sensors import SensorLayer

    if sensors is None:
        sensors = SensorLayer()

    new_atoms = sensors.ingest(
        state.raw_input,
        state.modality,
        {},
        state.tick,
    )

    return (
        make_updater(state)
        .append_atoms(new_atoms)
        .append_stage("stage_1_sensor_input")
        .to_patch()
    )


def stage_2_state_pool_maintenance(
    state: CogCoreState,
    pool: StatePool,
) -> dict:
    """阶段 2：状态池维护（衰减 → 注入 → 清理）。"""
    # 衰减
    _safe_call("stage_2", pool.decay)
    # 注入新原子
    for atom in state.new_atoms:
        _safe_call("stage_2", pool.add, atom)
    # 清理
    _safe_call("stage_2", pool.cleanup, min_energy=0.01, max_age=200)

    # patch：更新 pool_snapshot
    energy_summary = _safe_call("stage_2", pool.get_energy_summary)
    active_atoms = _safe_call("stage_2", pool.get_all) or []

    updater = make_updater(state).append_stage("stage_2_state_pool_maintenance")

    if energy_summary is not None:
        updater = updater.patch_pool_snapshot(
            energy_summary=energy_summary,
            active_atom_ids=[str(a.id) for a in active_atoms],
        )

    return updater.to_patch()


def stage_3_hdb_lookup(
    state: CogCoreState,
    hdb: HDB,
) -> dict:
    """阶段 3：查存一体（HDB.lookup）。"""
    result = _safe_call("stage_3", hdb.lookup, state.new_atoms)

    updater = make_updater(state).append_stage("stage_3_hdb_lookup")

    if result is not None:
        matched_ids = [str(s.id) for s in result.matched_structures]
        new_ids = [str(s.id) for s in result.new_structures]
        # match_scores 的 key 必须是 str（CogCoreState 设计为可 JSON 序列化）
        scores_str = {str(k): float(v) for k, v in result.match_scores.items()}

        updater = updater.patch_hdb_snapshot(
            matched_structure_ids=matched_ids,
            match_scores=scores_str,
            new_structure_ids=new_ids,
            residual_count=len(result.residuals),
        )

    return updater.to_patch()


def stage_4_induction_growth(
    state: CogCoreState,
    induction: InductionGrowth,
) -> dict:
    """阶段 4：感应生长（沿 HDB 局部结构展开预测）。"""
    grown = []
    if induction is not None:
        grown = _safe_call("stage_4", induction.expand, state.new_atoms) or []

    return (
        make_updater(state)
        .append_grown(grown)
        .append_stage("stage_4_induction_growth")
        .to_patch()
    )


def _get_previous_reward(state: CogCoreState) -> dict:
    """从 state 提取最近一条行动原子（如果有）的 reward_signal。"""
    for atom in reversed(state.new_atoms):
        if atom.source.value == "action":
            return {"reward_signal": atom.energy.real - atom.energy.virtual}
    return {}


def stage_5_cfs_evaluate(
    state: CogCoreState,
    cfs: CognitiveFeelingSystem,
) -> dict:
    """阶段 5：认知感受评估。"""
    cfs.set_tick(state.tick)
    cfs.set_recent_execution_count(0)  # M0.4 简版：默认 0

    pool_summary = {
        "cognitive_pressure": state.pool_snapshot.energy_summary.cognitive_pressure,
        "active_count": state.pool_snapshot.energy_summary.active_count,
    }
    hdb_dict = state.hdb_snapshot.model_dump() if state.hdb_snapshot else {}
    prev_feedback = _get_previous_reward(state)

    signals = cfs.evaluate(
        pool_energy_summary=pool_summary,
        hdb_result=hdb_dict,
        previous_feedback=prev_feedback,
    )

    feeling_atoms = cfs.to_stimulus_atoms(signals)

    return (
        make_updater(state)
        .append_feelings(signals)
        .append_atoms(feeling_atoms)
        .append_stage("stage_5_cfs_evaluate")
        .to_patch()
    )


def stage_6_attention_select(
    state: CogCoreState,
    attention: Attention,
    pool: StatePool,
) -> dict:
    """阶段 6：注意力选择（CAM）。"""
    cam = attention.select(pool)

    return (
        make_updater(state)
        .set_cam(cam)
        .append_stage("stage_6_attention_select")
        .to_patch()
    )


def stage_7_nt_update(
    state: CogCoreState,
    nt_sys: NeurotransmitterSystem,
) -> dict:
    """阶段 7：情绪递质更新（按惯性规则）。"""
    nt_sys.set_tick(state.tick)

    feeling_dicts = [s.model_dump() for s in state.feeling_signals]
    rewards = []
    for atom in state.new_atoms:
        if atom.source.value == "action":
            rewards.append(atom.energy.real - atom.energy.virtual)

    nt_sys.update(
        feeling_signals=feeling_dicts,
        reward_signals=rewards,
        rules={},
    )

    # 整体替换（修复陷阱 T1）
    return (
        make_updater(state)
        .patch_nt_values(
            focus=nt_sys.current.focus,
            arousal=nt_sys.current.arousal,
            caution=nt_sys.current.caution,
            exploration=nt_sys.current.exploration,
            fatigue=nt_sys.current.fatigue,
            stability=nt_sys.current.stability,
        )
        .append_stage("stage_7_nt_update")
        .to_patch()
    )


def stage_8_action_evaluate_and_execute(
    state: CogCoreState,
    action_sys: ActionSystem,
    pool: StatePool,
) -> dict:
    """阶段 8：行动评估与执行。

    论文 §4.8：驱动力计算、阈值调制、执行第一个候选。
    M0.3 简版：评估候选，如果触发则执行第一个，把结果包装为 StimulusAtom 注入 new_atoms。
    """
    # 同步 tick（保证驱动力时间衰减正确）
    action_sys.set_tick(state.tick)

    candidates = action_sys.evaluate_drives(pool, state.nt_values)

    if not candidates:
        return make_updater(state).append_stage("stage_8_action_evaluate_and_execute").to_patch()

    # 执行第一个候选（论文：按 drive 降序选）
    top = candidates[0]
    result = action_sys.execute(top)

    # 处理反馈（写入节点 history）
    action_sys.process_feedback(result, target_node=top.node)

    # 包装为 StimulusAtom 注入状态池（供后续 stage 查存/感受）
    action_atom = action_sys.to_stimulus_atom(result, top.node)

    # 同步行动节点当前的 drive 到 state.nt_values（通过 patch_nt_values）
    updater = make_updater(state).append_stage("stage_8_action_evaluate_and_execute")

    # 把行动 atom 注入 new_atoms
    updater = updater.append_atoms([action_atom])

    return updater.to_patch()


def stage_9_episodic_write(
    state: CogCoreState,
    hdb: HDB,
) -> dict:
    """阶段 9：情景记忆写入。

    论文 §4.4：把本轮经历打包为 EpisodicMemory 写入 HDB。
    M0.3 简版：记录本轮的 actions + 关联 structures。
    """
    from cogcore.types import EpisodicMemory

    # 收集本轮的行动原子（new_atoms 中 source=ACTION 的）
    action_atoms = [
        a for a in state.new_atoms
        if a.source.value == "action"
    ]

    # 收集本轮命中的 HDB 结构
    structure_refs = [
        # 我们没有从 HDBSnapshot 取回 UUID 类型的 ID（快照里是 str）
        # 在实际 LangGraph 实现中，这里应该用真正的 UUID
        a for a in [None]  # placeholder
    ]

    # tick_range
    tick_start = state.tick
    tick_end = state.tick

    mem = EpisodicMemory(
        tick_range=(tick_start, tick_end),
        action_taken=f"executed {len(action_atoms)} actions",
        outcome=Outcome.SUCCESS if action_atoms else Outcome.SUCCESS,
        stimuli_snapshot=[a.id for a in state.new_atoms],
    )
    hdb.write_episodic(mem)

    return make_updater(state).append_stage("stage_9_episodic_write").to_patch()


def stage_10_adaptive_tune(
    state: CogCoreState,
    tuner: AdaptiveTuner,
) -> dict:
    """阶段 10：自适应调参。"""
    # 构造 attention_stats
    cam_variance = 0.5  # 简化：用固定值
    if state.cam and state.cam.items:
        energies = [a.energy.total for a in state.cam.items]
        if len(energies) > 1:
            mean = sum(energies) / len(energies)
            cam_variance = sum((e - mean) ** 2 for e in energies) / len(energies)
    attention_stats = {
        "cam_energy_variance": cam_variance,
        "induction_nodes": 10,  # 简版
    }

    adjustments = tuner.assess(
        state.pool_snapshot.energy_summary,
        state.nt_values,
        attention_stats,
    )
    tuner.apply(adjustments)

    return make_updater(state).append_stage("stage_10_adaptive_tune").to_patch()


# ============================================================
# 总入口：run_cycle（M0.1 手动版）
# ============================================================


# 累加器字段（add reducer 由 StateUpdater.patch 保证不预累加）
_ADDITIVE_FIELDS = {
    "new_atoms",
    "grown_atoms",
    "feeling_signals",
    "stages_log",
    "error_log",
}


def _apply_patch(state: CogCoreState, patch: dict) -> None:
    """手动模拟 LangGraph Reducer 合并（M0.1 用，M0.5 由 StateGraph 接管）。

    - 累加器字段：拼接（add reducer 行为）
    - 其他字段：替换
    """
    for key, value in patch.items():
        if key in _ADDITIVE_FIELDS:
            current = getattr(state, key, [])
            setattr(state, key, current + value)
        else:
            setattr(state, key, value)


def run_cycle(
    raw_input: Any,
    modality: str = "text",
    tick: int = 0,
    pool: StatePool | None = None,
    hdb: HDB | None = None,
    induction: InductionGrowth | None = None,
    attention: Attention | None = None,
    cfs: CognitiveFeelingSystem | None = None,
    nt_sys: NeurotransmitterSystem | None = None,
    action_sys: ActionSystem | None = None,
    tuner: AdaptiveTuner | None = None,
) -> TickReportDC:
    """一轮认知滴答的完整主循环（M0.1 手动版）。

    **M0.5 迁移路径**：
        graph = StateGraph(CogCoreState)
        graph.add_node("perceive", stage_1_sensor_input)
        ...
        cogcore = graph.compile(checkpointer=..., store=...)
        result = cogcore.invoke({"raw_input": "..."})

    每个 stage 节点返回 patch dict，run_cycle 累积到 CogCoreState。
    """
    # 实例化默认
    pool = pool or StatePool()
    hdb = hdb or HDB()
    induction = induction or InductionGrowth(hdb)
    attention = attention or Attention()
    cfs = cfs or CognitiveFeelingSystem()
    nt_sys = nt_sys or NeurotransmitterSystem()
    action_sys = action_sys or ActionSystem()
    tuner = tuner or AdaptiveTuner()

    # 初始化 state
    state = CogCoreState(
        tick=tick,
        raw_input=str(raw_input) if raw_input is not None else "",
        modality=modality,
    )

    report = TickReportDC(tick=tick, timestamp=time.time())
    stage_names = [
        "stage_1_sensor_input",
        "stage_2_state_pool_maintenance",
        "stage_3_hdb_lookup",
        "stage_4_induction_growth",
        "stage_5_cfs_evaluate",
        "stage_6_attention_select",
        "stage_7_nt_update",
        "stage_8_action_evaluate_and_execute",
        "stage_9_episodic_write",
        "stage_10_adaptive_tune",
    ]

    logger.info(f"=== run_cycle tick={tick} ===")

    # 10 个 stage：每个返回 patch dict（StateUpdater.to_patch() 风格）
    stage_fns = [
        lambda s: stage_1_sensor_input(s, None),
        lambda s: stage_2_state_pool_maintenance(s, pool),
        lambda s: stage_3_hdb_lookup(s, hdb),
        lambda s: stage_4_induction_growth(s, induction),
        lambda s: stage_5_cfs_evaluate(s, cfs),
        lambda s: stage_6_attention_select(s, attention, pool),
        lambda s: stage_7_nt_update(s, nt_sys),
        lambda s: stage_8_action_evaluate_and_execute(s, action_sys, pool),
        lambda s: stage_9_episodic_write(s, hdb),
        lambda s: stage_10_adaptive_tune(s, tuner),
    ]

    for i, (name, fn) in enumerate(zip(stage_names, stage_fns)):
        try:
            patch = fn(state)
            if patch:
                _apply_patch(state, patch)
            report.stages_completed.append(name)
        except Exception as e:
            logger.exception(f"[{name}] failed: {e}")
            report.error_log.append(f"{name}: {e}")

    logger.info(
        f"=== run_cycle tick={tick} 完成：{len(report.stages_completed)}/10 阶段 ==="
    )
    return report
