"""ActionSystem 烟雾测试（M0.3）。

覆盖：register_node/evaluate_drives/execute/process_feedback/
queue_teacher_feedback/merge_pending_teacher_feedback/get_action_report。
"""

from __future__ import annotations

import logging

import pytest

from cogcore.action_system import (
    ActionCandidate,
    ActionResult,
    ActionSystem,
    TeacherFeedback,
)
from cogcore.nt import NTModulations
from cogcore.state_pool import StatePool
from cogcore.types import ActionNode, ActionSource, Outcome

logging.basicConfig(level=logging.WARNING)


def _make_node(
    name: str = "test_action",
    threshold: float = 1.0,
    base_source: ActionSource = ActionSource.INNATE,
) -> ActionNode:
    return ActionNode(
        name=name,
        threshold=threshold,
        source=base_source,
    )


# ============================================================
# 注册与基础状态
# ============================================================


def test_register_node():
    sys = ActionSystem()
    n = _make_node()
    sys.register_node(n)
    assert sys.get_node(n.id) is n
    assert len(sys._nodes) == 1


def test_register_multiple_nodes():
    sys = ActionSystem()
    n1 = _make_node("a")
    n2 = _make_node("b")
    sys.register_node(n1)
    sys.register_node(n2)
    assert len(sys._nodes) == 2


# ============================================================
# evaluate_drives
# ============================================================


def test_evaluate_drives_no_nodes():
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()
    assert sys.evaluate_drives(pool, nt) == []


def test_evaluate_drives_innate_node_passes_threshold():
    """先天节点基础 drive=1.0 > 默认 threshold=1.0 应该触发。"""
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()
    n = _make_node(threshold=0.5)
    sys.register_node(n)

    candidates = sys.evaluate_drives(pool, nt)
    assert len(candidates) == 1
    assert candidates[0].node.id == n.id
    assert candidates[0].final_drive > 0.5


def test_evaluate_drives_learned_node_lower_base():
    """后天习得节点基础 drive=0.5 < threshold=1.0 不应该触发。"""
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()
    n = _make_node(threshold=1.0, base_source=ActionSource.LEARNED)
    sys.register_node(n)

    candidates = sys.evaluate_drives(pool, nt)
    assert len(candidates) == 0


def test_evaluate_drives_nt_caution_modulates_threshold():
    """NT.caution 应该提高 threshold。"""
    sys = ActionSystem()
    pool = StatePool()
    nt_default = NTModulations()
    nt_cautious = NTModulations(caution=1.0)  # 翻倍 threshold

    n = _make_node(threshold=0.6)
    sys.register_node(n)

    # 默认下：drive ≈ 1.0 + 0 = 1.0 > 0.6 * (1 + 0) = 0.6 → 触发
    default_cands = sys.evaluate_drives(pool, nt_default)
    assert len(default_cands) == 1

    # cautious 下：drive ≈ 1.0 > 0.6 * (1 + 1.0) = 1.2 → 不触发
    cautious_cands = sys.evaluate_drives(pool, nt_cautious)
    assert len(cautious_cands) == 0


def test_evaluate_drives_nt_arousal_boosts_drive():
    """NT.arousal 应该提升 drive（让行动更易触发）。"""
    sys = ActionSystem()
    pool = StatePool()
    nt_calm = NTModulations()
    nt_aroused = NTModulations(arousal=1.0)  # +0.3 drive

    n = _make_node(threshold=1.25)  # 较高阈值
    sys.register_node(n)

    # calm: drive ≈ 1.0 + 0 = 1.0 < 1.25 → 不触发
    calm_cands = sys.evaluate_drives(pool, nt_calm)
    assert len(calm_cands) == 0

    # aroused: drive ≈ 1.0 + 0.3 = 1.3 > 1.25 → 触发
    aroused_cands = sys.evaluate_drives(pool, nt_aroused)
    assert len(aroused_cands) == 1


