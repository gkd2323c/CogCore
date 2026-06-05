"""M3.5 / L12 自修改安全闸门。

约束（来自总体计划 M3.5）：
  1. 路径必须是 src/cogcore/ 或 tests/ 或 docs/ 或 scripts/
  2. 不能删除文件
  3. 不能修改 config.toml / config.toml.example
  4. git commit message 必须包含 [auto-iterate] 标签
  5. pytest 不允许 -k skip
"""
from __future__ import annotations

from pathlib import Path


# 允许修改的路径前缀
ALLOWED_PATH_PREFIXES = (
    "src/cogcore/",
    "tests/",
    "docs/",
    "scripts/",
    "experiments/",
)

# 禁止修改的精确文件
FORBIDDEN_FILES = {
    "config.toml",
    "config.toml.example",
    ".env",
    "pyproject.toml",  # 依赖变更需要用户同意
    "AGENTS.md",       # 治理文档需要用户同意
    "AGENT_BUILD.MD",
}

# 禁止的命令模式
FORBIDDEN_CMD_PATTERNS = (
    "rm ", "rmdir ", "del ",         # 删除
    "mv ", "move ",                 # 移动（防止破坏 git 历史）
    "format ",                       # 格式化
    "> /dev/", ">/dev/null",        # 输出重定向到 /dev
    ":(){:|:&};:",                 # fork 炸弹
)


def check_paths(paths: list[str]) -> tuple[bool, str]:
    """检查一组路径是否都允许自修改。

    Returns:
        (True, "") if OK, else (False, error_message)
    """
    if not paths:
        return False, "no paths given"

    for p in paths:
        # 规范化
        normalized = p.replace("\\", "/")
        # 禁止文件
        if normalized in FORBIDDEN_FILES or any(
            normalized.endswith("/" + f) for f in FORBIDDEN_FILES
        ):
            return False, f"forbidden file: {normalized}"
        # 允许前缀
        if not any(normalized.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
            return False, f"path not in allowed zones: {normalized}"
    return True, ""


def check_command(cmd: str) -> tuple[bool, str]:
    """检查 shell 命令是否安全。

    Returns:
        (True, "") if OK, else (False, error_message)
    """
    cmd_lower = cmd.lower()
    for pat in FORBIDDEN_CMD_PATTERNS:
        if pat in cmd_lower:
            return False, f"forbidden command pattern: {pat}"
    # 限制: 只能跑 pytest, python, git
    cmd_stripped = cmd.strip()
    if not any(
        cmd_stripped.startswith(p)
        for p in ("pytest", "python", "git", "ls", "cat", "echo", "cd ", "pwd")
    ):
        return False, f"command not in allowlist: {cmd[:50]}"
    return True, ""


def check_pytest_args(args: str) -> tuple[bool, str]:
    """检查 pytest 参数是否含禁止的过滤/跳过。"""
    if "-k skip" in args or "--deselect" in args:
        return False, "forbidden pytest filter (skip/deselect)"
    return True, ""


def check_commit_message(msg: str) -> tuple[bool, str]:
    """检查 commit message 格式。"""
    if "[auto-iterate]" not in msg:
        return False, "commit message must contain [auto-iterate] tag"
    if len(msg) < 20:
        return False, "commit message too short (< 20 chars)"
    return True, ""


def is_path_in_repo(path: str) -> bool:
    """路径是否在仓库内（防止 ../ 越界）。"""
    p = Path(path)
    try:
        p.resolve().relative_to(Path(__file__).resolve().parent.parent.parent)
        return True
    except ValueError:
        return False
