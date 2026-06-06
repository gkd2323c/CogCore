"""M4.2 SQLite 维护测试。

覆盖: vacuum / prune / backup / health_check / full_maintenance。
不依赖 LangGraph checkpointer, 用纯 SQLite 模拟。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time

import pytest

from cogcore.db_maintenance import (
    BackupResult,
    HealthReport,
    HealthStatus,
    PruneResult,
    VacuumResult,
    backup_to,
    full_maintenance,
    health_check,
    prune_checkpoints,
    vacuum,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def tmp_db_path(tmp_path):
    """每个测试一个独立 DB。"""
    return str(tmp_path / "test.db")


@pytest.fixture
def tmp_backup_dir(tmp_path):
    return str(tmp_path / "backups")


def make_langgraph_like_db(db_path: str, thread_count: int = 3, checkpoints_per_thread: int = 50) -> None:
    """构造一个 LangGraph SqliteSaver 风格 DB。

    SqliteSaver 表: checkpoints(thread_id TEXT, thread_ts REAL, ...)
    """
    conn = sqlite3.connect(db_path)
    try:
        # 简化版 schema, 不必和真实 SqliteSaver 一致
        conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT,
            thread_ts REAL,
            checkpoint_ns REAL,
            data BLOB,
            PRIMARY KEY (thread_id, thread_ts)
        )
        """)
        # 多 thread, 每 thread 多 checkpoint
        now = time.time()
        for t in range(thread_count):
            for c in range(checkpoints_per_thread):
                conn.execute(
                    "INSERT INTO checkpoints VALUES (?, ?, ?, ?)",
                    (f"thread_{t}", now + c * 0.001, now + c * 0.001, b"x" * 100),
                )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# vacuum
# ============================================================


def test_vacuum_creates_file(tmp_db_path):
    """vacuum 不存在的 db 应该报错。"""
    with pytest.raises(FileNotFoundError):
        vacuum(tmp_db_path)


def test_vacuum_reduces_size(tmp_db_path):
    """vacuum 后 size 应该 <= vacuum 前。"""
    make_langgraph_like_db(tmp_db_path, thread_count=5, checkpoints_per_thread=20)
    # 删一些 row 制造碎片
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("DELETE FROM checkpoints WHERE thread_id = 'thread_0'")
    conn.commit()
    conn.close()
    r = vacuum(tmp_db_path)
    assert isinstance(r, VacuumResult)
    assert r.saved_bytes >= 0
    assert r.after_bytes <= r.before_bytes + 100  # 留 100 字节浮点容差


def test_vacuum_returns_result_fields(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=2, checkpoints_per_thread=10)
    r = vacuum(tmp_db_path)
    assert r.db_path == tmp_db_path
    assert r.duration_ms > 0
    assert r.before_bytes > 0
    assert r.after_bytes > 0


# ============================================================
# prune_checkpoints
# ============================================================


def test_prune_missing_db(tmp_db_path):
    with pytest.raises(FileNotFoundError):
        prune_checkpoints(tmp_db_path)


def test_prune_keeps_recent_n_per_thread(tmp_db_path):
    """prune 后, 每 thread 应该只剩 keep_last 个 checkpoint。"""
    make_langgraph_like_db(tmp_db_path, thread_count=3, checkpoints_per_thread=50)
    r = prune_checkpoints(tmp_db_path, keep_last=10)
    assert isinstance(r, PruneResult)
    # 3 thread * 50 = 150, 保留 3*10 = 30, 删除 120
    assert r.deleted_rows == 120
    assert r.remaining_rows == 30


def test_prune_noop_when_already_at_limit(tmp_db_path):
    """所有 thread 都已经 <= keep_last, 不该删任何东西。"""
    make_langgraph_like_db(tmp_db_path, thread_count=3, checkpoints_per_thread=5)
    r = prune_checkpoints(tmp_db_path, keep_last=10)
    assert r.deleted_rows == 0
    assert r.remaining_rows == 15


def test_prune_invalid_keep_last(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=1, checkpoints_per_thread=5)
    with pytest.raises(ValueError):
        prune_checkpoints(tmp_db_path, keep_last=0)


def test_prune_empty_db_no_checkpoint_table(tmp_db_path):
    """DB 里没有 checkpoints 表时, prune 应该 0 删除 0 报错。"""
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("CREATE TABLE other (x INT)")
    conn.commit()
    conn.close()
    r = prune_checkpoints(tmp_db_path, keep_last=10)
    assert r.deleted_rows == 0


