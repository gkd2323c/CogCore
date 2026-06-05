"""AdaptiveTuner（自适应调参器）烟雾测试（M0.4）。"""

from __future__ import annotations

import logging

import pytest

from cogcore.adaptive_tuner import AdaptiveTuner, TunerAdjustments
from cogcore.nt import NTModulations
from cogcore.state_pool import EnergySummary

logging.basicConfig(level=logging.WARNING)


# ============================================================
# assess
# ============================================================


def test_assess_normal_no_adjustment():
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=10.0, active_count=50, cognitive_pressure=0.1)
    nt = NTModulations()
    stats = {"cam_energy_variance": 0.5, "induction_nodes": 20}
    adj = tuner.assess(pool, nt, stats)
    assert adj.reason == "正常区间"
    assert adj.lambda_real_delta == 0.0
    assert adj.attention_budget_delta == 0


def test_assess_low_energy_increases_budget():
    """总能量 < 5.0 → 沉寂：增加 budget，降低衰减。"""
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=3.0, active_count=5, cognitive_pressure=0.1)
    nt = NTModulations()
    adj = tuner.assess(pool, nt, {})
    assert "沉寂" in adj.reason
    assert adj.lambda_real_delta < 0.0  # 降低衰减
    assert adj.attention_budget_delta > 0  # 增加 budget


def test_assess_overload_reduces_budget():
    """活跃对象 > 80% max → 过载。"""
    tuner = AdaptiveTuner(max_atoms=10, tuner_max_adjust=0.5)
    pool = EnergySummary(total_energy=10.0, active_count=9, cognitive_pressure=0.1)
    nt = NTModulations()
    adj = tuner.assess(pool, nt, {})
    assert "过载" in adj.reason
    assert adj.attention_budget_delta < 0  # 减少 budget
    assert adj.lambda_real_delta > 0.0  # 加速衰减


def test_assess_high_pressure_consecutive():
    """连续 N 轮认知压 > 0.7 触发压力响应。"""
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=10.0, active_count=10, cognitive_pressure=0.8)
    nt = NTModulations()

    # 第一轮：开始累计
    tuner.assess(pool, nt, {})
    # 第二轮
    tuner.assess(pool, nt, {})
    # 第三轮（达到阈值 3）
    adj = tuner.assess(pool, nt, {})
    assert "高压" in adj.reason


def test_assess_attention_diffuse_reduces_budget():
    """CAM 能量方差 < 0.1 → 注意力过散。"""
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=10.0, active_count=10, cognitive_pressure=0.1)
    nt = NTModulations()
    stats = {"cam_energy_variance": 0.05}
    adj = tuner.assess(pool, nt, stats)
    assert "注意力过散" in adj.reason
    assert adj.attention_budget_delta < 0


def test_assess_induction_thin():
    """感应展开节点 < 5 → 传播过薄。"""
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=10.0, active_count=10, cognitive_pressure=0.1)
    nt = NTModulations()
    stats = {"induction_nodes": 3}
    adj = tuner.assess(pool, nt, stats)
    assert "传播过薄" in adj.reason


def test_assess_priority_low_energy_over_overload():
    """低能量优先级高于过载（先沉寂后过载）。"""
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=2.0, active_count=200, cognitive_pressure=0.1)
    nt = NTModulations()
    adj = tuner.assess(pool, nt, {})
    # 低能量先匹配
    assert "沉寂" in adj.reason


# ============================================================
# clamp
# ============================================================


def test_clamp_truncates_large_deltas():
    """超过 max_adjust 的 delta 应该被 clamp。"""
    tuner = AdaptiveTuner(tuner_max_adjust=0.1, max_atoms=10)
    adj = TunerAdjustments(lambda_real_delta=0.5, threshold_delta=0.5)
    clamped = tuner._clamp(adj)
    assert abs(clamped.lambda_real_delta) <= 0.1
    assert abs(clamped.threshold_delta) <= 0.1
    assert clamped.truncated is True


def test_clamp_no_truncation_when_within_range():
    tuner = AdaptiveTuner(tuner_max_adjust=0.15)
    adj = TunerAdjustments(lambda_real_delta=0.1)
    clamped = tuner._clamp(adj)
    assert clamped.lambda_real_delta == 0.1
    assert clamped.truncated is False


# ============================================================
# apply
# ============================================================


def test_apply_records_adjustment():
    tuner = AdaptiveTuner()
    adj = TunerAdjustments(reason="test", attention_budget_delta=2)
    tuner.apply(adj)
    assert tuner._last_adjustments is adj
    assert len(tuner._adjustment_history) == 1


def test_apply_normal_no_log():
    """正常区间的 apply 不应输出 INFO 日志（但应该有 history）。"""
    tuner = AdaptiveTuner()
    adj = TunerAdjustments(reason="正常区间")
    tuner.apply(adj)
    assert len(tuner._adjustment_history) == 1


# ============================================================
# 报告
# ============================================================


def test_tuner_report():
    tuner = AdaptiveTuner()
    pool = EnergySummary(total_energy=10.0, active_count=10, cognitive_pressure=0.1)
    nt = NTModulations()
    tuner.assess(pool, nt, {})
    tuner.apply(tuner._last_adjustments)
    report = tuner.get_tuner_report()
    assert report["tick_count"] == 1
    assert report["history_size"] == 1
