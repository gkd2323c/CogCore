"""M4.3b sqlite-stats (L8)。

轻量级 SQLite 度量存储，不引入 Prometheus / Grafana 等外部服务。

提供三种 primitive:
  - counter: 单调递增计数，适合 tick_count / error_count
  - gauge: 当前值，适合 active_atoms / pressure
  - histogram: 分布样本，适合 duration_ms / queue_depth

CLI:
    python -m cogcore.sqlite_stats --db cogcore_data/stats.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Any


DEFAULT_STATS_DB = "cogcore_data/stats.db"


@dataclass
class StatsReport:
    """sqlite-stats 报告。"""

    db_path: str
    counters: dict[str, dict[str, float | int]]
    gauges: dict[str, dict[str, float | int]]
    histograms: dict[str, dict[str, float | int]]
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "counters": self.counters,
            "gauges": self.gauges,
            "histograms": self.histograms,
            "timestamp": self.timestamp,
        }


class StatsDB:
    """SQLite-backed metrics store."""

    def __init__(self, path: str = DEFAULT_STATS_DB) -> None:
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def __enter__(self) -> "StatsDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS counter (
                name TEXT NOT NULL,
                value REAL NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_counter_name_ts
                ON counter(name, ts);

            CREATE TABLE IF NOT EXISTS gauge (
                name TEXT NOT NULL,
                value REAL NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gauge_name_ts
                ON gauge(name, ts);

            CREATE TABLE IF NOT EXISTS histogram (
                name TEXT NOT NULL,
                value REAL NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_histogram_name_value
                ON histogram(name, value);
            """
        )
        self.conn.commit()

    def incr(self, name: str, value: float = 1) -> None:
        """增加 counter。

        counter 只接受非负值。总值在 report() 中用 SUM(value) 得到。
        """
        if value < 0:
            raise ValueError(f"counter increment must be >= 0, got {value}")
        self.conn.execute(
            "INSERT INTO counter(name, value, ts) VALUES (?, ?, ?)",
            (name, float(value), time.time()),
        )
        self.conn.commit()

    def set(self, name: str, value: float) -> None:
        """设置 gauge 当前值。历史值保留用于审计，report() 取最新值。"""
        self.conn.execute(
            "INSERT INTO gauge(name, value, ts) VALUES (?, ?, ?)",
            (name, float(value), time.time()),
        )
        self.conn.commit()

    def observe(self, name: str, value: float) -> None:
        """记录 histogram 样本。"""
        self.conn.execute(
            "INSERT INTO histogram(name, value, ts) VALUES (?, ?, ?)",
            (name, float(value), time.time()),
        )
        self.conn.commit()

    def _counter_report(self) -> dict[str, dict[str, float | int]]:
        rows = self.conn.execute(
            """
            SELECT name, SUM(value) AS value, COUNT(*) AS samples, MIN(ts) AS first_ts,
                   MAX(ts) AS last_ts
            FROM counter
            GROUP BY name
            ORDER BY name
            """
        ).fetchall()
        return {
            row["name"]: {
                "value": _clean_number(row["value"]),
                "samples": row["samples"],
                "first_ts": row["first_ts"],
                "last_ts": row["last_ts"],
            }
            for row in rows
        }

    def _gauge_report(self) -> dict[str, dict[str, float | int]]:
        rows = self.conn.execute(
            """
            WITH ranked AS (
                SELECT name, value, ts,
                       ROW_NUMBER() OVER (PARTITION BY name ORDER BY ts DESC, rowid DESC) AS rn,
                       COUNT(*) OVER (PARTITION BY name) AS samples
                FROM gauge
            )
            SELECT name, value, ts AS updated_ts, samples
            FROM ranked
            WHERE rn = 1
            ORDER BY name
            """
        ).fetchall()
        return {
            row["name"]: {
                "value": _clean_number(row["value"]),
                "samples": row["samples"],
                "updated_ts": row["updated_ts"],
            }
            for row in rows
        }

    def _histogram_report(self) -> dict[str, dict[str, float | int]]:
        rows = self.conn.execute(
            """
            WITH ranked AS (
                SELECT name, value,
                       ROW_NUMBER() OVER (PARTITION BY name ORDER BY value) AS rn,
                       COUNT(*) OVER (PARTITION BY name) AS n
                FROM histogram
            ),
            pct AS (
                SELECT name,
                       MIN(CASE WHEN rn >= CAST(n * 0.50 + 0.999999 AS INT) THEN value END) AS p50,
                       MIN(CASE WHEN rn >= CAST(n * 0.95 + 0.999999 AS INT) THEN value END) AS p95,
                       MIN(CASE WHEN rn >= CAST(n * 0.99 + 0.999999 AS INT) THEN value END) AS p99
                FROM ranked
                GROUP BY name
            ),
            base AS (
                SELECT name, COUNT(*) AS count, MIN(value) AS min, MAX(value) AS max,
                       AVG(value) AS avg, MIN(ts) AS first_ts, MAX(ts) AS last_ts
                FROM histogram
                GROUP BY name
            )
            SELECT base.name, count, min, max, avg, p50, p95, p99, first_ts, last_ts
            FROM base
            JOIN pct ON pct.name = base.name
            ORDER BY base.name
            """
        ).fetchall()
        return {
            row["name"]: {
                "count": row["count"],
                "min": _clean_number(row["min"]),
                "max": _clean_number(row["max"]),
                "avg": round(row["avg"], 6),
                "p50": _clean_number(row["p50"]),
                "p95": _clean_number(row["p95"]),
                "p99": _clean_number(row["p99"]),
                "first_ts": row["first_ts"],
                "last_ts": row["last_ts"],
            }
            for row in rows
        }

    def report(self) -> dict[str, Any]:
        """返回 JSON-safe report dict。"""
        return StatsReport(
            db_path=self.path,
            counters=self._counter_report(),
            gauges=self._gauge_report(),
            histograms=self._histogram_report(),
            timestamp=time.time(),
        ).to_dict()

    def report_markdown(self) -> str:
        """返回 Markdown 报告。"""
        return report_markdown(self.report())


