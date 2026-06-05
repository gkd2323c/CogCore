"""NT（情绪递质系统）烟雾测试（M0.4）。"""

from __future__ import annotations

import logging

import pytest

from cogcore.nt import NTModulations, NeurotransmitterSystem
from cogcore.types import FeelingType

logging.basicConfig(level=logging.WARNING)


def _signal(sig_type: str, intensity: float = 0.5, tick: int = 0):
    """构造 feeling signal dict（CFS 输出格式）。"""
    return {"type": sig_type, "intensity": intensity, "tick": tick}


# ============================================================
# update
# ============================================================


def test_update_empty():
    nt = NeurotransmitterSystem()
    result = nt.update(feeling_signals=[], reward_signals=[], rules={})
    # 没有 impulse，current 应该保持
    assert result.focus == 0.0
    assert result.arousal == 0.0


def test_update_dissonance_raises_caution():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[_signal("dissonance", 0.8)],
        reward_signals=[],
        rules={},
    )
    # caution 应该上升
    assert nt.current.caution > 0.0
    # arousal 也应该上升（违和感包含警觉）
    assert nt.current.arousal > 0.0


def test_update_correct_raises_focus():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[_signal("correct", 0.6)],
        reward_signals=[],
        rules={},
    )
    assert nt.current.focus > 0.0
    assert nt.current.stability > 0.0


def test_update_anticipation_raises_arousal_exploration():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[_signal("anticipation", 0.7)],
        reward_signals=[],
        rules={},
    )
    assert nt.current.arousal > 0.0
    assert nt.current.exploration > 0.0


def test_update_pressure_raises_caution_fatigue():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[_signal("pressure", 0.5)],
        reward_signals=[],
        rules={},
    )
    assert nt.current.caution > 0.0
    assert nt.current.fatigue > 0.0


def test_update_fatigue_raises_fatigue():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[_signal("fatigue", 0.6)],
        reward_signals=[],
        rules={},
    )
    assert nt.current.fatigue > 0.0


def test_update_positive_reward_raises_arousal():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[],
        reward_signals=[0.5],
        rules={},
    )
    assert nt.current.arousal > 0.0


def test_update_negative_reward_raises_caution():
    nt = NeurotransmitterSystem()
    nt.update(
        feeling_signals=[],
        reward_signals=[-0.5],
        rules={},
    )
    assert nt.current.caution > 0.0
    assert nt.current.fatigue > 0.0


# ============================================================
# 公式正确性
# ============================================================


def test_inertia_decay_toward_baseline():
    """高 inertia 应该让 NT 向 baseline 收敛。"""
    nt = NeurotransmitterSystem(
        NTModulations(
            focus=0.0, baseline={"focus": 0.5}
        )
    )
    # baseline=0.5, current=0.0, inertia=0.85
    # 第一次：focus = 0.5 + 0.85 * (0 - 0.5) + 0 = 0.075
    nt.update(feeling_signals=[], reward_signals=[], rules={})
    # focus 应该从 0 向 baseline 0.5 推进
    assert 0.0 < nt.current.focus < 0.5
    assert nt.current.focus == pytest.approx(0.075)


def test_clamp_to_unit_interval():
    """所有 NT 通道值应该 clamp 到 [0, 1]。"""
    nt = NeurotransmitterSystem()
    # 极强 impulse
    nt.update(
        feeling_signals=[_signal("dissonance", 10.0)],  # intensity > 1
        reward_signals=[],
        rules={},
    )
    assert 0.0 <= nt.current.focus <= 1.0
    assert 0.0 <= nt.current.arousal <= 1.0
    assert 0.0 <= nt.current.caution <= 1.0
    assert 0.0 <= nt.current.fatigue <= 1.0


def test_rules_fatigue_growth():
    """硬规则 fatigue_growth 应该累加 fatigue impulse。"""
    nt = NeurotransmitterSystem()
    nt.update(feeling_signals=[], reward_signals=[], rules={"fatigue_growth": 0.1})
    assert nt.current.fatigue > 0.0


def test_rules_stability_decay():
    """硬规则 stability_decay 应该减少 stability impulse。"""
    nt = NeurotransmitterSystem(NTModulations(stability=0.5))
    nt.update(feeling_signals=[], reward_signals=[], rules={"stability_decay": 0.1})
    # stability 从 0.5 → 0.85 * 0.5 - 0.1 = 0.325
    assert nt.current.stability < 0.5


# ============================================================
# 报告
# ============================================================


def test_nt_report():
    nt = NeurotransmitterSystem()
    nt.set_tick(7)
    nt.update(feeling_signals=[_signal("dissonance", 0.5)], reward_signals=[], rules={})
    report = nt.get_nt_report()
    assert report["tick"] == 7
    assert "caution" in report
    assert "inertia" in report
