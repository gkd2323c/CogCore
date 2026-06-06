"""M4.4 baseline-vs-candidate A/B harness."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable


EvalCallable = Callable[[dict[str, Any] | None], dict[str, Any]]


@dataclasses.dataclass
class ABResult:
    """Result of paired baseline/candidate evaluation."""

    name: str
    baseline: dict[str, Any]
    candidate: dict[str, Any]
    diff: dict[str, float]
    improved: bool
    score_key: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def numeric_diff(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, float]:
    """Return candidate - baseline for numeric keys present in both dicts."""
    out: dict[str, float] = {}
    for key, b_value in baseline.items():
        c_value = candidate.get(key)
        if isinstance(b_value, (int, float)) and isinstance(c_value, (int, float)):
            out[key] = round(float(c_value) - float(b_value), 6)
    return out


def run_ab(
    name: str,
    baseline_eval: EvalCallable,
    candidate_eval: EvalCallable,
    *,
    baseline_state: dict[str, Any] | None = None,
    candidate_state: dict[str, Any] | None = None,
    score_key: str = "score",
) -> ABResult:
    baseline = baseline_eval(baseline_state)
    candidate = candidate_eval(candidate_state)
    diff = numeric_diff(baseline, candidate)
    improved = diff.get(score_key, 0.0) >= 0.0
    return ABResult(
        name=name,
        baseline=baseline,
        candidate=candidate,
        diff=diff,
        improved=improved,
        score_key=score_key,
    )


def write_ab_report(result: ABResult, reports_dir: str = "evals/reports") -> str:
    out_dir = Path(reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.name}-ab.json"
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return str(path)

