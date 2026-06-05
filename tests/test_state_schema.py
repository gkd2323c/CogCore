"""状态合并与 Reducer 契约的烟雾测试。

⚠️ 核心保证：
1. 嵌套对象必须返回整个新对象（不能返回 partial dict）
2. 列表字段用 add reducer 累加
3. Pydantic model_copy(update=...) 是深合并的安全方式
4. ⚠️ StateUpdater 不预累加（修复陷阱 T5：Fluent API 双重累加）
"""

from __future__ import annotations

import logging
from operator import add
from typing import Annotated

from cogcore.nt import NTModulations
from cogcore.state_schema import (
    CogCoreState,
    HDBSnapshot,
    StatePoolSnapshot,
    StateUpdater,
    attention_budget_reducer,
    make_updater,
    merge_cam,
)
from cogcore.types import StimulusAtom, StimulusSource

logging.basicConfig(level=logging.WARNING)


# ============================================================
# CogCoreState 基础
# ============================================================


def test_pydantic_state_creation():
    """CogCoreState 可以默认实例化。"""
    state = CogCoreState()
    assert state.tick == 0
    assert state.raw_input == ""
    assert state.pool_snapshot is not None
    assert state.hdb_snapshot is not None
    assert state.nt_values is not None
    assert state.new_atoms == []
    assert state.grown_atoms == []
    assert state.stages_log == []


# ============================================================
# StateUpdater 不预累加（关键 T5 修复验证）
# ============================================================


def test_state_updater_does_not_preaccumulate():
    """⚠️ 关键：StateUpdater.append_atoms 不预累加，只记录增量。

    旧 Fluent API（错误）：
        state.new_atoms = [A]
        return state.append_atoms([B])
        # patch.new_atoms = [A, B]  ✗ 双重累加风险
        # LangGraph: [A] + [A, B] = [A, A, B]  💥

    新模式（正确）：
        state.new_atoms = [A]
        return make_updater(state).append_atoms([B]).to_patch()
        # patch = {"new_atoms": [B]}  ✓ 单独增量
        # LangGraph add reducer: [A] + [B] = [A, B]  ✓
    """
    atom_a = StimulusAtom(content="a", source=StimulusSource.EXTERNAL, trace={"origin": "t"})
    atom_b = StimulusAtom(content="b", source=StimulusSource.EXTERNAL, trace={"origin": "t"})

    # 模拟"state 中已有 atom_a"
    state = CogCoreState()
    state = state.model_copy(update={"new_atoms": [atom_a]})
    assert state.new_atoms == [atom_a]

    # 用 StateUpdater 增加 atom_b
    updater = make_updater(state)
    updater.append_atoms([atom_b])
    patch = updater.to_patch()

    # patch 中只有 [atom_b]，不与现有 state 拼接
    assert patch == {"new_atoms": [atom_b]}, (
        f"StateUpdater 不应预累加，但 patch = {patch}"
    )


def test_state_updater_chained_appends():
    """链式 append 应该在 patch 内可拼接（不与 state 现有值拼接）。"""
    atom_a = StimulusAtom(content="a", source=StimulusSource.EXTERNAL, trace={"origin": "t"})
    atom_b = StimulusAtom(content="b", source=StimulusSource.EXTERNAL, trace={"origin": "t"})
    atom_c = StimulusAtom(content="c", source=StimulusSource.EXTERNAL, trace={"origin": "t"})

    state = CogCoreState().model_copy(update={"new_atoms": [atom_a]})

    # 链式 append 两次
    patch = (
        make_updater(state)
        .append_atoms([atom_b])
        .append_atoms([atom_c])
        .to_patch()
    )

    # patch 内可拼接 → [atom_b, atom_c]
    # 不与 state 现有 [atom_a] 拼接 → 最终 LangGraph 会 add 一次变成 [atom_a, atom_b, atom_c]
    assert patch == {"new_atoms": [atom_b, atom_c]}


def test_langgraph_merge_no_double_accumulation():
    """⚠️ 模拟 LangGraph Reducer 合并：StateUpdater 输出不应导致双重累加。"""
    from cogcore.pipeline import _apply_patch

    atom_a = StimulusAtom(content="a", source=StimulusSource.EXTERNAL, trace={"origin": "t"})
    atom_b = StimulusAtom(content="b", source=StimulusSource.EXTERNAL, trace={"origin": "t"})

    # 初始 state: new_atoms = [atom_a]
    state = CogCoreState().model_copy(update={"new_atoms": [atom_a]})

    # 节点 1 返回 patch（不预累加）
    patch = make_updater(state).append_atoms([atom_b]).to_patch()
    assert patch == {"new_atoms": [atom_b]}

    # 模拟 LangGraph Reducer（_apply_patch 是手动版本）
    _apply_patch(state, patch)

    # 不变量：new_atoms 应该是 [atom_a, atom_b]，不是 [atom_a, atom_a, atom_b]
    assert len(state.new_atoms) == 2
    assert state.new_atoms[0].content == "a"
    assert state.new_atoms[1].content == "b"


