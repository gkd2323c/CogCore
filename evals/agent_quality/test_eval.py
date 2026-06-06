from __future__ import annotations

import pytest

from evals.agent_quality.eval import evaluate, score_response
from evals.protocol import make_report, write_report


pytestmark = pytest.mark.evals


def test_agent_quality_score_response():
    assert score_response("counter gauge histogram", ["counter", "histogram"]) >= 0.7
    assert score_response("", ["counter"]) == 0.0


def test_agent_quality_eval(tmp_path):
    metrics = evaluate()
    assert metrics["score"] >= 0.7
    assert metrics["case_count"] >= 1
    report = make_report("agent_quality", metrics, passed=True)
    path = write_report(report, reports_dir=str(tmp_path))
    assert path.endswith(".json")
