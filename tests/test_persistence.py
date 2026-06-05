"""CogCore SQLite 持久化测试（M1.2）。每个测试用独立数据库文件。"""
from __future__ import annotations

import os
import sqlite3
import uuid

import pytest

from cogcore.action_system import ActionSystem
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.graph import build_cogcore_graph_persistent, invoke_cogcore, _HAS_SQLITE
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool


def _modules():
    return {
        "pool": StatePool(), "hdb": HDB(), "cfs": CognitiveFeelingSystem(),
        "attention": Attention(), "nt_sys": NeurotransmitterSystem(),
        "action_sys": ActionSystem(), "tuner": AdaptiveTuner(),
    }


def _db():
    return f"test_{uuid.uuid4().hex[:12]}.db"


def skip():
    if not _HAS_SQLITE:
        pytest.skip("need langgraph-checkpoint-sqlite")


def _clean(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass
    for ext in ("-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except PermissionError:
                pass


def test_persistent_graph_compiles():
    skip()
    p = _db()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=p)
    assert g is not None
    _clean(p)


def test_persistent_invoke_10_stages():
    skip()
    p = _db()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=p)
    r = invoke_cogcore(g, "test", 0, "t-1")
    assert len(r["stages_log"]) == 10
    _clean(p)


def test_persistent_db_file_created():
    skip()
    p = _db()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=p)
    invoke_cogcore(g, "x", 0, "t-1")
    assert os.path.exists(p)
    assert os.path.getsize(p) > 0
    _clean(p)


def test_persistent_across_invocations():
    skip()
    p = _db()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=p)
    r1 = invoke_cogcore(g, "first", 0, "t-same")
    r2 = invoke_cogcore(g, "second", 1, "t-same")
    assert r2["raw_input"] == "second"
    assert r2["tick"] == 1
    _clean(p)


def test_persistent_different_threads():
    skip()
    p = _db()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=p)
    r_a = invoke_cogcore(g, "alpha", 0, "thread-a")
    r_b = invoke_cogcore(g, "beta", 0, "thread-b")
    assert r_a["raw_input"] == "alpha"
    assert r_b["raw_input"] == "beta"
    _clean(p)


def test_persistent_sqlite_has_tables():
    skip()
    p = _db()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=p)
    config = {"configurable": {"thread_id": "t-store"}}
    g.invoke({"tick": 0, "raw_input": "test", "modality": "text"}, config=config)
    conn = sqlite3.connect(p)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    names = [t[0] for t in tables]
    assert any("checkpoint" in t for t in names), f"no checkpoint tables: {names}"
    _clean(p)
