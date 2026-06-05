"""M1.1 端到端演示：CogCore tick → LLM prompt → LLM 回复 → 刺激元回注。

运行前提：Ollama 正在运行（http://localhost:11434），且模型可用。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "src"
    python scripts/demo_llm.py
"""

from __future__ import annotations

import logging
import sys

from cogcore.action_system import ActionNode, ActionSource, ActionSystem
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.config import get_config
from cogcore.graph import build_cogcore_graph, invoke_cogcore
from cogcore.hdb import HDB
from cogcore.llm_bridge import LLMBridge
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool

logging.basicConfig(level=logging.WARNING)


def _utf8():
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except Exception:
                pass


def main():
    _utf8()

    cfg = get_config()
    print(f"CogCore M1.1 Demo — LLM 桥接 ({cfg.llm.model})")
    print(f"API: {cfg.llm.endpoint}")
    print()

    # 1. 构造模块
    pool = StatePool()
    hdb = HDB()
    cfs = CognitiveFeelingSystem()
    attention = Attention()
    nt_sys = NeurotransmitterSystem()
    action_sys = ActionSystem()
    action_sys.register_node(ActionNode(
        name="query_weather", threshold=0.5, source=ActionSource.INNATE
    ))
    tuner = AdaptiveTuner()

    modules = {
        "pool": pool, "hdb": hdb, "cfs": cfs, "attention": attention,
        "nt_sys": nt_sys, "action_sys": action_sys, "tuner": tuner,
    }
    graph = build_cogcore_graph(modules)

    # 2. LLM Bridge
    bridge = LLMBridge()

    # 3. 多轮对话
    inputs = [
        "北京 明天 天气",
        "需要 带伞 吗",
    ]

    thread_id = "demo-m1-1"
    for tick, text in enumerate(inputs):
        print(f"\n{'='*60}")
        print(f"Tick {tick}: User >> {text}")
        print(f"{'='*60}")

        # Step A: CogCore cognitive tick
        state = invoke_cogcore(graph, raw_input=text, tick=tick, thread_id=thread_id)

        stages = state.get("stages_log", [])
        print(f"  CogCore stages: {len(stages)}/10 completed")
        print(f"  Pool: {pool.get_energy_summary().total_energy:.2f}e, "
              f"pressure={pool.get_energy_summary().cognitive_pressure:.2f}")
        print(f"  NT: arousal={nt_sys.current.arousal:.2f}, "
              f"caution={nt_sys.current.caution:.2f}")

        # Step B: Build context packet
        packet = bridge.build_context_packet(state, max_tokens=1000)
        print(f"\n  Context packet ({len(packet)} chars):")

        # Step C: Call LLM
        print(f"\n  >> LLM {cfg.llm.model} ...")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. The user's input has been processed through "
                    "a cognitive state system. Respond naturally based on the context provided."
                ),
            },
            {"role": "user", "content": packet},
        ]
        response = bridge.chat(messages)
        print(f"\n  LLM >> {response}")

        # Step D: Parse LLM output back into CogCore
        atoms = bridge.parse_llm_output(response)
        if atoms:
            for a in atoms[:5]:
                pool.add(a)
            print(f"\n  ↻ {len(atoms)} stimulus atoms injected back to state pool")

        print()

    print("Demo complete.")


if __name__ == "__main__":
    main()
