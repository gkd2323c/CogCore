"""StatePool 烟雾测试（M0.2）。

覆盖：add/get_all/get_by_energy/decay/cleanup/get_energy_summary/
apply_attention_boost/apply_inhibition/get_state_report。
"""

from __future__ import annotations

import logging
import pytest

from cogcore.state_pool import StatePool
from cogcore.types import StimulusAtom, StimulusSource

logging.basicConfig(level=logging.WARNING)


def _make_atom(content: str, energy_real: float = 1.0, energy_virtual: float = 0.5, age: int = 0) -> StimulusAtom:
    return StimulusAtom(
        content=content,
        source=StimulusSource.EXTERNAL,
        modality="text",
        energy={"real": energy_real, "virtual": energy_virtual},
        age_ticks=age,
        trace={"origin": "test"},
    )


# ============================================================
# add / get_all
# ============================================================


def test_add_and_get_all():
    pool = StatePool()
    assert pool.get_all() == []

    a1 = _make_atom("hello")
    a2 = _make_atom("world")
    pool.add(a1)
    pool.add(a2)

    atoms = pool.get_all()
    assert len(atoms) == 2
    assert {a.id for a in atoms} == {a1.id, a2.id}


def test_add_same_id_replaces():
    """同 ID 的原子 add 后会替换（dict 语义）。"""
    pool = StatePool()
    a1 = _make_atom("v1")
    pool.add(a1)
    a2 = _make_atom("v2")
    a2_id = a2.id

    # 创建一个同 ID 但内容不同的原子
    a3 = StimulusAtom(
        id=a2_id,
        content="v3_replaced",
        source=StimulusSource.EXTERNAL,
        trace={"origin": "test"},
    )
    pool.add(a3)

    atoms = pool.get_all()
    assert len(atoms) == 2
    replaced = next(a for a in atoms if a.id == a2_id)
    assert replaced.content == "v3_replaced"


# ============================================================
# get_by_energy
# ============================================================


def test_get_by_energy_filters_correctly():
    pool = StatePool()
    pool.add(_make_atom("low", energy_real=0.1, energy_virtual=0.05))  # total=0.15
    pool.add(_make_atom("mid", energy_real=0.5, energy_virtual=0.3))  # total=0.8
    pool.add(_make_atom("high", energy_real=1.0, energy_virtual=0.5))  # total=1.5

    high = pool.get_by_energy(1.0)
    assert len(high) == 1
    assert high[0].content == "high"

    mid_or_above = pool.get_by_energy(0.5)
    assert len(mid_or_above) == 2

    all_above_zero = pool.get_by_energy(0.0)
    assert len(all_above_zero) == 3


# ============================================================
# decay
# ============================================================


def test_decay_applies_lambda():
    """decay 应该按 λ_real 和 λ_virtual 衰减。"""
    pool = StatePool(lambda_real=0.5, lambda_virtual=0.25)
    atom = _make_atom("x", energy_real=1.0, energy_virtual=1.0)
    pool.add(atom)

    pool.decay()

    assert atom.energy.real == pytest.approx(0.5)
    assert atom.energy.virtual == pytest.approx(0.25)
    assert atom.age_ticks == 1


def test_decay_increments_age():
    pool = StatePool()
    atom = _make_atom("x", age=5)
    pool.add(atom)

    pool.decay()
    assert atom.age_ticks == 6

    pool.decay()
    assert atom.age_ticks == 7


# ============================================================
# cleanup
# ============================================================


def test_cleanup_removes_low_energy():
    pool = StatePool(min_energy_cleanup=0.1)
    pool.add(_make_atom("keep", energy_real=0.5, energy_virtual=0.5))  # total=1.0
    pool.add(_make_atom("drop", energy_real=0.05, energy_virtual=0.0))  # total=0.05

    evicted = pool.cleanup()

    remaining = pool.get_all()
    assert len(remaining) == 1
    assert remaining[0].content == "keep"

    # 验证返回的 evicted 列表
    assert len(evicted) == 1
    assert evicted[0].content == "drop"


def test_cleanup_removes_old_atoms():
    pool = StatePool(min_energy_cleanup=0.0, max_atoms=200)
    pool.add(_make_atom("young", age=10))
    pool.add(_make_atom("old", age=300))

    pool.cleanup(max_age=200)

    remaining = pool.get_all()
    assert len(remaining) == 1
    assert remaining[0].content == "young"


