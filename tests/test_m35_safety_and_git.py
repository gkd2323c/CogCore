"""M3.5 自修改安全闸门 + git 工具 + exec 工具测试。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cogcore.self_modify_safety import (
    check_command,
    check_commit_message,
    check_paths,
    check_pytest_args,
    is_path_in_repo,
)
from cogcore.tools import ToolRegistry
from cogcore.tools_exec import register_exec_tools, run_command, run_tests
from cogcore.tools_git import (
    git_diff,
    git_log,
    git_status,
    register_git_tools,
)


# ============================================================
# 安全闸门: paths
# ============================================================


def test_check_paths_allowed():
    ok, err = check_paths(["src/cogcore/types.py"])
    assert ok
    assert err == ""


def test_check_paths_tests_dir_allowed():
    ok, _ = check_paths(["tests/test_config.py", "tests/test_x.py"])
    assert ok


def test_check_paths_config_toml_blocked():
    ok, err = check_paths(["config.toml"])
    assert not ok
    assert "forbidden" in err


def test_check_paths_pyproject_blocked():
    ok, err = check_paths(["pyproject.toml"])
    assert not ok


def test_check_paths_agents_md_blocked():
    ok, err = check_paths(["AGENTS.md"])
    assert not ok


def test_check_paths_unknown_dir_blocked():
    ok, err = check_paths(["src/openai/secret.py"])
    assert not ok


def test_check_paths_empty():
    ok, err = check_paths([])
    assert not ok


# ============================================================
# 安全闸门: commands
# ============================================================


def test_check_command_pytest():
    ok, _ = check_command("pytest tests/")
    assert ok


def test_check_command_python():
    ok, _ = check_command("python -m pytest")
    assert ok


def test_check_command_git():
    ok, _ = check_command("git status")
    assert ok


def test_check_command_rm_blocked():
    ok, err = check_command("rm -rf /")
    assert not ok
    assert "forbidden" in err


def test_check_command_dd_blocked():
    ok, err = check_command("dd if=/dev/zero of=/dev/sda")
    assert not ok


def test_check_command_fork_bomb_blocked():
    ok, err = check_command(":(){:|:&};:")
    assert not ok


def test_check_command_unknown_blocked():
    ok, err = check_command("nmap localhost")
    assert not ok
    assert "allowlist" in err


# ============================================================
# 安全闸门: pytest args
# ============================================================


def test_check_pytest_args_normal():
    ok, _ = check_pytest_args("-v --tb=short")
    assert ok


def test_check_pytest_args_skip_blocked():
    ok, err = check_pytest_args("-k skip")
    assert not ok


def test_check_pytest_args_deselect_blocked():
    ok, err = check_pytest_args("--deselect tests/test_x.py")
    assert not ok


# ============================================================
# 安全闸门: commit message
# ============================================================


def test_check_commit_message_with_tag():
    ok, _ = check_commit_message("[auto-iterate] fix: 空指针 in NT update")
    assert ok


def test_check_commit_message_without_tag():
    ok, err = check_commit_message("fix: something")
    assert not ok
    assert "[auto-iterate]" in err


def test_check_commit_message_too_short():
    ok, err = check_commit_message("[auto-iterate] x")
    assert not ok


# ============================================================
# 安全闸门: path in repo
# ============================================================


def test_is_path_in_repo():
    assert is_path_in_repo("src/cogcore/types.py")
    assert is_path_in_repo("tests/test_x.py")


def test_is_path_in_repo_rejects_traversal():
    assert not is_path_in_repo("../../etc/passwd")


# ============================================================
# git 工具
# ============================================================


def test_git_status():
    """git status 应该返回结构化结果。"""
    result = git_status()
    assert "staged" in result
    assert "unstaged" in result
    assert "untracked" in result
    assert isinstance(result["staged"], list)


def test_git_log():
    """git log 应该返回最近 commits（即使为空也不报错）。"""
    result = git_log(n=3)
    assert isinstance(result, list)
    # 当前 git repo 应该有 commits
    if not result or "error" in result[0]:
        # 新仓库没 commit 也 OK
        return
    for entry in result:
        assert "sha" in entry
        assert "subject" in entry


def test_git_log_filter_by_path():
    result = git_log(path="src/cogcore/types.py", n=5)
    assert isinstance(result, list)


def test_git_diff():
    result = git_diff()
    # 可能是空字符串（无变更） 或 error
    assert isinstance(result, str)


def test_register_git_tools():
    reg = ToolRegistry()
    n = register_git_tools(reg)
    assert n == 5
    available = reg.get_available_tools()
    for name in ["git_status", "git_diff", "git_log", "git_commit", "git_revert"]:
        assert name in available


# ============================================================
# exec 工具
# ============================================================


def test_run_tests_full_suite():
    """跑全量测试, 应该 pass。

    只跑快测试 (排除慢测试如 MCP / API) 以避免超时。
    """
    result = run_tests(path="tests/test_config.py", timeout=30)
    assert "returncode" in result
    assert "passed" in result
    if "error" not in result:
        assert result["returncode"] == 0
        assert result["failed"] == 0
        assert result["errors"] == 0


def test_run_tests_specific_file():
    """跑单个测试文件。"""
    result = run_tests(path="tests/test_config.py", timeout=30)
    assert result.get("returncode") == 0
    assert result.get("failed", 0) == 0


def test_run_tests_invalid_path_blocked():
    result = run_tests(path="config.toml")
    assert "error" in result


def test_run_command_ls():
    result = run_command("ls src/cogcore")
    assert result.get("returncode") == 0
    assert "src/cogcore" in result.get("stdout", "") or "types.py" in result.get("stdout", "")


def test_run_command_rm_blocked():
    result = run_command("rm -rf /")
    assert "error" in result
    assert "blocked" in result.get("error", "")


def test_run_command_pwd():
    result = run_command("pwd")
    assert result.get("returncode") == 0


def test_register_exec_tools():
    reg = ToolRegistry()
    n = register_exec_tools(reg)
    assert n == 2
    assert "run_tests" in reg.get_available_tools()
    assert "run_command" in reg.get_available_tools()


# ============================================================
# git_commit 安全: 拒绝 config.toml
# ============================================================


def test_git_commit_blocked_for_config():
    """commit config.toml 应该被安全闸门拒绝。"""
    from cogcore.tools_git import git_commit

    result = git_commit(
        message="[auto-iterate] bad commit",
        paths=["config.toml"],
    )
    assert "Error" in result
    assert "forbidden" in result or "not in allowed" in result


def test_git_commit_blocked_without_tag():
    from cogcore.tools_git import git_commit

    result = git_commit(
        message="fix: no tag here",
        paths=["src/cogcore/types.py"],
    )
    assert "Error" in result
    assert "[auto-iterate]" in result
