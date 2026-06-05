"""M3.5 执行工具 (L12.2 自改)。

受限的 shell + pytest 执行, 过安全闸门。
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from cogcore.self_modify_safety import (
    check_command,
    check_paths,
    check_pytest_args,
    is_path_in_repo,
)

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _record_action(action: dict[str, Any]) -> None:
    logger.info(f"[agent-action] {json.dumps(action, ensure_ascii=False)}")


def run_tests(
    path: str = "tests/",
    marker: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    """跑 pytest, 返回 pass/fail 摘要。

    Args:
        path: 测试路径
        marker: pytest -m 标记
        timeout: 秒

    Returns:
        {passed, failed, errors, total, returncode, output_tail}
    """
    _record_action({"action": "run_tests", "path": path, "marker": marker})

    # 安全检查
    if path:
        ok, err = check_paths([path])
        if not ok:
            return {"error": f"path not allowed: {err}"}

    if marker and "-k skip" in marker.lower():
        return {"error": "forbidden pytest filter: -k skip"}

    # 构造命令
    cmd = ["python", "-m", "pytest", path, "-q", "--tb=line", "--no-header"]
    if marker:
        cmd.extend(["-m", marker])

    env = {**__import__("os").environ, "PYTHONPATH": "src"}
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_project_root()),
            capture_output=True,
            text=True,
            timeout=timeout + 30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"error": "pytest timed out", "returncode": -1}
    except FileNotFoundError:
        return {"error": "python not found", "returncode": -1}

    output = result.stdout + result.stderr
    # 解析最后一行 "=== N passed in X.Xs ===" 或 "=== N failed ==="
    passed = 0
    failed = 0
    errors = 0
    m = re.search(r"(\d+) passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", output)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+) errors?", output)
    if m:
        errors = int(m.group(1))
    # 提取 failure summary
    output_tail = "\n".join(output.splitlines()[-30:])

    return {
        "returncode": result.returncode,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": passed + failed + errors,
        "output_tail": output_tail,
    }


def run_command(cmd: str, timeout: int = 30) -> dict[str, Any]:
    """受限 shell 命令执行（白名单 + 超时）。

    允许的命令前缀: pytest, python, git, ls, cat, echo, cd, pwd
    """
    _record_action({"action": "run_command", "cmd": cmd[:200]})

    ok, err = check_command(cmd)
    if not ok:
        return {"error": f"command blocked: {err}", "returncode": -1}

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(_project_root()),
            capture_output=True,
            text=True,
            timeout=min(timeout, 120),
        )
    except subprocess.TimeoutExpired:
        return {"error": "command timed out", "returncode": -1}
    except Exception as e:
        return {"error": str(e), "returncode": -1}

    return {
        "returncode": result.returncode,
        "stdout": result.stdout[:2000],
        "stderr": result.stderr[:2000],
    }


# ============================================================
# 注册
# ============================================================


def register_exec_tools(registry: Any) -> int:
    """把执行工具注册到 ToolRegistry。"""
    from cogcore.tools import ToolRegistry

    if not isinstance(registry, ToolRegistry):
        return 0

    tools: list[tuple[str, Any, dict[str, str]]] = [
        ("run_tests", run_tests, {"path": "string", "marker": "string"}),
        ("run_command", run_command, {"cmd": "string", "timeout": "int"}),
    ]
    for name, func, schema in tools:
        registry.register_tool(name, func, schema)
        registry.add_to_allowlist(name)
    return len(tools)
