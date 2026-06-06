"""M4.4 eval protocol unit tests."""
from __future__ import annotations

import json
from pathlib import Path

from evals.ab_harness import numeric_diff, run_ab, write_ab_report
from evals.protocol import make_report, write_report


def test_numeric_diff_only_numeric_keys():
    diff = numeric_diff(
        {"score": 0.2, "name": "baseline", "count": 2},
        {"score": 0.7, "name": "candidate", "count": 3},
    )
    assert diff == {"score": 0.5, "count": 1.0}


def test_run_ab_marks_non_regression_improved():
    baseline = lambda state=None: {"score": 0.5}
    candidate = lambda state=None: {"score": 0.5}
    result = run_ab("demo", baseline, candidate)
    assert result.improved is True
    assert result.diff["score"] == 0.0


def test_write_report_json(tmp_path):
    report = make_report("demo_eval", {"score": 1.0}, passed=True)
    path = write_report(report, reports_dir=str(tmp_path))
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["name"] == "demo_eval"
    assert payload["passed"] is True


def test_write_report_includes_diff_vs_last(tmp_path):
    first = make_report("demo_eval", {"score": 0.25, "count": 1}, passed=True)
    write_report(first, reports_dir=str(tmp_path))
    second = make_report("demo_eval", {"score": 0.75, "count": 2}, passed=True)
    path = write_report(second, reports_dir=str(tmp_path))
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["diff_vs_last"] == {"score": 0.5, "count": 1.0}


def test_write_ab_report_json(tmp_path):
    result = run_ab(
        "demo_ab",
        lambda state=None: {"score": 0.1},
        lambda state=None: {"score": 0.4},
    )
    path = write_ab_report(result, reports_dir=str(tmp_path))
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["name"] == "demo_ab"
    assert payload["improved"] is True