def test_prune_respects_max_delete(tmp_db_path):
    """单次 prune 最多删 max_delete 条。"""
    make_langgraph_like_db(tmp_db_path, thread_count=5, checkpoints_per_thread=100)
    # 5*100=500, keep_last=10, 应该删 450
    # 但 max_delete=100, 只能删 100
    r = prune_checkpoints(tmp_db_path, keep_last=10, max_delete=100)
    assert r.deleted_rows == 100
    assert r.remaining_rows == 400


# ============================================================
# backup_to
# ============================================================


def test_backup_creates_file(tmp_db_path, tmp_backup_dir):
    make_langgraph_like_db(tmp_db_path, thread_count=2, checkpoints_per_thread=10)
    r = backup_to(tmp_db_path, tmp_backup_dir)
    assert isinstance(r, BackupResult)
    assert os.path.exists(r.backup_path)
    assert r.bytes_copied > 0
    assert r.duration_ms > 0
    # 备份的 db 应该和原 db 同样数据
    orig = sqlite3.connect(tmp_db_path).execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    bk = sqlite3.connect(r.backup_path).execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    assert orig == bk


def test_backup_creates_dir_if_missing(tmp_db_path, tmp_backup_dir):
    make_langgraph_like_db(tmp_db_path, thread_count=1, checkpoints_per_thread=5)
    nested = os.path.join(tmp_backup_dir, "subdir", "deep")
    r = backup_to(tmp_db_path, nested)
    assert os.path.exists(r.backup_path)


def test_backup_naming_has_timestamp(tmp_db_path, tmp_backup_dir):
    make_langgraph_like_db(tmp_db_path, thread_count=1, checkpoints_per_thread=2)
    r = backup_to(tmp_db_path, tmp_backup_dir)
    name = os.path.basename(r.backup_path)
    assert name.startswith("cogcore_state_")
    assert name.endswith(".db")


# ============================================================
# health_check
# ============================================================


def test_health_check_missing_db(tmp_db_path):
    r = health_check(tmp_db_path)
    assert isinstance(r, HealthReport)
    assert r.exists is False
    assert r.status == HealthStatus.OK.value  # missing is OK, just warn
    assert any("not found" in w for w in r.warnings)


def test_health_check_basic(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=2, checkpoints_per_thread=10)
    r = health_check(tmp_db_path)
    assert r.exists is True
    assert r.table_count >= 1
    assert r.thread_count == 2
    assert r.checkpoint_count == 20
    assert r.size_mb >= 0
    assert r.size_bytes > 0
    assert r.status == HealthStatus.OK.value


def test_health_check_warns_on_large_size(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=1, checkpoints_per_thread=1)
    r = health_check(tmp_db_path, warn_size_mb=0.0001)  # 极小阈值
    assert r.status == HealthStatus.WARNING.value
    assert any("warning threshold" in w for w in r.warnings)


def test_health_check_critical_on_very_large(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=1, checkpoints_per_thread=1)
    r = health_check(tmp_db_path, warn_size_mb=0.0001, crit_size_mb=0.0002)
    assert r.status == HealthStatus.CRITICAL.value
    assert any("critical threshold" in w for w in r.warnings)


def test_health_check_to_dict_is_json_safe(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=1, checkpoints_per_thread=2)
    r = health_check(tmp_db_path)
    d = r.to_dict()
    import json
    s = json.dumps(d, default=str)
    assert "db_path" in s
    assert "status" in s


# ============================================================
# full_maintenance
# ============================================================


def test_full_maintenance_pipeline(tmp_db_path, tmp_backup_dir):
    make_langgraph_like_db(tmp_db_path, thread_count=5, checkpoints_per_thread=50)
    # 制造一些碎片
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("DELETE FROM checkpoints WHERE thread_id = 'thread_0'")
    conn.commit()
    conn.close()

    r = full_maintenance(tmp_db_path, backup_dir=tmp_backup_dir, keep_last=10)
    assert "backup" in r
    assert "prune" in r
    assert "vacuum" in r
    assert "health" in r
    # 备份文件应该存在
    assert os.path.exists(r["backup"]["backup_path"])
    # prune 后剩 4 thread * 10 = 40
    assert r["prune"]["remaining_rows"] == 40
    # vacuum 后 size 减少
    assert r["vacuum"]["saved_bytes"] >= 0


def test_full_maintenance_without_backup(tmp_db_path):
    make_langgraph_like_db(tmp_db_path, thread_count=2, checkpoints_per_thread=20)
    r = full_maintenance(tmp_db_path, keep_last=5)
    assert "backup" not in r
    assert r["prune"]["remaining_rows"] == 10
    assert "health" in r
