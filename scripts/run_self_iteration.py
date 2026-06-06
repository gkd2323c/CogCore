"""M3.6 自迭代元循环 CLI 入口。

用法:
    python -m scripts.run_self_iteration --dry-run
    python -m scripts.run_self_iteration --once
    python -m scripts.run_self_iteration --interval 60  # 每 60s 跑一次
    python -m scripts.run_self_iteration --loop  # 一直跑, 每 5min 一次
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="CogCore self-iteration meta-loop")
    parser.add_argument("--dry-run", action="store_true", help="只生成 plan + change, 不真改")
    parser.add_argument("--once", action="store_true", help="跑一次就退出")
    parser.add_argument("--interval", type=int, default=300, help="循环模式间隔秒数")
    parser.add_argument("--loop", action="store_true", help="持续循环")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    parser.add_argument("--data-dir", default="cogcore_data", help="数据目录")
    args = parser.parse_args()

    from cogcore.self_iteration import SelfIterateLoop
    from cogcore.tools import ToolRegistry
    from cogcore.tools_code import register_code_tools
    from cogcore.tools_git import register_git_tools
    from cogcore.tools_exec import register_exec_tools

    # 构造 registry (注入 M3.5 工具)
    registry = ToolRegistry()
    register_code_tools(registry)
    register_git_tools(registry)
    register_exec_tools(registry)

    # LLM 桥接 (用配置)
    from cogcore.llm_bridge import LLMBridge
    try:
        llm = LLMBridge()
        logger.info("LLM bridge initialized from config")
    except Exception as e:
        logger.warning(f"LLM bridge failed: {e}, using mock")
        from unittest.mock import MagicMock
        from cogcore.llm_bridge import LLMBridge
        mock = MagicMock()
        mr = MagicMock()
        mc = MagicMock()
        mc.content = "[auto-iterate] mock fix"
        mr.choices = [type("c", (), {"message": mc})()]
        mock.chat.completions.create.return_value = mr
        llm = LLMBridge(client=mock)

    loop = SelfIterateLoop(
        registry=registry,
        llm=llm,
        project_root=args.project_root,
        data_dir=args.data_dir,
    )

    if args.once or args.dry_run:
        result = loop.run_once(dry_run=args.dry_run)
        print("\n=== Result ===")
        for k, v in result.items():
            if k in ("plan", "change") and isinstance(v, dict):
                print(f"  {k}:")
                for k2, v2 in v.items():
                    s = str(v2)[:200]
                    print(f"    {k2}: {s}")
            else:
                print(f"  {k}: {v}")
        return

    if args.loop:
        logger.info(f"Looping every {args.interval}s (Ctrl+C to stop)")
        try:
            while True:
                logger.info("Running self-iteration cycle...")
                result = loop.run_once(dry_run=False)
                logger.info(f"Cycle result: {list(result.keys())}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        return

    # 默认: 跑一次 dry-run
    logger.info("No mode specified, running --dry-run --once")
    result = loop.run_once(dry_run=True)
    print("\n=== Dry-Run Result ===")
    for k, v in result.items():
        if k in ("plan", "change") and isinstance(v, dict):
            print(f"  {k}:")
            for k2, v2 in v.items():
                print(f"    {k2}: {str(v2)[:200]}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