def test_evaluate_drives_learned_drive_from_rewards():
    """历史奖励应该提升 learned_drive。"""
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()

    n = _make_node(name="learnable", threshold=2.0, base_source=ActionSource.LEARNED)
    n.reward_history = [0.5, 0.5, 0.5]  # 累计 +1.5
    n.last_executed_tick = 0
    sys.set_tick(1)  # 1 tick 后评估
    sys.register_node(n)

    candidates = sys.evaluate_drives(pool, nt)
    # base(0.5) + learned(≈1.5 * 0.95) + contextual(0) - fatigue(0) ≈ 1.93
    # threshold(2.0) * 1 = 2.0
    # 应该不触发（接近但不超）
    assert len(candidates) == 0

    # 给更多奖励
    n.reward_history = [1.0, 1.0, 1.0]  # 累计 +3.0
    candidates = sys.evaluate_drives(pool, nt)
    # base(0.5) + learned(≈2.85) ≈ 3.35 > 2.0 → 触发
    assert len(candidates) == 1


def test_evaluate_drives_punishment_reduces_drive():
    """历史惩罚应该减少 learned_drive。"""
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()

    n = _make_node(threshold=0.6, base_source=ActionSource.LEARNED)
    n.punishment_history = [1.0, 1.0, 1.0]  # 累计 -3.0
    n.last_executed_tick = 0
    sys.set_tick(1)
    sys.register_node(n)

    candidates = sys.evaluate_drives(pool, nt)
    # base(0.5) + learned(≈-2.85) ≈ -2.35 < 0.6 → 不触发
    assert len(candidates) == 0


def test_evaluate_drives_sorted_by_drive():
    """candidates 应该按 final_drive 降序排列。"""
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations(arousal=1.0)  # +0.3 drive

    n1 = _make_node("low", threshold=0.5)
    n2 = _make_node("high", threshold=0.5)
    n2.reward_history = [1.0, 1.0]  # 高 drive
    n2.last_executed_tick = 0

    sys.set_tick(1)
    sys.register_node(n1)
    sys.register_node(n2)

    candidates = sys.evaluate_drives(pool, nt)
    assert len(candidates) == 2
    assert candidates[0].final_drive >= candidates[1].final_drive
    # n2 应该有更高 drive
    assert candidates[0].node.name == "high"


# ============================================================
# execute
# ============================================================


def test_execute_calls_executor():
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()

    n = _make_node()
    sys.register_node(n)
    sys.set_tick(0)

    # 自定义 executor
    def my_executor(node):
        return ActionResult(
            outcome=Outcome.SUCCESS,
            reward_signal=0.8,
            feedback_text=f"ran {node.name}",
        )

    candidates = sys.evaluate_drives(pool, nt)
    assert len(candidates) == 1

    result = sys.execute(candidates[0], executor=my_executor)
    assert result.outcome == Outcome.SUCCESS
    assert result.reward_signal == 0.8


def test_execute_updates_node_state():
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()

    n = _make_node()
    sys.register_node(n)
    sys.set_tick(5)

    def my_executor(node):
        return ActionResult(outcome=Outcome.SUCCESS, reward_signal=0.0)

    candidates = sys.evaluate_drives(pool, nt)
    sys.execute(candidates[0], executor=my_executor)

    assert n.execution_count == 1
    assert n.last_executed_tick == 5


def test_execute_without_executor_returns_error():
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()

    n = _make_node()
    sys.register_node(n)

    candidates = sys.evaluate_drives(pool, nt)
    result = sys.execute(candidates[0])  # 无 executor

    assert result.outcome == Outcome.ERROR


# ============================================================
# process_feedback
# ============================================================


def test_process_feedback_writes_reward_history():
    sys = ActionSystem()
    n = _make_node()
    sys.register_node(n)

    result = ActionResult(outcome=Outcome.SUCCESS, reward_signal=0.3)
    sys.process_feedback(result, target_node=n)

    assert n.reward_history == [0.3]


def test_process_feedback_significant_reward_announces():
    sys = ActionSystem()
    n = _make_node()
    sys.register_node(n)

    result = ActionResult(outcome=Outcome.SUCCESS, reward_signal=0.7)
    sys.process_feedback(result, target_node=n)

    # 显著奖励写入 reward_history
    assert n.reward_history == [0.7]


