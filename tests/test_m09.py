"""Milestone M0.9 Time Perception & Complexity Modulation Unit Tests.

This file verifies:
- Time perception and calibration mapping (E06)
- Delayed task scheduling and execution in StatePool (E06)
- Complexity score calculation and attention modulation of budget/top_n (E07)
- Residual memory promotion under time显影 (E08)
"""

from __future__ import annotations

import pytest
from uuid import uuid4, UUID

from cogcore.types import StimulusAtom, Modality, AtomEnergy, StimulusSource, AtomTrace
from cogcore.hdb import HDB
from cogcore.state_pool import StatePool
from cogcore.attention import Attention, AttentionConfig


def _make_test_atom(
    content: str,
    energy_real: float = 1.0,
    energy_virtual: float = 0.0,
    source: StimulusSource = StimulusSource.EXTERNAL,
    age: int = 0
) -> StimulusAtom:
    return StimulusAtom(
        content=content,
        source=source,
        modality=Modality.TEXT,
        energy=AtomEnergy(real=energy_real, virtual=energy_virtual),
        age_ticks=age,
        trace=AtomTrace(origin="test")
    )


# ============================================================
# E06: Time Perception Tests
# ============================================================


def test_time_bucket_calibration():
    """验证时间间隔校准的线性插值计算及到期时间预测是否正确。"""
    hdb = HDB()
    
    # 刚好对齐桶的值
    c_0_5 = hdb.calibrate_time_bucket(0.5, source_energy=1.0, start_tick=10)
    assert c_0_5["bucket_pair"] == "0_5t/0_5t"
    assert c_0_5["main_bucket"] == "0_5t"
    assert c_0_5["weights"] == [1.0, 0.0]
    # start_tick + max(2, interval) = 10 + max(2, 0.5) = 12
    assert c_0_5["arrival_tick"] == 12

    c_3 = hdb.calibrate_time_bucket(3.0, source_energy=1.0, start_tick=10)
    assert c_3["bucket_pair"] == "3t/6t" or c_3["bucket_pair"] == "1_5t/3t"
    # 刚好等于3t。3t的下一位是6t。
    # 让我们看看 hdb.py 的逻辑：
    # range 为 buckets[i] <= d < buckets[i+1]
    # buckets = [0.5, 1.5, 3.0, 6.0, 12.0]
    # i=2: buckets[2]=3.0, buckets[3]=6.0
    # 3.0 <= d < 6.0 匹配。所以 b1=3.0, b2=6.0
    # w1 = (6.0 - 3.0) / (6.0 - 3.0) = 1.0
    # w2 = 0.0
    assert c_3["bucket_pair"] == "3t/6t"
    assert c_3["main_bucket"] == "3t"
    assert c_3["weights"] == [1.0, 0.0]
    assert c_3["arrival_tick"] == 13

    # 插值情况：2.0 介于 1.5 和 3.0 之间
    c_2 = hdb.calibrate_time_bucket(2.0, source_energy=1.0, start_tick=10)
    assert c_2["bucket_pair"] == "1_5t/3t"
    # w1 = (3.0 - 2.0) / (3.0 - 1.5) = 1.0 / 1.5 = 2/3
    # w2 = 1.0 - 2/3 = 1/3
    # w1 >= w2, 所以 main_bucket 是 b1 ("1_5t")
    assert c_2["main_bucket"] == "1_5t"
    assert abs(c_2["weights"][0] - 2/3) < 1e-4
    assert c_2["arrival_tick"] == 12


def test_delayed_tasks_execution():
    """验证延迟任务能够到期自动提取并投回状态池，且能量比例合适。"""
    hdb = HDB()
    pool = StatePool()
    
    start_tick = 10
    pool.set_tick(start_tick)
    hdb.set_tick(start_tick)
    
    struct_id = uuid4()
    # 注册一个延迟为 3 ticks 的任务。
    # 滴答到达 tick 应该为 10 + max(2, 3) = 13
    hdb.register_delayed_tasks(pool, struct_id, 3)
    
    # 在 11 和 12 滴答，还不应该触发
    pool.set_tick(11)
    fired_11 = pool.process_delayed_tasks(11)
    assert len(fired_11) == 0
    
    pool.set_tick(12)
    fired_12 = pool.process_delayed_tasks(12)
    assert len(fired_12) == 0
    
    # 推进到 13 滴答，此时延迟任务到期
    pool.set_tick(13)
    fired_13 = pool.process_delayed_tasks(13)
    assert len(fired_13) == 2
    
    # 验证提取原子的类型和能量
    contents = {atom.content for atom in fired_13}
    assert contents == {"delayed_anchor_item", "delayed_structure_projection"}
    
    for atom in fired_13:
        assert atom.energy.real == 1.4925
        assert atom.energy.virtual == 0.0


# ============================================================
# E07: Complexity Modulation Tests
# ============================================================


