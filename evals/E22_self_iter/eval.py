"""E22 self-iteration eval.

Compares no-op baseline against the existing self-iteration detection/rollback path.
"""
from __future__ import annotations

import tempfile
from typing import Any
from unittest.mock import MagicMock

from cogcore.self_iteration import Change, SelfIterateLoop
from cogcore.tools import ToolRegistry
from cogcore.tools_code import register_code_tools
from cogcore.tools_exec import register_exec_tools
from cogcore.tools_git import register_git_tools
from scripts.run_m37_experiments import make_synthetic_failure


SCENARIOS = ["logic_error", "type_error", "import_error"]


def _registry_for(kind: str) -> ToolRegistry:
    registry = ToolRegistry()
    register_code_tools(registry)
    register_git_tools(registry)
    register_exec_tools(registry)
    registry.register_tool("run_tests", make_synthetic_failure(registry, kind), {"path": "string"})
    registry.add_to_allowlist("run_tests")
    return registry


def _llm() -> MagicMock:
    llm = MagicMock()
    mr = MagicMock()
    mc = MagicMock()
    mc.content = "[auto-iterate] eval fix"
    mr.choices = [type("c", (), {"message": mc})()]
    llm.chat.completions.create.return_value = mr
    return llm


def evaluate(state: dict[str, Any] | None = None) -> dict[str, Any]:
    scenarios = (state or {}).get("scenarios", SCENARIOS)
    detected = 0
    rolled_back = 0
    cases = []

    for kind in scenarios:
        with tempfile.TemporaryDirectory(prefix=f"cogcore_eval_e22_{kind}_") as data_dir:
            loop = SelfIterateLoop(registry=_registry_for(kind), llm=_llm(), data_dir=data_dir)
            target = f"src/cogcore/_eval_e22_{kind}.py"
            loop.propose_change = lambda plan, sources, t=target: Change(
                target_file=t,
                new_content="# eval synthetic change\n",
                commit_message="[auto-iterate] eval synthetic rollback",
            )
            observation = loop.observe()
            gap = loop.detect_gap(observation)
            result = loop.run_once()
            is_detected = gap is not None
            is_rolled_back = bool(result.get("rolled_back"))
            detected += int(is_detected)
            rolled_back += int(is_rolled_back)
            cases.append(
                {
                    "scenario": kind,
                    "detected": is_detected,
                    "rolled_back": is_rolled_back,
                }
            )

    total = len(scenarios)
    score = round((detected + rolled_back) / (2 * total), 3) if total else 0.0
    return {
        "score": score,
        "total_scenarios": total,
        "detected": detected,
        "rolled_back": rolled_back,
        "detect_rate": round(detected / total, 3) if total else 0.0,
        "rollback_rate": round(rolled_back / total, 3) if total else 0.0,
        "cases": cases,
    }

