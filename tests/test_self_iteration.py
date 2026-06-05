"""M3.6 自迭代元循环测试。

测试 9 步流程 + 安全回滚 + dry-run 模式。
所有 LLM 和 git 操作都用 mock。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

from cogcore.self_iteration import Change, Gap, Plan, SelfIterateLoop
from cogcore.tools import ToolRegistry
from cogcore.tools_code import register_code_tools
from cogcore.tools_exec import register_exec_tools
from cogcore.tools_git import register_git_tools


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def tmp_data_dir():
    """临时数据目录。"""
    d = tempfile.mkdtemp(prefix="cogcore_si_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mock_registry():
    """包含 M3.5 工具的 registry。"""
    reg = ToolRegistry()
    register_code_tools(reg)
    register_git_tools(reg)
    register_exec_tools(reg)
    return reg


@pytest.fixture
def mock_llm():
    """Mock LLM bridge。"""
    llm = MagicMock()
    mr = MagicMock()
    mc = MagicMock()
    mc.content = "[auto-iterate] mock fix"
    mr.choices = [type("c", (), {"message": mc})()]
    llm.chat.completions.create.return_value = mr
    return llm


@pytest.fixture
def loop(mock_registry, mock_llm, tmp_data_dir):
    """构造一个 self-iteration loop 绑定临时数据目录。"""
    return SelfIterateLoop(
        registry=mock_registry,
        llm=mock_llm,
        project_root=os.getcwd(),
        data_dir=tmp_data_dir,
    )


# ============================================================
# 9 步基础
# ============================================================


def test_observe_collects_status_and_tests(loop, tmp_data_dir):
    obs = loop.observe()
    assert "timestamp" in obs
    # git_status 应该是 dict (无论真实还是 error)
    assert "git_status" in obs
    # test 字段存在
    assert "test" in obs


def test_detect_gap_no_failures(loop):
    obs = {"test": {"failed": 0, "errors": 0, "returncode": 0}}
    assert loop.detect_gap(obs) is None


def test_detect_gap_with_failures(loop):
    obs = {"test": {"failed": 2, "errors": 0, "returncode": 1}}
    gap = loop.detect_gap(obs)
    assert gap is not None
    assert "failed" in gap.description.lower() or "2 tests" in gap.description
    assert gap.severity == "high"


def test_plan_fix_returns_plan(loop):
    gap = Gap(id="g1", description="x failed", severity="high", evidence={})
    plan = loop.plan_fix(gap)
    assert plan.gap_id == "g1"
    assert isinstance(plan.files_to_read, list)


def test_propose_change_returns_change(loop):
    plan = Plan(gap_id="g1", files_to_read=[], files_to_modify=[], reasoning="x")
    change = loop.propose_change(plan, {})
    assert isinstance(change, Change)
    assert "[auto-iterate]" in change.commit_message


def test_apply_change_blocked_by_safety(loop, tmp_data_dir):
    """apply_change 拒绝改 config.toml。"""
    # 把 project_root 切到 tmp 目录, 避免跟真实项目里的 config.toml 冲突
    real_root = loop.root
    loop.root = tmp_data_dir
    try:
        change = Change(
            target_file="config.toml",
            new_content="[evil]\nfoo=bar",
            commit_message="[auto-iterate] bad",
        )
        assert not loop.apply_change(change)
        # 文件不应该被创建
        assert not os.path.exists(os.path.join(loop.root, "config.toml"))
    finally:
        loop.root = real_root


def test_apply_change_allowed(loop, tmp_data_dir):
    change = Change(
        target_file="src/cogcore/_test_tmp_module.py",
        new_content="# test\n",
        commit_message="[auto-iterate] tmp",
    )
    assert loop.apply_change(change)
    # 清理
    test_file = os.path.join(loop.root, change.target_file)
    if os.path.exists(test_file):
        os.unlink(test_file)


def test_test_returns_true_when_no_failures(loop):
    """当 run_tests 返回 0 failed / 0 errors 时 test() 返回 True。"""
    # 跑实际测试 (仓库内是健康的)
    assert loop.test() is True


def test_test_returns_false_when_failures(loop, mock_registry):
    """当 run_tests 返回 failed > 0 时 test() 返回 False。"""
    mock_registry.register_tool(
        "run_tests",
        lambda **kw: {"returncode": 1, "failed": 1, "errors": 0, "passed": 0, "output_tail": "1 failed"},
        {"path": "string"},
    )
    mock_registry.add_to_allowlist("run_tests")
    loop.registry = mock_registry
    assert loop.test() is False


def test_commit_requires_auto_iterate_tag(loop, mock_registry):
    change = Change(target_file="x.py", new_content="y", commit_message="no tag")
    result = loop.commit(change)
    assert "Error" in result


# ============================================================
# 完整 9 步循环: no-gap 跳过
# ============================================================


def test_run_once_no_gap_skips(loop):
    """测试都通过时, run_once 跳过 (no gap detected)。"""
    result = loop.run_once()
    assert "skipped" in result
    assert "no gap" in result["skipped"].lower()


# ============================================================
# Dry-run 模式
# ============================================================


def test_run_once_dry_run_with_proposal(loop, mock_registry, tmp_data_dir):
    """Dry-run 模式: 即使有 gap + 提案, 也不真改文件, 只返回 proposal。"""
    # mock 一个会失败的 run_tests
    call_count = {"n": 0}

    def fake_run_tests(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:  # 第一次 (observe) - 失败触发 gap
            return {"returncode": 1, "failed": 1, "errors": 0, "passed": 0, "output_tail": "1 failed"}
        return {"returncode": 0, "failed": 0, "errors": 0, "passed": 1, "output_tail": "ok"}

    mock_registry.register_tool("run_tests", fake_run_tests, {"path": "string"})
    mock_registry.add_to_allowlist("run_tests")
    loop.registry = mock_registry

    # override propose_change 给个具体 change
    change = Change(
        target_file="src/cogcore/_test_tmp.py",
        new_content="# test\n",
        commit_message="[auto-iterate] test",
    )
    loop.propose_change = lambda plan, sources: change

    result = loop.run_once(dry_run=True)
    assert result.get("dry_run") is True
    assert "gap" in result
    assert "change" in result
    # 文件不应该被创建 (dry-run)
    test_file = os.path.join(loop.root, "src/cogcore/_test_tmp.py")
    assert not os.path.exists(test_file)


# ============================================================
# 完整 9 步循环: 测试失败回滚
# ============================================================


def test_run_once_test_failure_rolls_back(loop, mock_registry, tmp_data_dir):
    """应用变更后测试失败, 应该 rollback (删除临时文件)。"""
    # observe 失败触发 gap
    call_count = {"n": 0}

    def fake_run_tests(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:  # observe
            return {"returncode": 1, "failed": 1, "errors": 0, "passed": 0, "output_tail": "x failed"}
        # 后续 (test 步骤) 全部失败
        return {"returncode": 1, "failed": 1, "errors": 0, "passed": 0, "output_tail": "still failing"}

    mock_registry.register_tool("run_tests", fake_run_tests, {"path": "string"})
    mock_registry.add_to_allowlist("run_tests")

    change = Change(
        target_file="src/cogcore/_test_tmp.py",
        new_content="# test\n",
        commit_message="[auto-iterate] test",
    )
    loop.propose_change = lambda plan, sources: change
    loop.registry = mock_registry

    result = loop.run_once()
    assert result.get("failed") == "tests failed"
    assert result.get("rolled_back") is True
    # 文件应该被删除
    test_file = os.path.join(loop.root, "src/cogcore/_test_tmp.py")
    assert not os.path.exists(test_file)


# ============================================================
# 完整 9 步循环: 成功
# ============================================================


def test_run_once_success(loop, mock_registry, tmp_data_dir):
    """完整 9 步走通: 失败 -> 提议 -> 应用 -> 测试过 -> commit -> reload -> log。"""
    call_count = {"n": 0}

    def fake_run_tests(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:  # observe
            return {"returncode": 1, "failed": 1, "errors": 0, "passed": 0, "output_tail": "fail"}
        # 后续: 全过
        return {"returncode": 0, "failed": 0, "errors": 0, "passed": 99, "output_tail": "ok"}

    mock_registry.register_tool("run_tests", fake_run_tests, {"path": "string"})
    mock_registry.add_to_allowlist("run_tests")

    # mock git_commit
    mock_registry.register_tool(
        "git_commit",
        lambda **kw: "Committed: abc123",
        {"message": "string", "paths": "dict"},
    )
    mock_registry.add_to_allowlist("git_commit")

    change = Change(
        target_file="src/cogcore/_test_success.py",
        new_content="# success test\n",
        commit_message="[auto-iterate] fixed it",
    )
    loop.propose_change = lambda plan, sources: change
    loop.registry = mock_registry

    result = loop.run_once()
    assert result.get("success") is True
    assert result.get("gap_id", "").startswith("gap-")
    # 日志应该被写
    log_path = os.path.join(tmp_data_dir, "self_iteration.jsonl")
    assert os.path.exists(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    # 至少 9 行 (每步 1 行)
    assert len(lines) >= 9
    steps = [json.loads(l).get("step") for l in lines]
    assert "observe_start" in steps
    assert "detect_gap_start" in steps
    assert "test_passed" in steps
    assert "complete" in steps
    # 清理
    test_file = os.path.join(loop.root, "src/cogcore/_test_success.py")
    if os.path.exists(test_file):
        os.unlink(test_file)


# ============================================================
# 日志格式
# ============================================================


def test_log_writes_jsonl(loop, tmp_data_dir):
    loop.log("test_step", {"foo": "bar"})
    log_path = os.path.join(tmp_data_dir, "self_iteration.jsonl")
    with open(log_path) as f:
        line = f.readline().strip()
    record = json.loads(line)
    assert record["step"] == "test_step"
    assert record["foo"] == "bar"
    assert "ts" in record


# ============================================================
# 辅助方法
# ============================================================


def test_path_to_module():
    loop = SelfIterateLoop.__new__(SelfIterateLoop)
    assert loop._path_to_module("src/cogcore/tools.py") == "cogcore.tools"
    assert loop._path_to_module("src/cogcore/types.py") == "cogcore.types"
    assert loop._path_to_module("tests/test_x.py") == ""  # tests/ 不是模块
    assert loop._path_to_module("src/cogcore/__init__.py") == "cogcore"
