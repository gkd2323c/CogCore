"""M4.6 self-iteration A/B eval decision tests."""
from __future__ import annotations

import pytest

from cogcore.self_iteration import SelfIterateLoop


class FakeLoop:
    """Minimal stand-in for evaluate_after_change testing."""

    def __init__(self):
        self.logs: list[dict] = []

    def _log(self, payload: dict) -> None:
        self.logs.append(payload)

    evaluate_after_change = SelfIterateLoop.evaluate_after_change


def test_evaluate_accept_when_improved():
    loop = FakeLoop()
    decision = loop.evaluate_after_change(
        {"score": 0.5}, {"score": 0.7}, score_key="score"
    )
    assert decision == "accept"


def test_evaluate_revert_when_regressed():
    loop = FakeLoop()
    decision = loop.evaluate_after_change(
        {"score": 0.7}, {"score": 0.5}, score_key="score"
    )
    assert decision == "revert"


def test_evaluate_accept_when_unchanged():
    loop = FakeLoop()
    decision = loop.evaluate_after_change(
        {"score": 0.5}, {"score": 0.5}, score_key="score"
    )
    assert decision == "accept"


def test_evaluate_respects_min_improvement():
    loop = FakeLoop()
    # tiny regression below threshold -> still accept
    decision = loop.evaluate_after_change(
        {"score": 0.5}, {"score": 0.499}, score_key="score", min_improvement=0.01
    )
    assert decision == "accept"


def test_evaluate_logs_decision():
    loop = FakeLoop()
    loop.evaluate_after_change({"score": 0.5}, {"score": 0.3}, score_key="score")
    assert any(l.get("step") == "evaluate_after_change" for l in loop.logs)
    assert any(l.get("decision") == "revert" for l in loop.logs)


def test_evaluate_custom_key():
    loop = FakeLoop()
    decision = loop.evaluate_after_change(
        {"accuracy": 0.9}, {"accuracy": 0.95}, score_key="accuracy"
    )
    assert decision == "accept"
