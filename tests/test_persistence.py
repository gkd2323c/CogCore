"""CogCore SQLite 持久化测试（M1.2）。每个测试用独立数据库文件。

DB 路径放 pytest tmp_path 里, 由 pytest 自动清理 (含 -wal/-shm 伴随文件),
避免测试失败时 SQLite 连接未关导致的 PermissionError 残留。
"""
from __future__ import annotations

import os
import sqlite3

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


def skip():
    if not _HAS_SQLITE:
        pytest.skip("need langgraph-checkpoint-sqlite")


@pytest.fixture
def db_path(tmp_path):
    """每个测试一个临时 DB, tmp_path 由 pytest 在测试后自动清理。"""
    return str(tmp_path / "cogcore_persist.db")


def test_persistent_graph_compiles(db_path):
    skip()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=db_path)
    assert g is not None


def test_persistent_invoke_10_stages(db_path):
    skip()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=db_path)
    r = invoke_cogcore(g, "test", 0, "t-1")
    assert len(r["stages_log"]) == 10


def test_persistent_db_file_created(db_path):
    skip()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=db_path)
    invoke_cogcore(g, "x", 0, "t-1")
    assert os.path.exists(db_path)
    assert os.path.getsize(db_path) > 0


def test_persistent_across_invocations(db_path):
    skip()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=db_path)
    r1 = invoke_cogcore(g, "first", 0, "t-same")
    r2 = invoke_cogcore(g, "second", 1, "t-same")
    assert r2["raw_input"] == "second"
    assert r2["tick"] == 1


def test_persistent_different_threads(db_path):
    skip()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=db_path)
    r_a = invoke_cogcore(g, "alpha", 0, "thread-a")
    r_b = invoke_cogcore(g, "beta", 0, "thread-b")
    assert r_a["raw_input"] == "alpha"
    assert r_b["raw_input"] == "beta"


def test_persistent_sqlite_has_tables(db_path):
    skip()
    g = build_cogcore_graph_persistent(_modules(), sqlite_path=db_path)
    config = {"configurable": {"thread_id": "t-store"}}
    g.invoke({"tick": 0, "raw_input": "test", "modality": "text"}, config=config)
    conn = sqlite3.connect(db_path)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    names = [t[0] for t in tables]
    assert any("checkpoint" in t for t in names), f"no checkpoint tables: {names}"
