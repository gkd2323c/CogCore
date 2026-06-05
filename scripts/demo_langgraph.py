"""M0.5 演示脚本：通过 LangGraph StateGraph 跑多轮 invoke。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "$PWD\\src"
    python scripts/demo_langgraph.py
"""

from __future__ import annotations

import logging

from cogcore.action_system import ActionNode, ActionResult, ActionSource, ActionSystem, Outcome
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.graph import build_cogcore_graph, invoke_cogcore
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool

logging.basicConfig(level=logging.WARNING)


def fake_weather_executor(node):
    import random
    success = random.random() > 0.4
    return ActionResult(
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
        reward_signal=0.8 if success else -0.4,
    )


def main() -> None:
    pool = StatePool()
    hdb = HDB()
    cfs = CognitiveFeelingSystem()
    attention = Attention()
    nt_sys = NeurotransmitterSystem()
    action_sys = ActionSystem()
    action_sys.set_executor(fake_weather_executor)
    action_sys.register_node(ActionNode(
        name="weather_query", threshold=0.5, source=ActionSource.INNATE
    ))
    tuner = AdaptiveTuner()

    modules = {
        "pool": pool,
        "hdb": hdb,
        "cfs": cfs,
        "attention": attention,
        "nt_sys": nt_sys,
        "action_sys": action_sys,
        "tuner": tuner,
    }

    graph = build_cogcore_graph(modules)

    print("=" * 60)
    print("M0.5 LangGraph 集成演示：5 轮 invoke")
    print("=" * 60)

    thread_id = "demo-session-1"
    for tick in range(5):
        action_sys.set_tick(tick)
        result = invoke_cogcore(
            graph,
            raw_input=f"tick {tick} 的输入",
            tick=tick,
            thread_id=thread_id,
        )

        # 注意：在 LangGraph 中，新 invoke 的 raw_input 会覆盖旧的
        # 但 state 在 thread_id 下累积
        print(f"\n--- Tick {tick} ---")
        # stages_log 在同一 thread_id 下累积；只数最后 10 条
        recent_stages = result["stages_log"][-10:]
        print(f"  本轮阶段: {len(recent_stages)}/10, 累计 {len(result['stages_log'])} 条")
        print(f"  Pool: active={pool.get_energy_summary().active_count}, "
              f"pressure={pool.get_energy_summary().cognitive_pressure:.3f}, "
              f"total_e={pool.get_energy_summary().total_energy:.2f}")
        print(f"  NT: focus={nt_sys.current.focus:.3f}, "
              f"arousal={nt_sys.current.arousal:.3f}, "
              f"caution={nt_sys.current.caution:.3f}, "
              f"fatigue={nt_sys.current.fatigue:.3f}")
        print(f"  CFS: 历史={len(cfs.get_feeling_history())}, "
              f"上压={cfs.get_cfs_report()['last_pressure']:.3f}")
        print(f"  HDB: {hdb.get_hdb_report()['structure_count']} structures")
        print(f"  Action: total_executions={action_sys.get_action_report()['total_executions']}")
        print(f"  APT: last_reason={tuner.get_tuner_report()['last_reason']}")


if __name__ == "__main__":
    main()
