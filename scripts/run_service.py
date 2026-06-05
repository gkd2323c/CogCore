"""CogCore 后台服务启动脚本。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "src"
    python scripts/run_service.py          # 后台模式（自动 tick）
    python scripts/run_service.py --no-bg  # 手动 tick 模式
    python scripts/run_service.py --ticks 10  # 跑 10 个 tick 后退出
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time


def _utf8():
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except Exception:
                pass


def main() -> int:
    _utf8()
    parser = argparse.ArgumentParser(description="CogCore 后台服务")
    parser.add_argument("--no-bg", action="store_true", help="不启动后台 tick，手动触发")
    parser.add_argument("--ticks", type=int, default=0, help="运行 N 个 tick 后自动退出（0=持续运行）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from cogcore.service import CogCoreService

    service = CogCoreService(config_path=args.config)

    if args.no_bg:
        service.config.service.tick_interval = 0

    def on_sigint(sig, frame):
        print("\nShutting down...")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)

    print(f"CogCore Service v0.1")
    print(f"  Data dir: {service.config.service.data_dir}")
    print(f"  Tick interval: {service.config.service.tick_interval}s")
    print(f"  Persistence: SQLite")

    service.start()

    if args.ticks > 0:
        print(f"\nRunning {args.ticks} ticks...")
        for i in range(args.ticks):
            service.tick()
            status = service.get_status()
            print(f"  Tick {i+1}: pool={status['pool']['active']}a "
                  f"pressure={status['pool']['pressure']:.2f} "
                  f"nt=a={status['nt']['arousal']:.2f}/c={status['nt']['caution']:.2f}")
        service.stop()
        print("Done.")
    else:
        print("\nService running. Press Ctrl+C to stop.")
        try:
            while service.running:
                time.sleep(1)
        except KeyboardInterrupt:
            service.stop()
            print("\nStopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
