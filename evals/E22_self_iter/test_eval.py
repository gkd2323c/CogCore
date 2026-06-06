from __future__ import annotations

import pytest

from evals.E22_self_iter.eval import evaluate
from evals.ab_harness import run_ab
from evals.protocol import make_report, write_report


pytestmark = pytest.mark.evals


def test_e22_self_iter_eval(tmp_path):
    metrics = evaluate({"scenarios": ["logic_error"]})
    assert metrics["detected"] == 1
    assert metrics["rolled_back"] == 1
    report = make_report("E22_self_iter", metrics, passed=True)
    path = write_report(report, reports_dir=str(tmp_path))
    assert path.endswith(".json")


def test_e22_ab_harness_detects_improvement():
    baseline = lambda state=None: {"score": 0.0, "detect_rate": 0.0}
    candidate = lambda state=None: {"score": 0.5, "detect_rate": 1.0}
    result = run_ab("E22_self_iter", baseline, candidate)
    assert result.improved is True
    assert result.diff["score"] == 0.5