def test_nested_field_independence():
    """修改一个嵌套字段不应影响其他嵌套字段。"""
    state = CogCoreState()
    updater = make_updater(state).patch_nt_values(focus=0.5)
    patch = updater.to_patch()

    # patch 包含整个新 nt_values（不是部分 dict）
    assert "nt_values" in patch
    assert patch["nt_values"].focus == 0.5
    # 其他 NT 字段保留默认值
    assert patch["nt_values"].arousal == 0.0


def test_pool_snapshot_patch():
    """patch_pool_snapshot 完整返回新对象。"""
    state = CogCoreState()
    patch = make_updater(state).patch_pool_snapshot(
        active_atom_ids=["uuid-1", "uuid-2"]
    ).to_patch()

    assert patch["pool_snapshot"].active_atom_ids == ["uuid-1", "uuid-2"]


# ============================================================
# 链式调用
# ============================================================


def test_chained_patches_compose():
    """链式 patch 应该累积到 patch dict。"""
    state = CogCoreState()

    patch = (
        make_updater(state)
        .append_stage("stage_1")
        .append_stage("stage_2")
        .patch_nt_values(focus=0.7)
        .append_stage("stage_3")
        .to_patch()
    )

    # patch 内：stages_log 累加，nt_values 整体替换
    assert patch["stages_log"] == ["stage_1", "stage_2", "stage_3"]
    assert patch["nt_values"].focus == 0.7


def test_to_patch_returns_independent_dict():
    """to_patch 返回独立 dict，修改不影响内部状态。"""
    state = CogCoreState()
    updater = make_updater(state).append_stage("test")
    patch = updater.to_patch()
    patch["stages_log"].append("tampered")

    # 再次 to_patch 应返回原始 patch（未污染）
    patch2 = updater.to_patch()
    assert patch2["stages_log"] == ["test"]


def test_bool_of_updater():
    """updater 应该能用作 bool 判断（是否有内容）。"""
    state = CogCoreState()
    empty_updater = make_updater(state)
    assert not empty_updater

    non_empty = make_updater(state).append_stage("test")
    assert non_empty


# ============================================================
# Pipeline 集成
# ============================================================


def test_pipeline_runs_10_stages():
    """run_cycle 应该跑通 10 个 stage 节点。"""
    from cogcore.pipeline import run_cycle

    report = run_cycle(raw_input="测试", tick=0)
    assert len(report.stages_completed) == 10
    assert len(report.error_log) == 0


def test_pipeline_no_double_accumulation_after_10_stages():
    """⚠️ 跑完 10 个 stage 后，stages_log 应有 10 条（不是 100+）。"""
    from cogcore.pipeline import _apply_patch
    from cogcore.state_schema import CogCoreState, make_updater

    state = CogCoreState()

    # 模拟跑 10 个 stage——每个用 StateUpdater + append_stage
    for i in range(10):
        patch = make_updater(state).append_stage(f"stage_{i}").to_patch()
        _apply_patch(state, patch)

    # 关键不变量：stages_log 应该是 10 条
    assert len(state.stages_log) == 10, (
        f"双重累加 bug 触发：stages_log 有 {len(state.stages_log)} 条"
    )


# ============================================================
# Reducer 函数
# ============================================================


def test_attention_budget_reducer():
    """attention_budget_reducer 应该 clamp 在 [0, 20]。"""
    assert attention_budget_reducer(15, 25) == 20
    assert attention_budget_reducer(15, -5) == 0
    assert attention_budget_reducer(15, None) == 15
    assert attention_budget_reducer(15, 10) == 10


def test_merge_cam():
    """merge_cam 应该用 update 替换 existing。"""
    from cogcore.attention import CurrentAttentionMemory

    cam1 = CurrentAttentionMemory(items=[], tick=0)
    cam2 = CurrentAttentionMemory(items=[], tick=1)

    assert merge_cam(cam1, cam2) is cam2
    assert merge_cam(cam1, None) is cam1
    assert merge_cam(None, cam2) is cam2


def test_annotated_add_reducer_works():
    """Annotated[list, add] Reducer 应该累加。"""
    existing = ["a", "b"]
    update = ["c", "d"]
    result = add(existing, update)
    assert result == ["a", "b", "c", "d"]


# ============================================================
# 错误模式（必须避免）
# ============================================================


def test_partial_dict_pattern_would_be_dangerous():
    """演示：如果用部分嵌套 dict（错误模式 T1），会发生什么。

    这个测试不是要"使用"它，而是要"展示"它为什么危险。
    """
    state = CogCoreState()

    # 错误模式：返回部分嵌套 dict
    bad_patch = {"nt_values": {"focus": 0.5}}  # ✗ 整个 nt_values 被替换为 {"focus": 0.5}

    # 模拟 LangGraph 默认合并行为
    # LangGraph 看到顶层 key 是 nt_values，会做 existing 替换 update
    # existing = NTModulations()  →  update = {"focus": 0.5}
    # 结果：nt_values 变成一个没有 NTModulations 验证的 dict

    # 这就是为什么必须用整个 Pydantic 对象替换：
    good_patch = {"nt_values": state.nt_values.model_copy(update={"focus": 0.5})}
    assert good_patch["nt_values"].focus == 0.5
    # good_patch["nt_values"] 是 NTModulations 实例
    assert isinstance(good_patch["nt_values"], NTModulations)
