"""Agent quality eval.

This is intentionally local and deterministic by default. A future provider can
swap score_response() for an Ollama judge without changing the eval protocol.
"""
from __future__ import annotations

from typing import Any


DEFAULT_CASES = [
    {
        "prompt": "hello",
        "response": "Hello. I can help with CogCore status, docs, and code tasks.",
        "must_include": ["help"],
    },
    {
        "prompt": "what changed?",
        "response": "The sqlite-stats module adds counter, gauge, and histogram metrics.",
        "must_include": ["sqlite-stats", "counter", "histogram"],
    },
]


def score_response(response: str, must_include: list[str]) -> float:
    if not response.strip():
        return 0.0
    hits = sum(1 for term in must_include if term.lower() in response.lower())
    coverage = hits / max(1, len(must_include))
    length_ok = 1.0 if 10 <= len(response) <= 800 else 0.5
    return round((coverage * 0.8) + (length_ok * 0.2), 3)


def evaluate(state: dict[str, Any] | None = None) -> dict[str, Any]:
    cases = (state or {}).get("cases", DEFAULT_CASES)
    scored = []
    for case in cases:
        score = score_response(case.get("response", ""), case.get("must_include", []))
        scored.append({**case, "score": score})
    avg = round(sum(c["score"] for c in scored) / len(scored), 3) if scored else 0.0
    return {
        "score": avg,
        "case_count": len(scored),
        "pass_rate": round(sum(1 for c in scored if c["score"] >= 0.7) / len(scored), 3)
        if scored
        else 0.0,
        "cases": scored,
    }

