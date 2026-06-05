"""CogCore CLI 入口。

M0.1 阶段：跑通一次完整 tick，输出 10 阶段的「待实现」日志。
用法：
    python -m cogcore.main "明天上海出门，帮我看看要不要带伞"
"""

from __future__ import annotations

import argparse
import logging
import sys

from cogcore.pipeline import run_cycle


def _ensure_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，强制改为 UTF-8 让中文日志正确显示。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="CogCore 认知内核 M0.1 骨架")
    parser.add_argument(
        "input",
        nargs="?",
        default="明天上海出门，帮我看看要不要带伞",
        help="外源输入文本（默认示例）",
    )
    parser.add_argument(
        "--modality",
        default="text",
        help="输入模态（默认 text）",
    )
    parser.add_argument(
        "--tick",
        type=int,
        default=0,
        help="全局 tick 计数（默认 0）",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="详细日志",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    print(f"CogCore M0.1 骨架 — 跑一次完整 tick")
    print(f"输入: {args.input!r} (modality={args.modality})")
    print()

    report = run_cycle(
        raw_input=args.input,
        modality=args.modality,
        tick=args.tick,
    )

    print()
    print(f"=== Tick {report.tick} 报告 ===")
    print(f"完成阶段: {len(report.stages_completed)}/10")
    for i, stage in enumerate(report.stages_completed, 1):
        print(f"  {i:2}. {stage}")
    print()
    print("注意：M0.1 阶段每个模块内部方法都 raise NotImplementedError")
    print("      骨架已跑通 10 阶段调度；M0.2-M0.8 逐模块实现。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
