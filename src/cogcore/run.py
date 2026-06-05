"""CogCore CLI 入口（M0.5 LangGraph 集成版）。

用法：
    python -m cogcore.run "明天上海出门，帮我看看要不要带伞"

与 cogcore.main（M0.1 手动版）不同：
- 使用 LangGraph StateGraph
- in-memory checkpointer（MemorySaver）
- 支持多次 invoke 累积 state
"""

from __future__ import annotations

import argparse
import logging
import sys

from cogcore.action_system import ActionNode, ActionResult, ActionSource, ActionSystem, Outcome
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.graph import build_cogcore_graph, invoke_cogcore
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool


def _ensure_utf8_stdout() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass


def _fake_weather_executor(node) -> ActionResult:
    """假的天气查询执行器（50% 成功）。"""
    import random
    success = random.random() > 0.5
    return ActionResult(
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
        reward_signal=0.8 if success else -0.4,
        feedback_text="查天气完成" if success else "网络超时",
    )


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="CogCore M0.5 LangGraph 集成版")
    parser.add_argument(
        "input",
        nargs="?",
        default="明天上海出门，帮我看看要不要带伞",
        help="外源输入文本",
    )
    parser.add_argument("--modality", default="text", help="输入模态")
    parser.add_argument("--tick", type=int, default=0, help="全局 tick 计数")
    parser.add_argument("--thread-id", default="default", help="会话 ID（checkpointer 用）")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="详细日志"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # 构造模块
    pool = StatePool()
    hdb = HDB()
    cfs = CognitiveFeelingSystem()
    attention = Attention()
    nt_sys = NeurotransmitterSystem()
    action_sys = ActionSystem()
    action_sys.set_executor(_fake_weather_executor)
    action_sys.register_node(ActionNode(
        name="weather_query", threshold=0.5, source=ActionSource.INNATE,
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

    # 编译图
    graph = build_cogcore_graph(modules)
    print(f"CogCore M0.5 (LangGraph 集成版)")
    print(f"输入: {args.input!r} (modality={args.modality})")
    print(f"thread_id={args.thread_id}, tick={args.tick}")
    print()

    # 调用
    result = invoke_cogcore(
        graph,
        raw_input=args.input,
        tick=args.tick,
        thread_id=args.thread_id,
        modality=args.modality,
    )

    # 输出报告
    print(f"=== Tick {result['tick']} 报告 ===")
    print(f"完成阶段: {len(result['stages_log'])}/10")
    for i, stage in enumerate(result['stages_log'], 1):
        print(f"  {i:2}. {stage}")
    print()
    print(f"StatePool: active={pool.get_energy_summary().active_count}, "
          f"total_e={pool.get_energy_summary().total_energy:.2f}, "
          f"pressure={pool.get_energy_summary().cognitive_pressure:.3f}")
    print(f"HDB: {hdb.get_hdb_report()['structure_count']} structures, "
          f"{hdb.get_hdb_report()['episodic_count']} episodic")
    print(f"NT: arousal={nt_sys.current.arousal:.3f}, "
          f"caution={nt_sys.current.caution:.3f}")
    print(f"Action: total_executions={action_sys.get_action_report()['total_executions']}")
    print(f"APT: last_reason={tuner.get_tuner_report()['last_reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