def test_cleanup_combined_criteria():
    pool = StatePool()
    pool.add(_make_atom("a", energy_real=0.5, energy_virtual=0.5, age=5))
    pool.add(_make_atom("b", energy_real=0.01, energy_virtual=0.0, age=5))  # 太低
    pool.add(_make_atom("c", energy_real=0.5, energy_virtual=0.5, age=300))  # 太老

    pool.cleanup(min_energy=0.05, max_age=200)

    remaining = [a.content for a in pool.get_all()]
    assert remaining == ["a"]


# ============================================================
# get_energy_summary
# ============================================================


def test_energy_summary_empty_pool():
    pool = StatePool()
    summary = pool.get_energy_summary()
    assert summary.total_energy == 0.0
    assert summary.active_count == 0
    assert summary.cognitive_pressure == 0.0


def test_energy_summary_with_atoms():
    pool = StatePool()
    pool.add(_make_atom("a", energy_real=1.0, energy_virtual=0.0))  # |1-0|=1
    pool.add(_make_atom("b", energy_real=0.5, energy_virtual=0.5))  # |0.5-0.5|=0

    summary = pool.get_energy_summary()
    assert summary.active_count == 2
    assert summary.real_energy == pytest.approx(1.5)
    assert summary.virtual_energy == pytest.approx(0.5)
    assert summary.total_energy == pytest.approx(2.0)
    # 认知压：(1+0)/2 = 0.5
    assert summary.cognitive_pressure == pytest.approx(0.5)


# ============================================================
# apply_attention_boost / apply_inhibition
# ============================================================


def test_apply_attention_boost_increases_energy():
    pool = StatePool()
    a = _make_atom("x", energy_real=1.0, energy_virtual=0.5)
    pool.add(a)

    pool.apply_attention_boost([a.id], factor=0.5)

    assert a.energy.real == pytest.approx(1.5)
    assert a.energy.virtual == pytest.approx(0.75)


def test_apply_inhibition_decreases_energy():
    pool = StatePool()
    a = _make_atom("x", energy_real=1.0, energy_virtual=1.0)
    pool.add(a)

    pool.apply_inhibition([a.id], factor=0.3)

    assert a.energy.real == pytest.approx(0.7)
    assert a.energy.virtual == pytest.approx(0.7)


def test_apply_boost_on_missing_atom_silent():
    """不存在的 ID 应该被静默忽略。"""
    pool = StatePool()
    from uuid import uuid4
    pool.apply_attention_boost([uuid4()], factor=1.0)
    assert pool.get_all() == []  # 无副作用


# ============================================================
# get_state_report
# ============================================================


def test_get_state_report_basic():
    pool = StatePool(lambda_real=0.9, lambda_virtual=0.8, max_atoms=100)
    pool.set_tick(42)
    pool.add(_make_atom("a", energy_real=0.5, energy_virtual=0.5))

    report = pool.get_state_report()

    assert report["tick"] == 42
    assert report["active_count"] == 1
    assert report["lambda_real"] == 0.9
    assert report["lambda_virtual"] == 0.8
    assert report["max_atoms"] == 100
    assert report["total_energy"] == pytest.approx(1.0)


# ============================================================
# 与 CogCoreState 集成（patch 风格）
# ============================================================


def test_state_pool_patch_workflow():
    """演示：StatePool 内部修改 _atoms，但 CogCoreState 通过 patch 风格更新 pool_snapshot。"""
    from cogcore.state_schema import CogCoreState, make_updater

    state = CogCoreState()
    pool = StatePool()
    pool.add(_make_atom("a", energy_real=1.0, energy_virtual=0.0))
    pool.add(_make_atom("b", energy_real=0.5, energy_virtual=0.5))

    # 类似 stage_2 的逻辑：把状态池摘要记到 patch
    summary = pool.get_energy_summary()
    active_ids = [str(a.id) for a in pool.get_all()]

    patch = (
        make_updater(state)
        .patch_pool_snapshot(
            energy_summary=summary,
            active_atom_ids=active_ids,
        )
        .to_patch()
    )

    # 应用 patch 到 state
    from cogcore.pipeline import _apply_patch
    _apply_patch(state, patch)

    # 不变量：state.pool_snapshot 应该反映状态池内容
    assert state.pool_snapshot.energy_summary.active_count == 2
    assert len(state.pool_snapshot.active_atom_ids) == 2
    assert state.pool_snapshot.energy_summary.cognitive_pressure == pytest.approx(0.5)
