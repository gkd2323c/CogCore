"""M0.3 演示脚本：跑三轮 run_cycle 看行动评估 + 教师反馈延迟合流。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "$PWD\\src"
    python scripts/demo_action.py
"""

from __future__ import annotations

import logging
import random

from cogcore.action_system import ActionResult, ActionSystem, Outcome
from cogcore.hdb import HDB
from cogcore.nt import NTModulations
from cogcore.pipeline import run_cycle
from cogcore.state_pool import StatePool
from cogcore.types import ActionNode, ActionSource

logging.basicConfig(level=logging.WARNING)


def fake_weather_executor(node: ActionNode) -> ActionResult:
    """假的天气查询执行器：50% 概率成功。"""
    success = random.random() > 0.5
    return ActionResult(
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
        reward_signal=0.8 if success else -0.4,
        feedback_text="查天气完成" if success else "网络超时",
    )


def main() -> None:
    pool = StatePool()
    hdb = HDB()
    action_sys = ActionSystem()
    action_sys.set_executor(fake_weather_executor)

    # 注册两个行动节点
    weather_node = ActionNode(
        name="weather_query",
        threshold=0.5,
        source=ActionSource.INNATE,
    )
    smalltalk_node = ActionNode(
        name="smalltalk",
        threshold=0.5,
        source=ActionSource.LEARNED,
    )
    action_sys.register_node(weather_node)
    action_sys.register_node(smalltalk_node)

    print("=" * 60)
    print("初始状态")
    print("=" * 60)
    names = [n.name for n in [weather_node, smalltalk_node]]
    print(f"  行动节点: {names}")
    print(f"  action report: {action_sys.get_action_report()}")

    for tick in range(3):
        print()
        print("=" * 60)
        print(f"Tick {tick}")
        print("=" * 60)

        # 模拟"上一轮反馈"：先 queue 一条教师反馈
        if tick > 0:
            # 模拟教师对上一轮行动的反馈
            action_sys.queue_teacher_feedback({
                "reward_signal": 0.6 if tick % 2 == 0 else -0.3,
                "anchor_note": f"after tick {tick - 1}",
                "explanation": "good timing" if tick % 2 == 0 else "too early",
            })
            print(f"  [tick {tick} 开始] 合并 {len(action_sys._feedback_queue)} 条教师反馈")
            merged = action_sys.merge_pending_teacher_feedback()
            print(f"    合并后: {[(m.reward_signal, m.anchor_note) for m in merged]}")
            # 把合并后的反馈写入相应节点
            for fb in merged:
                if fb.reward_signal > 0:
                    weather_node.reward_history.append(fb.reward_signal)
                else:
                    weather_node.punishment_history.append(fb.reward_signal)

        report = run_cycle(
            raw_input=f"tick {tick} 的输入",
            modality="text",
            tick=tick,
            pool=pool,
            hdb=hdb,
            action_sys=action_sys,
        )

        print(f"  完成阶段: {len(report.stages_completed)}/10")
        print(f"  action report: {action_sys.get_action_report()}")
        print(f"  池中行动 atoms: {[a.content for a in pool.get_all() if a.source.value == 'action']}")

    print()
    print("=" * 60)
    print("最终状态")
    print("=" * 60)
    print(f"  weather_node: drive={weather_node.drive:.3f}, "
          f"execution_count={weather_node.execution_count}, "
          f"reward_count={len(weather_node.reward_history)}, "
          f"punishment_count={len(weather_node.punishment_history)}")
    print(f"  smalltalk_node: drive={smalltalk_node.drive:.3f}, "
          f"execution_count={smalltalk_node.execution_count}")


if __name__ == "__main__":
    main()
