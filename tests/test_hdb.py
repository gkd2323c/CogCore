"""HDB 极简版烟雾测试（M0.2）。

覆盖：lookup/store/get_structure/get_local_db/get_episodic/
write_episodic/decay_unused/get_hdb_report。
"""

from __future__ import annotations

import logging

from cogcore.hdb import HDB
from cogcore.types import EpisodicMemory, Outcome, StimulusAtom, StimulusSource, Structure

logging.basicConfig(level=logging.WARNING)


def _make_atom(content: str) -> StimulusAtom:
    return StimulusAtom(
        content=content,
        source=StimulusSource.EXTERNAL,
        modality="text",
        trace={"origin": "test"},
    )


# ============================================================
# lookup
# ============================================================


def test_lookup_empty_hdb_creates_new_structure():
    """空 HDB 应该为新 stimuli 创建结构。"""
    hdb = HDB()
    hdb.set_tick(0)

    result = hdb.lookup([_make_atom("hello world")])

    assert len(result.new_structures) == 1
    assert result.matched_structures == []
    # 残差：第一次 lookup 没有命中，所以没残差
    assert result.residuals == []


def test_lookup_finds_exact_match():
    """完全匹配应该高 match_score。"""
    hdb = HDB()
    hdb.set_tick(0)

    # 第一次：创建新结构
    hdb.lookup([_make_atom("hello world")])
    # 第二次：完全相同
    result = hdb.lookup([_make_atom("hello world")])

    assert len(result.matched_structures) >= 1
    best_score = max(result.match_scores.values())
    assert best_score > 0.5  # 完全匹配应该有高 score


def test_lookup_partial_match_creates_substructure():
    """部分匹配时应该写新子结构到 local_db（M0.2 简化版：残差的首 token）。"""
    hdb = HDB(growth_threshold=0.3)
    hdb.set_tick(0)

    # 第一次："hello world"
    hdb.lookup([_make_atom("hello world")])
    # 第二次："hello world 朋友"（部分匹配 + 残差）
    result = hdb.lookup([_make_atom("hello world friend")])

    # 应该有 matched（"hello world" 部分）和 new_structures
    assert len(result.matched_structures) >= 1
    # 残差应该非空
    assert len(result.residuals) > 0 or len(result.new_structures) > 0


def test_lookup_no_match_creates_new_structure():
    """完全不匹配时应该写新结构。"""
    hdb = HDB(growth_threshold=0.9)  # 极高阈值，几乎不匹配
    hdb.set_tick(0)

    hdb.lookup([_make_atom("alpha")])
    result = hdb.lookup([_make_atom("omega")])

    # 第二次应该创建新结构（因为第一次没有高匹配）
    assert len(result.new_structures) >= 1


def test_lookup_increments_hit_count():
    hdb = HDB()
    hdb.set_tick(0)

    # 第 1 次 lookup 创建结构（hit_count = 0）
    hdb.lookup([_make_atom("test content")])
    # 第 2、3 次 lookup 应该匹配已有结构（hit_count++）
    hdb.lookup([_make_atom("test content")])
    hdb.lookup([_make_atom("test content")])

    # 3 次 lookup 后，至少有一个结构的 hit_count >= 2（创建+2次匹配）
    structures = list(hdb._structures.values())
    assert any(s.energy_stats.hit_count >= 2 for s in structures)


def test_lookup_stimuli_case_insensitive():
    """匹配应该大小写无关。"""
    hdb = HDB()
    hdb.set_tick(0)

    hdb.lookup([_make_atom("Hello World")])
    result = hdb.lookup([_make_atom("hello world")])

    assert len(result.matched_structures) >= 1


# ============================================================
# store
# ============================================================


def test_store_creates_structure_explicitly():
    hdb = HDB()
    hdb.set_tick(0)

    atoms = [_make_atom("explicit content")]
    struct = hdb.store(atoms, residual="some context")

    assert struct in hdb._structures.values()
    assert "some context" in struct.residuals


