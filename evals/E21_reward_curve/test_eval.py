from __future__ import annotations

import pytest

from evals.E21_reward_curve.eval import evaluate
from evals.protocol import make_report, write_report


pytestmark = pytest.mark.evals


def test_e21_reward_curve_eval(tmp_path):
    metrics = evaluate({"n_ticks": 50})
    assert metrics["paths_diverge"] is True
    assert metrics["score"] > 0
    report = make_report("E21_reward_curve", metrics, passed=True)
    path = write_report(report, reports_dir=str(tmp_path))
    assert path.endswith(".json")

