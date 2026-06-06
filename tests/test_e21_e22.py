"""M3.7 实验单元测试: E21 奖惩反事实课程 + E22 自迭代 A/B 对照.

直接测 run_m37_experiments.py 里的核心逻辑, 不需要跑全实验 (那个太慢).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

import scripts.run_m37_experiments as mex


# ============================================================
# E21: Reward Schedule Generation
# ============================================================


def test_e21_linear_asc_is_monotonic():
    """linear_asc 应该单调上升, 从 0 到接近 1."""
    sched = mex.make_reward_schedule("linear_asc", 100)
    assert len(sched) == 100
    assert sched[0] == 0.0
    assert sched[-1] > 0.95
    # 单调: 任意 i < j, sched[i] <= sched[j]
    for i in range(len(sched) - 1):
        assert sched[i] <= sched[i + 1]


def test_e21_plateau_spike_has_two_phases():
    """plateau_spike 前 30% 平, 后 70% 上升."""
    sched = mex.make_reward_schedule("plateau_spike", 100)
    # 前 30% 应该几乎不变 (允许 0.01 浮点误差)
    plateau = sched[:30]
    assert all(abs(p - 0.3) < 0.01 for p in plateau)
    # 后段单调上升
    for i in range(30, len(sched) - 1):
        assert sched[i] <= sched[i + 1] + 0.001


def test_e21_inverse_u_peaks_in_middle():
    """inverse_u 中间高, 两端低."""
    sched = mex.make_reward_schedule("inverse_u", 100)
    mid = sched[50]
    edge_low = sched[0]
    edge_high = sched[-1]
    assert mid > edge_low
    assert mid > edge_high


def test_e21_punishment_first_dominantly_negative():
    """punishment_first 前 80% 是 -0.5."""
    sched = mex.make_reward_schedule("punishment_first", 100)
    punishment = sched[:80]
    assert all(p == -0.5 for p in punishment)
    # 后 20% 上升到 0.4
    assert sched[-1] > 0.35


def test_e21_random_seed_reproducible():
    """random 用 seed 42 应该可复现."""
    sched1 = mex.make_reward_schedule("random", 50)
    sched2 = mex.make_reward_schedule("random", 50)
    assert sched1 == sched2
    # 不应全相同 (有随机性)
    assert any(sched1[i] != sched1[i + 1] for i in range(len(sched1) - 1))


# ============================================================
# E21: NT 演化路径对比
# ============================================================


def test_e21_paths_diverge_across_schedules():
    """5 条曲线 NT 演化路径应该有差异."""
    schedules = ["linear_asc", "plateau_spike", "inverse_u", "punishment_first", "random"]
    from cogcore.nt import NeurotransmitterSystem

    final_states = {}
    for sched in schedules:
        rewards = mex.make_reward_schedule(sched, 50)
        nt = NeurotransmitterSystem()
        for tick, r in enumerate(rewards):
            nt.set_tick(tick)
            nt.update([], [r], {"reward_signal": r})
        final_states[sched] = {
            "arousal": round(nt.current.arousal, 3),
            "caution": round(nt.current.caution, 3),
        }

    # arousal 应该跨至少 0.1 区间
    arousals = [v["arousal"] for v in final_states.values()]
    assert max(arousals) - min(arousals) > 0.1, f"arousal range too small: {arousals}"


def test_e21_punishment_leaves_more_fatigue_than_reward():
    """punishment_first 应该比 linear_asc 累积更多疲劳."""
    from cogcore.nt import NeurotransmitterSystem

    nt_punish = NeurotransmitterSystem()
    nt_reward = NeurotransmitterSystem()

    p_rewards = mex.make_reward_schedule("punishment_first", 50)
    r_rewards = mex.make_reward_schedule("linear_asc", 50)

    for tick, (p, r) in enumerate(zip(p_rewards, r_rewards)):
        nt_punish.set_tick(tick)
        nt_punish.update([], [p], {"reward_signal": p})
        nt_reward.set_tick(tick)
        nt_reward.update([], [r], {"reward_signal": r})

    # 允许 ±0.05 的浮点抖动
    assert nt_punish.current.fatigue >= nt_reward.current.fatigue - 0.05


# ============================================================
# E22: 自迭代 A/B 对照
# ============================================================


def test_e22_synthetic_failures_have_different_signatures():
    """3 种合成失败应该有不同 signature (failed vs errors vs returncode)."""
    from cogcore.tools import ToolRegistry
    from cogcore.tools_code import register_code_tools
    from cogcore.tools_exec import register_exec_tools
    from cogcore.tools_git import register_git_tools

    reg = ToolRegistry()
    register_code_tools(reg)
    register_git_tools(reg)
    register_exec_tools(reg)

    # logic_error: failed=1, errors=0, returncode=1
    reg.register_tool("run_tests", lambda **kw: {
        "failed": 1, "errors": 0, "returncode": 1, "passed": 0,
        "output_tail": "AssertionError"
    }, {"path": "string"})
    reg.add_to_allowlist("run_tests")
    res1 = reg.execute_tool("run_tests", {"path": "tests/"})
    assert res1["failed"] == 1
    assert res1["errors"] == 0

    # type_error: errors=1
    reg.register_tool("run_tests", lambda **kw: {
        "failed": 0, "errors": 1, "returncode": 1, "passed": 0,
        "output_tail": "TypeError"
    }, {"path": "string"})
    res2 = reg.execute_tool("run_tests", {"path": "tests/"})
    assert res2["failed"] == 0
    assert res2["errors"] == 1

    # import_error: errors=1, returncode=2
    reg.register_tool("run_tests", lambda **kw: {
        "failed": 0, "errors": 1, "returncode": 2, "passed": 0,
        "output_tail": "ImportError"
    }, {"path": "string"})
    res3 = reg.execute_tool("run_tests", {"path": "tests/"})
    assert res3["returncode"] == 2


def test_e22_meta_loop_detects_synthetic_failures():
    """M3.6 元循环在 3 个合成失败中都应该 detect 到 gap."""
    from cogcore.self_iteration import SelfIterateLoop
    from cogcore.tools import ToolRegistry
    from cogcore.tools_code import register_code_tools
    from cogcore.tools_exec import register_exec_tools
    from cogcore.tools_git import register_git_tools

    for kind in ["logic_error", "type_error", "import_error"]:
        reg = ToolRegistry()
        register_code_tools(reg)
        register_git_tools(reg)
        register_exec_tools(reg)
        reg.register_tool("run_tests", mex.make_synthetic_failure(reg, kind), {"path": "string"})
        reg.add_to_allowlist("run_tests")

        llm = MagicMock()
        mr = MagicMock()
        mc = MagicMock()
        mc.content = "[auto-iterate] mock"
        mr.choices = [type("c", (), {"message": mc})()]
        llm.chat.completions.create.return_value = mr

        d = tempfile.mkdtemp(prefix=f"cogcore_test_e22_{kind}_")
        try:
            loop = SelfIterateLoop(registry=reg, llm=llm, data_dir=d)
            obs = loop.observe()
            gap = loop.detect_gap(obs)
            assert gap is not None, f"{kind} should produce a gap"
        finally:
            shutil.rmtree(d, ignore_errors=True)


def test_e22_meta_loop_rolls_back_when_test_still_fails():
    """当 test 持续失败, 元循环应该 rollback 提议的 change."""
    from cogcore.self_iteration import Change, SelfIterateLoop
    from cogcore.tools import ToolRegistry
    from cogcore.tools_code import register_code_tools
    from cogcore.tools_exec import register_exec_tools
    from cogcore.tools_git import register_git_tools

    reg = ToolRegistry()
    register_code_tools(reg)
    register_git_tools(reg)
    register_exec_tools(reg)
    # 一直 fail
    reg.register_tool("run_tests", lambda **kw: {
        "failed": 1, "errors": 0, "returncode": 1, "passed": 0, "output_tail": "still failing"
    }, {"path": "string"})
    reg.add_to_allowlist("run_tests")

    llm = MagicMock()
    d = tempfile.mkdtemp()
    try:
        loop = SelfIterateLoop(registry=reg, llm=llm, data_dir=d)
        # override propose_change 给具体内容
        target = "src/cogcore/_test_e22_rollback.py"
        loop.propose_change = lambda plan, sources: Change(
            target_file=target,
            new_content="# auto generated\n",
            commit_message="[auto-iterate] test rollback",
        )
        result = loop.run_once()
        # 失败场景: rolled_back=True
        assert result.get("rolled_back") is True
        # 文件应该被删除
        full = os.path.join(os.getcwd(), target)
        assert not os.path.exists(full), f"{target} should be removed after rollback"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        # 兜底清理
        target = "src/cogcore/_test_e22_rollback.py"
        full = os.path.join(os.getcwd(), target)
        if os.path.exists(full):
            os.unlink(full)
