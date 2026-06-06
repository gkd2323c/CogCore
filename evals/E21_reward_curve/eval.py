"""E21 reward-curve eval.

Measures whether different reward schedules still produce divergent NT paths.
"""
from __future__ import annotations

from typing import Any

from cogcore.nt import NeurotransmitterSystem
from scripts.run_m37_experiments import make_reward_schedule


SCHEDULES = ["linear_asc", "plateau_spike", "inverse_u", "punishment_first", "random"]


def evaluate(state: dict[str, Any] | None = None) -> dict[str, Any]:
    n_ticks = int((state or {}).get("n_ticks", 100))
    final_states: dict[str, dict[str, float]] = {}
    for schedule in SCHEDULES:
        nt = NeurotransmitterSystem()
        for tick, reward in enumerate(make_reward_schedule(schedule, n_ticks)):
            nt.set_tick(tick)
            nt.update([], [reward], {"reward_signal": reward})
        final_states[schedule] = {
            "focus": round(nt.current.focus, 3),
            "arousal": round(nt.current.arousal, 3),
            "caution": round(nt.current.caution, 3),
            "exploration": round(nt.current.exploration, 3),
            "fatigue": round(nt.current.fatigue, 3),
            "stability": round(nt.current.stability, 3),
        }

    arousal_values = [v["arousal"] for v in final_states.values()]
    caution_values = [v["caution"] for v in final_states.values()]
    arousal_range = round(max(arousal_values) - min(arousal_values), 3)
    caution_range = round(max(caution_values) - min(caution_values), 3)
    score = round(arousal_range + caution_range, 3)
    return {
        "score": score,
        "n_ticks": n_ticks,
        "schedules": len(SCHEDULES),
        "arousal_range": arousal_range,
        "caution_range": caution_range,
        "paths_diverge": arousal_range > 0.1 or caution_range > 0.1,
        "final_states": final_states,
    }