def test_process_feedback_significant_punishment_writes_both():
    """显著惩罚（负 reward）应该同时写入 reward 和 punishment。"""
    sys = ActionSystem()
    n = _make_node()
    sys.register_node(n)

    result = ActionResult(outcome=Outcome.FAILURE, reward_signal=-0.7)
    sys.process_feedback(result, target_node=n)

    assert n.reward_history == [-0.7]
    assert n.punishment_history == [-0.7]


def test_to_stimulus_atom_wraps_action_result():
    sys = ActionSystem()
    n = _make_node("weather_query")
    sys.register_node(n)

    result = ActionResult(outcome=Outcome.SUCCESS, reward_signal=0.5)
    atom = sys.to_stimulus_atom(result, n)

    from cogcore.types import StimulusSource
    assert atom.source == StimulusSource.ACTION
    assert "weather_query" in atom.content
    assert "success" in atom.content
    assert atom.energy.real == 0.5  # 奖励 → 真实能量
    assert atom.trace.origin == f"action_node:{n.id}"


# ============================================================
# 教师反馈延迟合流（论文 5.7.1 关键设计）
# ============================================================


def test_queue_teacher_feedback_does_not_apply_immediately():
    """queue_teacher_feedback 不应立即改变行动节点状态。"""
    sys = ActionSystem()
    n = _make_node()
    sys.register_node(n)
    initial_reward = list(n.reward_history)

    sys.queue_teacher_feedback({
        "reward_signal": 0.9,
        "anchor_note": "good timing",
    })

    # 关键：行动节点状态未变（因为还没 merge）
    assert n.reward_history == initial_reward
    # 但 feedback_queue 已加入
    assert len(sys._feedback_queue) == 1


def test_merge_pending_teacher_feedback_returns_queued():
    sys = ActionSystem()
    sys.set_tick(5)

    sys.queue_teacher_feedback({
        "reward_signal": 0.8,
        "anchor_note": "well done",
    })
    sys.queue_teacher_feedback({
        "reward_signal": -0.3,
        "anchor_note": "too verbose",
    })

    merged = sys.merge_pending_teacher_feedback()
    assert len(merged) == 2
    assert merged[0].reward_signal == 0.8
    assert merged[1].reward_signal == -0.3
    assert merged[0].received_tick == 5

    # merge 后 queue 应清空
    assert len(sys._feedback_queue) == 0


def test_merge_clears_queue():
    """多次 queue + 一次 merge 后 queue 应清空。"""
    sys = ActionSystem()
    for i in range(5):
        sys.queue_teacher_feedback({"reward_signal": 0.1 * i})

    assert len(sys._feedback_queue) == 5
    merged = sys.merge_pending_teacher_feedback()
    assert len(merged) == 5
    assert len(sys._feedback_queue) == 0


def test_teacher_feedback_with_atom_target():
    """教师反馈可以锚定到特定 atom_id。"""
    from uuid import uuid4
    sys = ActionSystem()
    target = uuid4()
    sys.queue_teacher_feedback({
        "reward_signal": 0.5,
        "anchor_note": "specific action",
        "target_atom_id": target,
    })
    merged = sys.merge_pending_teacher_feedback()
    assert merged[0].target_atom_id == target


# ============================================================
# get_action_report
# ============================================================


def test_get_action_report_basic():
    sys = ActionSystem()
    n1 = _make_node("a")
    n2 = _make_node("b")
    sys.register_node(n1)
    sys.register_node(n2)
    sys.set_tick(7)

    report = sys.get_action_report()
    assert report["tick"] == 7
    assert report["node_count"] == 2
    assert report["pending_teacher_feedback"] == 0
    assert report["total_executions"] == 0
    assert len(report["nodes"]) == 2


def test_get_action_report_with_executions():
    sys = ActionSystem()
    pool = StatePool()
    nt = NTModulations()
    n = _make_node("test")
    sys.register_node(n)
    sys.set_tick(0)

    def my_executor(node):
        return ActionResult(outcome=Outcome.SUCCESS, reward_signal=0.0)

    candidates = sys.evaluate_drives(pool, nt)
    sys.execute(candidates[0], executor=my_executor)

    report = sys.get_action_report()
    assert report["total_executions"] == 1
    assert report["nodes"][0]["execution_count"] == 1
