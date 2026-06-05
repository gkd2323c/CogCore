"""CFS（认知感受系统）烟雾测试（M0.4）。"""

from __future__ import annotations

import logging

import pytest

from cogcore.cfs import CognitiveFeelingSystem, FeelingSignal
from cogcore.state_pool import EnergySummary
from cogcore.types import FeelingType, StimulusSource

logging.basicConfig(level=logging.WARNING)


# ============================================================
# evaluate
# ============================================================


def test_evaluate_empty_summary():
    cfs = CognitiveFeelingSystem()
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.0, "active_count": 0},
        hdb_result={},
        previous_feedback={},
    )
    assert signals == []


def test_evaluate_dissonance_high_pressure():
    """认知压 > 0.7 应该触发违和感。"""
    cfs = CognitiveFeelingSystem(pressure_high=0.7)
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.85, "active_count": 5},
        hdb_result={},
        previous_feedback={},
    )
    dissonance = [s for s in signals if s.type == FeelingType.DISSONANCE]
    assert len(dissonance) == 1
    assert dissonance[0].intensity == pytest.approx(0.85)


def test_evaluate_correct_pressure_drop():
    """认知压快速下降应该触发正确感。"""
    cfs = CognitiveFeelingSystem(pressure_drop=0.3)
    # 第一轮高认知压
    cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.9, "active_count": 5},
        hdb_result={},
        previous_feedback={},
    )
    # 第二轮认知压骤降
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.4, "active_count": 5},
        hdb_result={},
        previous_feedback={},
    )
    correct = [s for s in signals if s.type == FeelingType.CORRECT]
    assert len(correct) == 1
    # 下降 0.5 > 0.3 触发
    assert correct[0].intensity == pytest.approx(0.5)


def test_evaluate_anticipation_reward():
    """奖励 > 0.3 应该触发期待。"""
    cfs = CognitiveFeelingSystem()
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.1, "active_count": 3},
        hdb_result={},
        previous_feedback={"reward_signal": 0.7},
    )
    anticipation = [s for s in signals if s.type == FeelingType.ANTICIPATION]
    assert len(anticipation) == 1
    assert anticipation[0].intensity == pytest.approx(0.7)


def test_evaluate_pressure_punishment():
    """惩罚 < -0.3 应该触发压力。"""
    cfs = CognitiveFeelingSystem()
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.1, "active_count": 3},
        hdb_result={},
        previous_feedback={"reward_signal": -0.7},
    )
    pressure = [s for s in signals if s.type == FeelingType.PRESSURE]
    assert len(pressure) == 1
    assert pressure[0].intensity == pytest.approx(0.7)


def test_evaluate_fatigue_high_executions():
    """最近执行次数 > 5 应该触发疲劳。"""
    cfs = CognitiveFeelingSystem(fatigue_threshold=5)
    cfs.set_recent_execution_count(8)
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.1, "active_count": 3},
        hdb_result={},
        previous_feedback={},
    )
    fatigue = [s for s in signals if s.type == FeelingType.FATIGUE]
    assert len(fatigue) == 1
    assert fatigue[0].intensity == pytest.approx(0.8)  # 8/10


def test_evaluate_multiple_signals_at_once():
    """高压 + 惩罚 → 违和 + 压力。"""
    cfs = CognitiveFeelingSystem()
    signals = cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.85, "active_count": 3},
        hdb_result={},
        previous_feedback={"reward_signal": -0.6},
    )
    types = {s.type for s in signals}
    assert FeelingType.DISSONANCE in types
    assert FeelingType.PRESSURE in types


# ============================================================
# to_stimulus_atoms
# ============================================================


def test_to_stimulus_atoms_wraps_signals():
    cfs = CognitiveFeelingSystem()
    cfs.set_tick(5)
    signals = [
        FeelingSignal(type=FeelingType.DISSONANCE, intensity=0.8, tick=5),
        FeelingSignal(type=FeelingType.ANTICIPATION, intensity=0.6, tick=5),
    ]
    atoms = cfs.to_stimulus_atoms(signals)

    assert len(atoms) == 2
    for atom in atoms:
        assert atom.source == StimulusSource.FEELING
        assert atom.birth_tick == 5
    assert "dissonance" in atoms[0].content
    assert "anticipation" in atoms[1].content


# ============================================================
# 历史
# ============================================================


def test_feeling_history_accumulates():
    cfs = CognitiveFeelingSystem()
    cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.8, "active_count": 3},
        hdb_result={},
        previous_feedback={},
    )
    cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.4, "active_count": 3},
        hdb_result={},
        previous_feedback={"reward_signal": 0.5},
    )
    history = cfs.get_feeling_history()
    assert len(history) >= 2  # 至少 2 个信号


def test_cfs_report():
    cfs = CognitiveFeelingSystem()
    cfs.set_tick(10)
    cfs.evaluate(
        pool_energy_summary={"cognitive_pressure": 0.8, "active_count": 3},
        hdb_result={},
        previous_feedback={},
    )
    report = cfs.get_cfs_report()
    assert report["tick"] == 10
    assert report["history_size"] >= 1
    assert "dissonance" in report["type_counts"]
