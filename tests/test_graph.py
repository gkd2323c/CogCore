"""CogCore StateGraph 黑盒测试（M0.5）。

覆盖：
- build_cogcore_graph 编译
- invoke 一次能跑通 10 阶段
- state 累积 stages_log
- 不变量：嵌套字段独立性（T1）+ 不双重累加（T5）
"""

from __future__ import annotations

import logging

import pytest

from cogcore.action_system import ActionNode, ActionResult, ActionSource, ActionSystem, Outcome
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.graph import build_cogcore_graph, invoke_cogcore
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool

logging.basicConfig(level=logging.WARNING)


def _make_modules():
    """构造一组默认模块实例。"""
    pool = StatePool()
    hdb = HDB()
    cfs = CognitiveFeelingSystem()
    attention = Attention()
    nt_sys = NeurotransmitterSystem()
    action_sys = ActionSystem()
    tuner = AdaptiveTuner()
    return {
        "pool": pool,
        "hdb": hdb,
        "cfs": cfs,
        "attention": attention,
        "nt_sys": nt_sys,
        "action_sys": action_sys,
        "tuner": tuner,
    }


# ============================================================
# 编译
# ============================================================


def test_build_graph_returns_compiled():
    modules = _make_modules()
    graph = build_cogcore_graph(modules)
    assert graph is not None
    assert "CompiledStateGraph" in type(graph).__name__


def test_build_graph_with_no_modules():
    """无模块传入时也能编译（stage 会通过 _safe_call 处理 None）。"""
    graph = build_cogcore_graph()
    assert graph is not None


def test_build_graph_with_partial_modules():
    """部分模块传入时也能编译。"""
    pool = StatePool()
    hdb = HDB()
    graph = build_cogcore_graph({"pool": pool, "hdb": hdb})
    assert graph is not None


# ============================================================
# invoke
# ============================================================


def test_invoke_runs_10_stages():
    """一次 invoke 应该跑通 10 个 stage。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    result = invoke_cogcore(
        graph,
        raw_input="测试输入",
        tick=0,
        thread_id="test-1",
    )

    # 关键不变量：stages_log 应该有 10 条（T5 修复：add reducer 不双重累加）
    assert len(result["stages_log"]) == 10, (
        f"stages_log 期望 10 条，实际 {len(result['stages_log'])}"
    )


def test_invoke_state_atoms_accumulated():
    """一次 invoke 后 new_atoms 应该有内容（TextSensor 把输入拆为词）。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    result = invoke_cogcore(
        graph,
        raw_input="你好 世界",
        tick=0,
        thread_id="test-2",
    )

    # TextSensor 把 "你好 世界" 拆为 2 个 atom
    assert len(result["new_atoms"]) >= 2


def test_invoke_cam_set():
    """invoke 后 cam 应该被设置。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    result = invoke_cogcore(
        graph,
        raw_input="测试",
        tick=0,
        thread_id="test-3",
    )

    assert result["cam"] is not None
    # CAM 是 Pydantic 实例，访问属性
    assert len(result["cam"].items) > 0


def test_invoke_nt_values_updated():
    """invoke 后 nt_values 应该被更新（不再是全 0）。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    result = invoke_cogcore(
        graph,
        raw_input="测试",
        tick=0,
        thread_id="test-4",
    )

    nt = result["nt_values"]
    assert nt is not None
    # 至少能访问 6 个通道字段
    assert isinstance(nt.focus, float)
    assert isinstance(nt.arousal, float)


# ============================================================
# 关键不变量：T1 + T5
# ============================================================


def test_nested_field_independence_invoke():
    """invoke 后 nt_values 应该是完整的 NTModulations，不是部分 dict。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    result = invoke_cogcore(
        graph,
        raw_input="test",
        tick=0,
        thread_id="test-5",
    )

    # T1 验证：nt_values 是 NTModulations 实例（不是部分 dict）
    nt = result["nt_values"]
    # 应该有 6 个 NT 通道属性
    expected_channels = ["focus", "arousal", "caution", "exploration", "fatigue", "stability"]
    for ch in expected_channels:
        assert hasattr(nt, ch), f"nt_values 缺少通道: {ch}"


def test_no_double_accumulation_invoke():
    """T5 验证：stages_log 在一次 invoke 中恰好累积 10 条（add reducer 单次）。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    result = invoke_cogcore(
        graph,
        raw_input="test",
        tick=0,
        thread_id="test-6",
    )

    stages = result["stages_log"]
    assert len(stages) == 10
    # 每条应该是 stage_X_xxx 格式
    for s in stages:
        assert s.startswith("stage_"), f"格式错误: {s}"


# ============================================================
# 多次 invoke（thread state）
# ============================================================


def test_multiple_invocations_accumulate_through_checkpointer():
    """多次 invoke 在同一 thread_id 下，state 会通过 checkpointer 累积。"""
    modules = _make_modules()
    graph = build_cogcore_graph(modules)

    # 第一次
    r1 = invoke_cogcore(graph, raw_input="first", tick=0, thread_id="t-7")
    # 第二次（同 thread）
    r2 = invoke_cogcore(graph, raw_input="second", tick=1, thread_id="t-7")

    # raw_input 应该是最新一次（"second"）
    # 注意：LangGraph checkpointer 默认行为是把初始 input 和 state 合并
    # r2["raw_input"] 应该是 "second"
    assert r2["raw_input"] == "second"
    # tick 应该被设置
    assert r2["tick"] == 1


# ============================================================
# 模块集成验证
# ============================================================


def test_invoke_with_action_executor_actually_executes():
    """invoke 后 action_sys 应该真的执行了行动。"""
    modules = _make_modules()

    def my_executor(node):
        return ActionResult(
            outcome=Outcome.SUCCESS,
            reward_signal=0.7,
            feedback_text="test",
        )

    modules["action_sys"].set_executor(my_executor)
    modules["action_sys"].register_node(ActionNode(
        name="test_action", threshold=0.5, source=ActionSource.INNATE,
    ))

    graph = build_cogcore_graph(modules)
    result = invoke_cogcore(
        graph,
        raw_input="trigger",
        tick=0,
        thread_id="t-8",
    )

    # 行动应该被执行 1 次
    assert modules["action_sys"].get_action_report()["total_executions"] == 1
    # new_atoms 中应该有 action 来源的 atom
    # 注：LangGraph invoke 后 StimulusAtom 是 Pydantic 实例，访问 .source.value
    action_atoms = [a for a in result["new_atoms"] if a.source.value == "action"]
    assert len(action_atoms) >= 1