def _clean_number(value: float | int | None) -> float | int | None:
    """把 5.0 这类值显示为 5，报告更易读。"""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def report_markdown(report: dict[str, Any]) -> str:
    """把 report dict 渲染为 Markdown。"""
    lines = [
        f"# CogCore sqlite-stats — {report.get('db_path', '?')}",
        "",
        f"**时间**: {report.get('timestamp', 0):.0f}",
        "",
        "## Counters",
        "",
    ]
    counters = report.get("counters", {})
    if counters:
        lines.extend(["| Name | Value | Samples |", "|------|-------|---------|"])
        for name, data in counters.items():
            lines.append(f"| `{name}` | {data['value']} | {data['samples']} |")
    else:
        lines.append("_No counters._")

    lines.extend(["", "## Gauges", ""])
    gauges = report.get("gauges", {})
    if gauges:
        lines.extend(["| Name | Value | Samples |", "|------|-------|---------|"])
        for name, data in gauges.items():
            lines.append(f"| `{name}` | {data['value']} | {data['samples']} |")
    else:
        lines.append("_No gauges._")

    lines.extend(["", "## Histograms", ""])
    histograms = report.get("histograms", {})
    if histograms:
        lines.extend(
            [
                "| Name | Count | Avg | Min | P50 | P95 | P99 | Max |",
                "|------|-------|-----|-----|-----|-----|-----|-----|",
            ]
        )
        for name, data in histograms.items():
            lines.append(
                f"| `{name}` | {data['count']} | {data['avg']} | {data['min']} | "
                f"{data['p50']} | {data['p95']} | {data['p99']} | {data['max']} |"
            )
    else:
        lines.append("_No histograms._")

    lines.append("")
    return "\n".join(lines)


def _ensure_utf8_stdout() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="CogCore sqlite-stats report")
    parser.add_argument("--db", default=DEFAULT_STATS_DB, help="stats DB 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    parser.add_argument("--incr", nargs=2, metavar=("NAME", "VALUE"), help="增加 counter")
    parser.add_argument("--set", nargs=2, metavar=("NAME", "VALUE"), help="设置 gauge")
    parser.add_argument("--observe", nargs=2, metavar=("NAME", "VALUE"), help="记录 histogram")
    args = parser.parse_args(argv)

    with StatsDB(args.db) as db:
        if args.incr:
            db.incr(args.incr[0], float(args.incr[1]))
        if args.set:
            db.set(args.set[0], float(args.set[1]))
        if args.observe:
            db.observe(args.observe[0], float(args.observe[1]))

        report = db.report()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(report_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
