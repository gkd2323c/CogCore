"""M3.5 git 工具 (L12.2 自改)。

所有写操作都过 self_modify_safety 安全闸门。
所有调用都记录到 traces/agent-actions.jsonl (M4.3 实现)。
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from cogcore.self_modify_safety import (
    check_command,
    check_commit_message,
    check_paths,
    is_path_in_repo,
)

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _run_git(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """在项目根跑 git 命令, 返回 (returncode, stdout, stderr)。"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(_project_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out"
    except FileNotFoundError:
        return -1, "", "git not installed"


def _record_action(action: dict[str, Any]) -> None:
    """记录到 traces/agent-actions.jsonl（M4.3 后实写, 现在先 log）。"""
    logger.info(f"[agent-action] {json.dumps(action, ensure_ascii=False)}")


def git_status() -> dict[str, Any]:
    """返回 staged / unstaged / untracked 文件列表。"""
    code, out, err = _run_git(["status", "--porcelain"])
    if code != 0:
        return {"error": err, "staged": [], "unstaged": [], "untracked": []}
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    for line in out.strip().split("\n"):
        if not line:
            continue
        # 格式: XY filename, 如 "M  src/cogcore/xxx.py" 或 "?? newfile"
        if len(line) < 3:
            continue
        xy = line[:2]
        fname = line[3:]
        if "?" in xy:
            untracked.append(fname)
        else:
            if xy[0] != " ":
                staged.append(fname)
            if xy[1] != " ":
                unstaged.append(fname)
    return {"staged": staged, "unstaged": unstaged, "untracked": untracked}


def git_diff(path: str = "", staged: bool = False) -> str:
    """返回指定路径的 diff 字符串。"""
    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    if path:
        args.append("--")
        args.append(path)
    code, out, err = _run_git(args)
    if code != 0:
        return f"Error: {err}"
    return out


def git_log(path: str = "", n: int = 10) -> list[dict[str, str]]:
    """返回最近 n 个 commit。"""
    args = ["log", f"-n{n}", "--pretty=format:%H|%an|%ae|%s"]
    if path:
        args.append("--")
        args.append(path)
    code, out, err = _run_git(args)
    if code != 0:
        return [{"error": err}]
    results: list[dict[str, str]] = []
    for line in out.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            sha, author, email, subject = parts
            results.append({
                "sha": sha,
                "author": author,
                "email": email,
                "subject": subject,
            })
    return results


def git_commit(message: str, paths: list[str] | None = None) -> str:
    """提交变更（必须含 [auto-iterate] 标签, 路径必须在允许区）。"""
    _record_action({
        "action": "git_commit",
        "message": message,
        "paths": paths,
    })

    # 安全检查
    paths = paths or []
    if not paths:
        # 没有指定 paths, 用 git status 中的所有变更
        st = git_status()
        paths = st.get("staged", []) + st.get("unstaged", [])
        if not paths:
            return "Error: no paths to commit"

    ok, err = check_paths(paths)
    if not ok:
        return f"Error: {err}"

    ok, err = check_commit_message(message)
    if not ok:
        return f"Error: {err}"

    # git add + commit
    code, out, err = _run_git(["add"] + paths)
    if code != 0:
        return f"Error: git add failed: {err}"

    code, out, err = _run_git(["commit", "-m", message])
    if code != 0:
        return f"Error: git commit failed: {err}"
    return out


def git_revert(commit_sha: str) -> str:
    """回滚指定 commit（不能改 config.toml / pyproject.toml 等）。"""
    _record_action({"action": "git_revert", "commit_sha": commit_sha})

    # 看 commit 改了什么
    code, out, err = _run_git(["show", "--name-only", "--pretty=format:", commit_sha])
    if code != 0:
        return f"Error: {err}"
    changed_files = [f for f in out.strip().split("\n") if f]
    ok, err = check_paths(changed_files)
    if not ok:
        return f"Error: cannot revert forbidden changes: {err}"

    code, out, err = _run_git(["revert", "--no-edit", commit_sha])
    if code != 0:
        return f"Error: git revert failed: {err}"
    return out


# ============================================================
# 注册
# ============================================================


def register_git_tools(registry: Any) -> int:
    """把 git 工具注册到 ToolRegistry。"""
    from cogcore.tools import ToolRegistry

    if not isinstance(registry, ToolRegistry):
        return 0

    tools: list[tuple[str, Any, dict[str, str]]] = [
        ("git_status", git_status, {}),
        ("git_diff", git_diff, {"path": "string", "staged": "bool"}),
        ("git_log", git_log, {"path": "string", "n": "int"}),
        ("git_commit", git_commit, {"message": "string", "paths": "dict"}),
        ("git_revert", git_revert, {"commit_sha": "string"}),
    ]
    for name, func, schema in tools:
        registry.register_tool(name, func, schema)
        registry.add_to_allowlist(name)
    return len(tools)