def test_attention_complexity_modulation():
    """验证活跃原子数改变时，Attention 能够切换至合适模式并调制容量和有效截断。"""
    att = Attention()
    
    # 1. 低复杂度分支 (N <= 8)
    pool_low = StatePool()
    for i in range(5):
        pool_low.add(_make_test_atom(f"low_{i}"))
    att.select(pool_low)
    report_low = att.get_selection_report()
    assert report_low["attention_mode"] == "attention_diverge_mode"
    assert report_low["budget"] == 6
    assert report_low["top_n"] == 21

    # 2. 中复杂度分支 (8 < N <= 10)
    pool_mid = StatePool()
    for i in range(9):
        pool_mid.add(_make_test_atom(f"mid_{i}"))
    att.select(pool_mid)
    report_mid = att.get_selection_report()
    assert report_mid["attention_mode"] == "baseline"
    assert report_mid["budget"] == 8
    assert report_mid["top_n"] == 16

    # 3. 高复杂度分支 (N > 10)
    pool_high = StatePool()
    for i in range(12):
        pool_high.add(_make_test_atom(f"high_{i}"))
    att.select(pool_high)
    report_high = att.get_selection_report()
    assert report_high["attention_mode"] == "attention_focus_mode"
    assert report_high["budget"] == 10
    assert report_high["top_n"] == 11

    # 验证指标差值
    # 高低预算差 == 4
    assert report_high["budget"] - report_low["budget"] == 4
    # 搜索范围差 == 10
    assert report_low["top_n"] - report_high["top_n"] == 10


# ============================================================
# E08: Residual Memory Promotion Tests
# ============================================================


def test_residual_promotion_matched():
    """验证恰好 3 ticks，且种子和线索均存在时，晋升能够成功触发。"""
    hdb = HDB()
    pool = StatePool()
    
    # t=1 激活种子
    hdb.set_tick(1)
    hdb.lookup([_make_test_atom("project_seed")])
    
    # t=4 (时间间隔恰好为 3) 收到线索
    pool.set_tick(4)
    pool.add(_make_test_atom("project_cue"))
    
    hdb.residual_promotion(pool, current_tick=4, promotion_enabled=True)
    
    # 检查状态池中是否已注入影子原子 st_000030
    promo_atoms = [atom for atom in pool.get_all() if atom.content == "promoted_shadow_raw_residual"]
    assert len(promo_atoms) == 1
    
    promo_atom = promo_atoms[0]
    assert promo_atom.id == UUID("00000000-0000-0000-0000-000000000030")
    assert promo_atom.energy.real == 2.0
    assert promo_atom.energy.virtual == 0.0


def test_residual_promotion_no_seed():
    """验证缺少种子激活时不会触发晋升。"""
    hdb = HDB()
    pool = StatePool()
    
    # 没有激活种子直接收到线索
    pool.set_tick(4)
    pool.add(_make_test_atom("project_cue"))
    
    hdb.residual_promotion(pool, current_tick=4, promotion_enabled=True)
    promo_atoms = [atom for atom in pool.get_all() if atom.content == "promoted_shadow_raw_residual"]
    assert len(promo_atoms) == 0


def test_residual_promotion_no_cue():
    """验证缺少线索时不会触发晋升。"""
    hdb = HDB()
    pool = StatePool()
    
    # t=1 激活种子
    hdb.set_tick(1)
    hdb.lookup([_make_test_atom("project_seed")])
    
    # t=4 (相差 3 tick)，但是状态池里没有 cue
    pool.set_tick(4)
    
    hdb.residual_promotion(pool, current_tick=4, promotion_enabled=True)
    promo_atoms = [atom for atom in pool.get_all() if atom.content == "promoted_shadow_raw_residual"]
    assert len(promo_atoms) == 0


def test_residual_promotion_wrong_tick():
    """验证时间间隔不为 3 时不会触发晋升。"""
    hdb = HDB()
    pool = StatePool()
    
    # t=1 激活种子
    hdb.set_tick(1)
    hdb.lookup([_make_test_atom("project_seed")])
    
    # 时间不为 4 (例如 t=3) 收到线索
    pool.set_tick(3)
    pool.add(_make_test_atom("project_cue"))
    
    hdb.residual_promotion(pool, current_tick=3, promotion_enabled=True)
    promo_atoms = [atom for atom in pool.get_all() if atom.content == "promoted_shadow_raw_residual"]
    assert len(promo_atoms) == 0

    # 推进到 t=5 收到线索
    pool_5 = StatePool()
    pool_5.set_tick(5)
    pool_5.add(_make_test_atom("project_cue"))
    
    hdb.residual_promotion(pool_5, current_tick=5, promotion_enabled=True)
    promo_atoms = [atom for atom in pool_5.get_all() if atom.content == "promoted_shadow_raw_residual"]
    assert len(promo_atoms) == 0


def test_residual_promotion_disabled():
    """验证禁用晋升通道时不会触发晋升。"""
    hdb = HDB()
    pool = StatePool()
    
    # t=1 激活种子
    hdb.set_tick(1)
    hdb.lookup([_make_test_atom("project_seed")])
    
    # t=4 收到线索
    pool.set_tick(4)
    pool.add(_make_test_atom("project_cue"))
    
    # 禁用通道
    hdb.residual_promotion(pool, current_tick=4, promotion_enabled=False)
    promo_atoms = [atom for atom in pool.get_all() if atom.content == "promoted_shadow_raw_residual"]
    assert len(promo_atoms) == 0
