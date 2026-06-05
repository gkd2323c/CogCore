"""M0.4 演示脚本：跑 5 轮 run_cycle 看 CFS + NT + Attention + AdaptiveTuner 调制。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "$PWD\\src"
    python scripts/demo_modulation.py
"""

from __future__ import annotations

import logging
import random

from cogcore.action_system import ActionResult, ActionSystem, Outcome
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.pipeline import run_cycle
from cogcore.state_pool import StatePool
from cogcore.types import ActionNode, ActionSource

logging.basicConfig(level=logging.WARNING)


def fake_weather_executor(node):
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
    tuner = AdaptiveTuner()
    action_sys = ActionSystem()
    action_sys.set_executor(fake_weather_executor)
    action_sys.register_node(ActionNode(
        name="weather_query", threshold=0.5, source=ActionSource.INNATE
    ))

    print("=" * 60)
    print("M0.4 演示：5 轮调制循环")
    print("=" * 60)

    for tick in range(5):
        action_sys.set_tick(tick)
        report = run_cycle(
            raw_input=f"tick {tick} 输入",
            modality="text",
            tick=tick,
            pool=pool,
            hdb=hdb,
            cfs=cfs,
            attention=attention,
            nt_sys=nt_sys,
            tuner=tuner,
            action_sys=action_sys,
        )

        print(f"\n--- Tick {tick} ---")
        print(f"  Pool 状态:")
        print(f"    active={pool.get_energy_summary().active_count}, "
              f"pressure={pool.get_energy_summary().cognitive_pressure:.3f}, "
              f"total_e={pool.get_energy_summary().total_energy:.2f}")
        print(f"  NT 调制: focus={nt_sys.current.focus:.3f}, "
              f"arousal={nt_sys.current.arousal:.3f}, "
              f"caution={nt_sys.current.caution:.3f}, "
              f"fatigue={nt_sys.current.fatigue:.3f}")
        print(f"  CFS: 历史信号数={len(cfs.get_feeling_history())}, "
              f"上次压力={cfs.get_cfs_report()['last_pressure']:.3f}")
        if attention._last_cam:
            print(f"  Attention: CAM size={len(attention._last_cam.items)}, "
                  f"top_score={max(attention._last_cam.scores.values()):.3f}")
        print(f"  APT: tick={tuner.get_tuner_report()['tick_count']}, "
              f"last_reason={tuner.get_tuner_report()['last_reason']}")


if __name__ == "__main__":
    main()
