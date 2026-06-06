"""M4.3b sqlite-stats 报告 CLI。

用法:
    python scripts/stats_report.py
    python scripts/stats_report.py --db cogcore_data/stats.db --json
    python scripts/stats_report.py --incr ticks 1 --observe latency_ms 12.5
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cogcore.sqlite_stats import main


if __name__ == "__main__":
    sys.exit(main())