def test_store_with_empty_residual():
    hdb = HDB()
    struct = hdb.store([_make_atom("x")], residual=None)
    assert struct.residuals == []


# ============================================================
# get_structure / get_local_db
# ============================================================


def test_get_structure_returns_stored():
    hdb = HDB()
    struct = hdb.store([_make_atom("x")], residual=None)

    retrieved = hdb.get_structure(struct.id)
    assert retrieved.id == struct.id
    assert retrieved.index_key == struct.index_key


def test_get_local_db_default_empty():
    hdb = HDB()
    struct = hdb.store([_make_atom("x")], residual=None)
    local_db = hdb.get_local_db(struct.id)
    assert local_db == {}


# ============================================================
# 情景记忆
# ============================================================


def test_write_and_get_episodic():
    hdb = HDB()
    mem = EpisodicMemory(
        action_taken="查天气",
        outcome=Outcome.SUCCESS,
    )
    hdb.write_episodic(mem)

    retrieved = hdb.get_episodic(mem.id)
    assert retrieved.action_taken == "查天气"
    assert retrieved.outcome == Outcome.SUCCESS


# ============================================================
# decay_unused
# ============================================================


def test_decay_unused_removes_old_uncalled_structures():
    hdb = HDB()
    hdb.set_tick(0)

    # 创建结构
    hdb.store([_make_atom("rarely used")], residual=None)

    # 推进 tick
    hdb.set_tick(200)

    removed = hdb.decay_unused(max_age_ticks=100, min_hit_count=1)
    assert removed >= 1


def test_decay_unused_keeps_popular_structures():
    hdb = HDB()
    hdb.set_tick(0)

    # 创建并反复查询（提高 hit_count）
    hdb.lookup([_make_atom("popular query")])
    for _ in range(5):
        hdb.lookup([_make_atom("popular query")])

    hdb.set_tick(200)
    removed = hdb.decay_unused(max_age_ticks=100, min_hit_count=3)

    # popular 的应该被保留
    popular = [s for s in hdb._structures.values() if s.energy_stats.hit_count >= 5]
    assert len(popular) >= 1


# ============================================================
# get_hdb_report
# ============================================================


def test_get_hdb_report_includes_sha256():
    hdb = HDB()
    hdb.set_tick(0)
    hdb.store([_make_atom("x")], residual=None)

    report = hdb.get_hdb_report()
    assert "sha256" in report
    assert len(report["sha256"]) == 64  # SHA-256 hex
    assert report["structure_count"] == 1
    assert report["episodic_count"] == 0


def test_get_hdb_report_aggregates_depths():
    hdb = HDB()
    hdb.set_tick(0)
    hdb.store([_make_atom("a")], residual=None)
    hdb.store([_make_atom("b")], residual=None)

    report = hdb.get_hdb_report()
    assert report["structure_count"] == 2
    assert report["avg_depth"] == 0.0
    assert report["max_depth"] == 0


# ============================================================
# 与 CogCoreState 集成
# ============================================================


def test_hdb_patch_workflow():
    """演示：HDB.lookup 返回 LookupResult，CogCoreState 用 patch_hdb_snapshot 接收。"""
    from cogcore.state_schema import CogCoreState, make_updater
    from cogcore.pipeline import _apply_patch

    hdb = HDB()
    hdb.set_tick(0)
    hdb.lookup([_make_atom("hello world")])

    # 类似 stage_3 的逻辑
    result = hdb.lookup([_make_atom("hello world")])

    state = CogCoreState()
    patch = (
        make_updater(state)
        .patch_hdb_snapshot(
            matched_structure_ids=[str(s.id) for s in result.matched_structures],
            match_scores={str(k): float(v) for k, v in result.match_scores.items()},
            new_structure_ids=[str(s.id) for s in result.new_structures],
            residual_count=len(result.residuals),
        )
        .to_patch()
    )
    _apply_patch(state, patch)

    assert len(state.hdb_snapshot.matched_structure_ids) >= 1
    assert state.hdb_snapshot.residual_count >= 0
