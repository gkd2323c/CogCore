"""Shared eval protocol helpers for M4.4."""
from __future__ import annotations

import dataclasses
import datetime
import json
from pathlib import Path
from typing import Any, Callable


MetricFn = Callable[[dict[str, Any] | None], dict[str, Any]]


@dataclasses.dataclass
class EvalReport:
    """JSON-safe eval report."""

    name: str
    metrics: dict[str, Any]
    passed: bool
    timestamp: str
    notes: list[str]
    diff_vs_last: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def make_report(
    name: str,
    metrics: dict[str, Any],
    *,
    passed: bool,
    notes: list[str] | None = None,
    diff_vs_last: dict[str, float] | None = None,
) -> EvalReport:
    return EvalReport(
        name=name,
        metrics=metrics,
        passed=passed,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        notes=notes or [],
        diff_vs_last=diff_vs_last or {},
    )


def write_report(report: EvalReport, reports_dir: str = "evals/reports") -> str:
    """Write an eval report as evals/reports/<name>-YYYY-MM-DD.json."""
    out_dir = Path(reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    previous = latest_report(report.name, reports_dir=str(out_dir))
    if previous is not None:
        report.diff_vs_last = numeric_metric_diff(
            previous.get("metrics", {}),
            report.metrics,
        )
    date = datetime.date.today().isoformat()
    path = out_dir / f"{report.name}-{date}.json"
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return str(path)


def latest_report(name: str, reports_dir: str = "evals/reports") -> dict[str, Any] | None:
    """Read the latest existing report for name, if any."""
    out_dir = Path(reports_dir)
    if not out_dir.exists():
        return None
    candidates = sorted(out_dir.glob(f"{name}-*.json"))
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def numeric_metric_diff(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, float]:
    """Return current - previous for top-level numeric metric keys."""
    diff: dict[str, float] = {}
    for key, old_value in previous.items():
        new_value = current.get(key)
        if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
            diff[key] = round(float(new_value) - float(old_value), 6)
    return diff
