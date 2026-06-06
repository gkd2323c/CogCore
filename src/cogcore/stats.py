"""兼容入口: python -m cogcore.stats。

实际实现见 cogcore.sqlite_stats。
"""
from __future__ import annotations

import sys

from cogcore.sqlite_stats import main


if __name__ == "__main__":
    sys.exit(main())
