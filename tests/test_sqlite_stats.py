"""M4.3b sqlite-stats 测试。

覆盖: counter / gauge / histogram 三种 primitive, report, Markdown, CLI helper。
"""
from __future__ import annotations

import json
import os
import sqlite3

import pytest

from cogcore.sqlite_stats import StatsDB, report_markdown


@pytest.fixture
def stats_path(tmp_path):
    return str(tmp_path / "stats.db")


def test_statsdb_creates_three_tables(stats_path):
    db = StatsDB(stats_path)
    db.close()

    conn = sqlite3.connect(stats_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"counter", "gauge", "histogram"}.issubset(tables)


def test_incr_accumulates_counter(stats_path):
    db = StatsDB(stats_path)
    db.incr("ticks")
    db.incr("ticks", 4)
    db.incr("errors", 2)

    report = db.report()
    db.close()

    assert report["counters"]["ticks"]["value"] == 5
    assert report["counters"]["ticks"]["samples"] == 2
    assert report["counters"]["errors"]["value"] == 2


def test_incr_rejects_negative_values(stats_path):
    db = StatsDB(stats_path)
    with pytest.raises(ValueError):
        db.incr("ticks", -1)
    db.close()


def test_set_overwrites_gauge(stats_path):
    db = StatsDB(stats_path)
    db.set("active_atoms", 10)
    db.set("active_atoms", 7.5)

    report = db.report()
    db.close()

    assert report["gauges"]["active_atoms"]["value"] == 7.5
    assert report["gauges"]["active_atoms"]["samples"] == 2


def test_observe_histogram_percentiles(stats_path):
    db = StatsDB(stats_path)
    for value in range(1, 101):
        db.observe("latency_ms", value)

    report = db.report()
    db.close()

    latency = report["histograms"]["latency_ms"]
    assert latency["count"] == 100
    assert latency["min"] == 1
    assert latency["max"] == 100
    assert latency["avg"] == 50.5
    assert latency["p50"] == 50
    assert latency["p95"] == 95
    assert latency["p99"] == 99


def test_observe_multiple_histograms_independently(stats_path):
    db = StatsDB(stats_path)
    db.observe("latency_ms", 10)
    db.observe("latency_ms", 20)
    db.observe("queue_depth", 3)

    report = db.report()
    db.close()

    assert report["histograms"]["latency_ms"]["count"] == 2
    assert report["histograms"]["latency_ms"]["p50"] == 10
    assert report["histograms"]["queue_depth"]["count"] == 1
    assert report["histograms"]["queue_depth"]["p95"] == 3


def test_report_is_json_safe(stats_path):
    db = StatsDB(stats_path)
    db.incr("ticks", 2)
    db.set("pressure", 0.42)
    db.observe("latency_ms", 12.5)

    payload = db.report()
    db.close()

    encoded = json.dumps(payload, ensure_ascii=False)
    assert "ticks" in encoded
    assert "latency_ms" in encoded


def test_report_markdown_contains_all_sections(stats_path):
    db = StatsDB(stats_path)
    db.incr("ticks", 2)
    db.set("pressure", 0.42)
    db.observe("latency_ms", 12.5)

    md = db.report_markdown()
    db.close()

    assert "# CogCore sqlite-stats" in md
    assert "## Counters" in md
    assert "`ticks`" in md
    assert "## Gauges" in md
    assert "`pressure`" in md
    assert "## Histograms" in md
    assert "`latency_ms`" in md


def test_module_report_markdown_accepts_report_dict(stats_path):
    db = StatsDB(stats_path)
    db.incr("ticks", 3)
    report = db.report()
    db.close()

    md = report_markdown(report)
    assert "ticks" in md
    assert "3" in md


def test_context_manager_closes_connection(stats_path):
    with StatsDB(stats_path) as db:
        db.incr("ticks")

    assert os.path.exists(stats_path)
