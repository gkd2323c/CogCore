"""M4.2 SQLite 健康检查 CLI。

用法:
    python scripts/db_health.py                          # 默认 cogcore_data/state.db
    python scripts/db_health.py --db path/to/state.db   # 指定 db
    python scripts/db_health.py --backup cogcore_data/backups  # 维护模式 (backup + prune + vacuum + health)
    python scripts/db_health.py --prune --keep 50       # 只 prune, 保留 50
    python scripts/db_health.py --vacuum                # 只 vacuum
    python scripts/db_health.py --json                  # 输出 JSON 而不是 Markdown
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cogcore.db_maintenance import (
    HealthStatus,
    health_check,
    vacuum,
    prune_checkpoints,
    backup_to,
    full_maintenance,
)


DEFAULT_DBS = [
    "cogcore_data/state.db",
    "cogcore_state.db",
]


def find_default_db() -> str | None:
    """找第一个存在的默认 db。"""
    for d in DEFAULT_DBS:
        if os.path.exists(d):
            return d
    return None


def render_markdown(report_dict: dict, db_path: str) -> str:
    """渲染 HealthReport 为 Markdown。"""
    status = report_dict.get("status", "?")
    icon = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}.get(status, "?")
    lines = [
        f"# SQLite 健康报告 — {db_path}",
        "",
        f"**状态**: {icon} `{status.upper()}`",
        f"**时间**: {report_dict.get('timestamp', 0):.0f}",
        "",
        "## 容量",
        f"- 文件大小: **{report_dict.get('size_mb', 0):.2f} MB** ({report_dict.get('size_bytes', 0)} bytes)",
        f"- 含 WAL/SHM: {report_dict.get('size_with_wal_bytes', 0)} bytes",
        f"- WAL 未合并: {report_dict.get('writeahead_count', 0)} bytes",
        "",
        "## 结构",
        f"- 表数: {report_dict.get('table_count', 0)}",
        f"- thread 数: {report_dict.get('thread_count', 0)}",
        f"- checkpoint 数: {report_dict.get('checkpoint_count', 0)}",
        f"- 最早 checkpoint: {report_dict.get('oldest_checkpoint_ts')}",
        f"- 最新 checkpoint: {report_dict.get('newest_checkpoint_ts')}",
        "",
    ]
    if report_dict.get("warnings"):
        lines.append("## 警告")
        for w in report_dict["warnings"]:
            lines.append(f"- ⚠️ {w}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="CogCore SQLite 健康检查")
    parser.add_argument("--db", help="DB 路径 (默认找 cogcore_data/state.db)")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    parser.add_argument("--warn-mb", type=float, default=50.0, help="WARNING 阈值 (MB)")
    parser.add_argument("--crit-mb", type=float, default=200.0, help="CRITICAL 阈值 (MB)")
    parser.add_argument("--backup", help="同时执行 backup_to, 指定 backup 目录")
    parser.add_argument("--prune", action="store_true", help="执行 prune_checkpoints")
    parser.add_argument("--keep", type=int, default=100, help="prune 时每 thread 保留数")
    parser.add_argument("--vacuum", action="store_true", help="执行 vacuum")
    args = parser.parse_args()

    db_path = args.db or find_default_db()
    if not db_path:
        print("[!] 没找到 state.db, 用 --db 指定路径", file=sys.stderr)
        return 1

    if not os.path.exists(db_path):
        print(f"[!] DB 不存在: {db_path}", file=sys.stderr)
        return 1

    # 决定模式
    do_maintenance = bool(args.backup or args.prune or args.vacuum)
    if do_maintenance:
        if args.backup:
            r = backup_to(db_path, args.backup)
            print(f"[backup] {r.backup_path} ({r.bytes_copied} bytes, {r.duration_ms:.0f}ms)")
        if args.prune:
            r = prune_checkpoints(db_path, keep_last=args.keep)
            print(f"[prune] deleted {r.deleted_rows}, remaining {r.remaining_rows}, keep_last {r.keep_last}, {r.duration_ms:.0f}ms")
        if args.vacuum:
            r = vacuum(db_path)
            print(f"[vacuum] saved {r.saved_bytes} bytes ({r.before_bytes} -> {r.after_bytes}), {r.duration_ms:.0f}ms")

    # 健康检查
    report = health_check(db_path, warn_size_mb=args.warn_mb, crit_size_mb=args.crit_mb)
    d = report.to_dict()
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(d, db_path))

    # 退出码: CRITICAL -> 2, WARNING -> 1, OK -> 0
    if report.status == HealthStatus.CRITICAL:
        return 2
    if report.status == HealthStatus.WARNING:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
