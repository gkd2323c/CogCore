"""M0.2 演示脚本：跑两次 run_cycle 看 StatePool + HDB 的实际计算。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "$PWD\\src"
    python scripts/demo_run.py
"""

from __future__ import annotations

import logging

from cogcore.hdb import HDB
from cogcore.pipeline import run_cycle
from cogcore.state_pool import StatePool

logging.basicConfig(level=logging.WARNING)


def main() -> None:
    pool = StatePool()
    hdb = HDB()

    # === Tick 0：第一次输入 ===
    print("=" * 60)
    print("Tick 0 — 第一次输入 '明天 上海 出门'")
    print("=" * 60)
    run_cycle(
        raw_input="明天 上海 出门",
        modality="text",
        tick=0,
        pool=pool,
        hdb=hdb,
    )

    print(f"  池中原子: {[a.content for a in pool.get_all()]}")
    print(f"  池能量: real={pool.get_energy_summary().real_energy}, "
          f"virtual={pool.get_energy_summary().virtual_energy}, "
          f"cognitive_pressure={pool.get_energy_summary().cognitive_pressure:.2f}")
    print(f"  HDB 结构数: {len(hdb._structures)}")
    print(f"  HDB hit_count: {[s.energy_stats.hit_count for s in hdb._structures.values()]}")

    # === Tick 1：相同输入（应该匹配） ===
    print()
    print("=" * 60)
    print("Tick 1 — 重复输入 '明天 上海 出门'")
    print("=" * 60)
    run_cycle(
        raw_input="明天 上海 出门",
        modality="text",
        tick=1,
        pool=pool,
        hdb=hdb,
    )

    print(f"  池中原子: {[a.content for a in pool.get_all()]}")
    print(f"  池能量: real={pool.get_energy_summary().real_energy:.3f}, "
          f"virtual={pool.get_energy_summary().virtual_energy:.3f}, "
          f"cognitive_pressure={pool.get_energy_summary().cognitive_pressure:.2f}")
    print(f"  HDB 结构数: {len(hdb._structures)}")
    print(f"  HDB hit_count: {[s.energy_stats.hit_count for s in hdb._structures.values()]}")

    # === Tick 2：部分新输入（应该写新结构） ===
    print()
    print("=" * 60)
    print("Tick 2 — 部分新输入 '上海 天气 怎么样'")
    print("=" * 60)
    run_cycle(
        raw_input="上海 天气 怎么样",
        modality="text",
        tick=2,
        pool=pool,
        hdb=hdb,
    )

    print(f"  池中原子: {[a.content for a in pool.get_all()][:10]}...")
    print(f"  池原子数: {len(pool.get_all())}")
    print(f"  HDB 结构数: {len(hdb._structures)}")
    print(f"  HDB 新增 hit_count: {[s.energy_stats.hit_count for s in hdb._structures.values()]}")

    # === 报告 ===
    print()
    print("=" * 60)
    print("最终报告")
    print("=" * 60)
    print(f"  StatePool: {pool.get_state_report()}")
    print(f"  HDB: {hdb.get_hdb_report()}")


if __name__ == "__main__":
    main()
