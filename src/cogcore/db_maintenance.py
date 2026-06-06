"""M4.2 SQLite 维护 (L7 优化)。

LangGraph SqliteSaver 默认无限增长 state.db。本模块提供:

  - vacuum(db_path): 压缩 SQLite (VACUUM 命令)
  - prune_checkpoints(db_path, keep_last=100): 只保留最近 N 个 thread_id 的
    最后 K 个 checkpoint
  - backup_to(db_path, backup_dir): 滚动备份 (含 WAL/SHM)
  - health_check(db_path) -> dict: 容量 + 表数 + 预警
  - HealthStatus: OK / WARNING / CRITICAL

不引外部服务, 只用 stdlib sqlite3 + os/shutil。

设计原则：
  - 不动 SqliteSaver 内部表结构 (它用 thread_id + checkpoint_ns 排序)
  - vacuum 前强制 checkpoint, 避免被锁
  - prune 用事务 + LIMIT, 一次最多删除 max_delete 条
  - 备份用 sqlite3.Connection.backup() API, 保证一致性
"""
from __future__ import annotations

import enum
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# ============================================================
# 状态枚举
# ============================================================


class HealthStatus(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


# ============================================================
# 配置常量
# ============================================================


# size_mb >= 触发 WARNING
DEFAULT_WARN_SIZE_MB = 50.0
# size_mb >= 触发 CRITICAL
DEFAULT_CRIT_SIZE_MB = 200.0
# 一次 prune 最多删多少条, 防止事务过大
MAX_DELETE_PER_BATCH = 1000
# 默认保留最近 N 个 checkpoint per thread
DEFAULT_KEEP_LAST = 100


# ============================================================
# 数据类
# ============================================================


@dataclass
class HealthReport:
    """健康检查报告。"""

    db_path: str
    exists: bool
    size_bytes: int
    size_mb: float
    size_with_wal_bytes: int
    table_count: int
    thread_count: int
    checkpoint_count: int
    writeahead_count: int
    oldest_checkpoint_ts: float | None
    newest_checkpoint_ts: float | None
    status: str  # HealthStatus value
    warnings: list[str]
    timestamp: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VacuumResult:
    """vacuum() 结果。"""

    db_path: str
    before_bytes: int
    after_bytes: int
    saved_bytes: int
    duration_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PruneResult:
    """prune_checkpoints() 结果。"""

    db_path: str
    deleted_rows: int
    remaining_rows: int
    keep_last: int
    duration_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BackupResult:
    """backup_to() 结果。"""

    db_path: str
    backup_path: str
    bytes_copied: int
    duration_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# 辅助
# ============================================================


def _total_size_with_wal(db_path: str) -> int:
    """db 文件 + WAL + SHM 三个文件的总大小。"""
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = db_path + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total


def _checkpoint_wal(db_path: str) -> None:
    """强制把 WAL 数据合并到主 db。vacuum / 备份前必跑。"""
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        # PASSIVE = 不阻塞读者, 跑过能合并的合并多少
        # FULL = 阻塞到合并完
        # 这里用 PASSIVE: 真空 / 备份能容忍少量残留 WAL
        try:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.DatabaseError:
            pass  # 非 WAL 模式也无所谓
    finally:
        conn.close()


# ============================================================
# 核心操作
# ============================================================


def vacuum(
    db_path: str,
    *,
    checkpoint_wal_first: bool = True,
) -> VacuumResult:
    """压缩 SQLite 数据库。

    SQLite 的 VACUUM 会重写整个 db 文件, 释放未用空间。
    运行前会自动做 WAL checkpoint 以避免锁。

    Args:
        db_path: 数据库文件路径
        checkpoint_wal_first: 是否先做 WAL checkpoint

    Returns:
        VacuumResult 含前后大小对比
    """
    t0 = time.time()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")
    before = _total_size_with_wal(db_path)

    if checkpoint_wal_first:
        _checkpoint_wal(db_path)

    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()

    after = _total_size_with_wal(db_path)
    return VacuumResult(
        db_path=db_path,
        before_bytes=before,
        after_bytes=after,
        saved_bytes=max(0, before - after),
        duration_ms=(time.time() - t0) * 1000,
    )


def prune_checkpoints(
    db_path: str,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
    max_delete: int = MAX_DELETE_PER_BATCH,
) -> PruneResult:
    """只保留每个 thread_id 的最近 keep_last 个 checkpoint。

    SqliteSaver 用 thread_id + checkpoint_ns 主键组织 checkpoint。
    我们按 (thread_id, checkpoint_ns DESC) 取每个 thread 的前 keep_last 个,
    其余删除。

    Args:
        db_path: 数据库文件路径
        keep_last: 每 thread 保留的 checkpoint 数
        max_delete: 单次事务最多删除的条数 (防事务过大)

    Returns:
        PruneResult
    """
    t0 = time.time()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")

    _checkpoint_wal(db_path)

    conn = sqlite3.connect(db_path, timeout=30.0)
    deleted = 0
    try:
        # 找到 LangGraph SqliteSaver 的 checkpoints 表名
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%checkpoint%'"
        ).fetchall()]
        if not tables:
            return PruneResult(
                db_path=db_path, deleted_rows=0, remaining_rows=0,
                keep_last=keep_last, duration_ms=(time.time() - t0) * 1000,
            )
        cp_table = tables[0]

        # 先查列名
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({cp_table})").fetchall()]
        # 找 thread_id 列 和 checkpoint_ns (或类似时间戳) 列
        # 优先选 'thread_id' 精确匹配, 避免 'thread_ts' 抢了
        thread_col = None
        ts_col = None
        for c in cols:
            cl = c.lower()
            if cl == "thread_id":
                thread_col = c
                break
        if thread_col is None:
            for c in cols:
                cl = c.lower()
                if "thread" in cl and cl != "thread_ts":
                    thread_col = c
                    break
        for c in cols:
            cl = c.lower()
            if "checkpoint_ns" in cl:
                ts_col = c
                break
        if ts_col is None:
            for c in cols:
                cl = c.lower()
                if cl == "ts" or "timestamp" in cl:
                    ts_col = c
                    break
        if not thread_col or not ts_col:
            logger.warning(f"can't find thread_id / ts cols in {cp_table}: {cols}")
            return PruneResult(
                db_path=db_path, deleted_rows=0, remaining_rows=0,
                keep_last=keep_last, duration_ms=(time.time() - t0) * 1000,
            )

        # 找出每 thread 要保留的 checkpoint_id
        # SQLite rowid 在没有 WITHOUT ROWID 表的情况下总是存在且唯一
        pk = "rowid"

        sql = f"""
        WITH ranked AS (
            SELECT rowid AS pk, {thread_col} AS tid, {ts_col} AS ts,
                   ROW_NUMBER() OVER (PARTITION BY {thread_col} ORDER BY {ts_col} DESC) AS rn
            FROM {cp_table}
        )
        DELETE FROM {cp_table}
        WHERE rowid IN (
            SELECT pk FROM ranked WHERE rn > ?
            LIMIT ?
        )
        """
        # 检查 keep_last 是否合理
        if keep_last < 1:
            raise ValueError(f"keep_last must be >= 1, got {keep_last}")
        # SQLite 不保证 rowcount, 先记下删前总数
        before = conn.execute(f"SELECT COUNT(*) FROM {cp_table}").fetchone()[0]
        conn.execute(sql, (keep_last, max_delete))
        conn.commit()
        deleted = before - conn.execute(f"SELECT COUNT(*) FROM {cp_table}").fetchone()[0]

        # 剩余
        remaining = conn.execute(f"SELECT COUNT(*) FROM {cp_table}").fetchone()[0]
    finally:
        conn.close()

    return PruneResult(
        db_path=db_path,
        deleted_rows=deleted,
        remaining_rows=remaining,
        keep_last=keep_last,
        duration_ms=(time.time() - t0) * 1000,
    )


def backup_to(
    db_path: str,
    backup_dir: str,
    *,
    checkpoint_wal_first: bool = True,
) -> BackupResult:
    """备份 SQLite 到 backup_dir。

    用 sqlite3.Connection.backup() 拿一致性快照 (即使有并发写)。
    文件名: cogcore_state_YYYYMMDD_HHMMSS.db

    Args:
        db_path: 源 DB
        backup_dir: 目标目录
        checkpoint_wal_first: 是否先做 WAL checkpoint

    Returns:
        BackupResult
    """
    t0 = time.time()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)

    if checkpoint_wal_first:
        _checkpoint_wal(db_path)

    ts_str = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"cogcore_state_{ts_str}.db"
    backup_path = os.path.join(backup_dir, backup_name)

    src = sqlite3.connect(db_path, timeout=30.0)
    dst = sqlite3.connect(backup_path, timeout=30.0)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    # 也复制 WAL/SHM 以便恢复一致
    for suffix in ("-wal", "-shm"):
        wp = db_path + suffix
        if os.path.exists(wp):
            shutil.copy2(wp, backup_path + suffix)

    return BackupResult(
        db_path=db_path,
        backup_path=backup_path,
        bytes_copied=os.path.getsize(backup_path),
        duration_ms=(time.time() - t0) * 1000,
    )


# ============================================================
# 健康检查
# ============================================================


def health_check(
    db_path: str,
    *,
    warn_size_mb: float = DEFAULT_WARN_SIZE_MB,
    crit_size_mb: float = DEFAULT_CRIT_SIZE_MB,
) -> HealthReport:
    """健康检查。

    Args:
        db_path: 数据库路径
        warn_size_mb: 触发 WARNING 的 size 阈值
        crit_size_mb: 触发 CRITICAL 的 size 阈值

    Returns:
        HealthReport 含 size / 表数 / thread 数 / checkpoint 数 / 预警
    """
    warnings: list[str] = []
    ts_now = time.time()

    if not os.path.exists(db_path):
        return HealthReport(
            db_path=db_path, exists=False, size_bytes=0, size_mb=0.0,
            size_with_wal_bytes=0, table_count=0, thread_count=0,
            checkpoint_count=0, writeahead_count=0,
            oldest_checkpoint_ts=None, newest_checkpoint_ts=None,
            status=HealthStatus.OK.value, warnings=["db file not found"],
            timestamp=ts_now,
        )

    size_bytes = os.path.getsize(db_path)
    size_with_wal = _total_size_with_wal(db_path)
    size_mb = size_with_wal / (1024 * 1024)

    # 容量预警
    if size_mb >= crit_size_mb:
        warnings.append(f"size {size_mb:.1f}MB >= critical threshold {crit_size_mb}MB")
        status = HealthStatus.CRITICAL
    elif size_mb >= warn_size_mb:
        warnings.append(f"size {size_mb:.1f}MB >= warning threshold {warn_size_mb}MB")
        status = HealthStatus.WARNING
    else:
        status = HealthStatus.OK

    # 表 + checkpoint 统计
    table_count = 0
    thread_count = 0
    checkpoint_count = 0
    writeahead_count = 0
    oldest_ts = None
    newest_ts = None

    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        # 表数
        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]

        # checkpoints 表
        cp_tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%checkpoint%'"
        ).fetchall()]
        if cp_tables:
            cp_table = cp_tables[0]
            checkpoint_count = conn.execute(f"SELECT COUNT(*) FROM {cp_table}").fetchone()[0]

            # thread 数 (找列名)
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({cp_table})").fetchall()]
            thread_col = next((c for c in cols if c.lower() == "thread_id"), None)
            if thread_col:
                thread_count = conn.execute(
                    f"SELECT COUNT(DISTINCT {thread_col}) FROM {cp_table}"
                ).fetchone()[0]

            # 时间戳
            ts_col = next((c for c in cols if "checkpoint_ns" in c.lower() or c.lower() == "ts"), None)
            if ts_col:
                row = conn.execute(
                    f"SELECT MIN({ts_col}), MAX({ts_col}) FROM {cp_table}"
                ).fetchone()
                oldest_ts = row[0]
                newest_ts = row[1]
    except sqlite3.DatabaseError as e:
        warnings.append(f"sqlite error: {e}")
    finally:
        conn.close()

    # WAL 文件大小
    wal_path = db_path + "-wal"
    if os.path.exists(wal_path):
        writeahead_count = os.path.getsize(wal_path)
        if writeahead_count > 5 * 1024 * 1024:  # > 5MB WAL 未合并
            warnings.append(f"WAL size {writeahead_count / 1024 / 1024:.1f}MB large, run checkpoint")

    return HealthReport(
        db_path=db_path, exists=True,
        size_bytes=size_bytes, size_mb=round(size_mb, 2),
        size_with_wal_bytes=size_with_wal,
        table_count=table_count, thread_count=thread_count,
        checkpoint_count=checkpoint_count, writeahead_count=writeahead_count,
        oldest_checkpoint_ts=oldest_ts, newest_checkpoint_ts=newest_ts,
        status=status.value, warnings=warnings, timestamp=ts_now,
    )


# ============================================================
# 便捷 API
# ============================================================


def full_maintenance(
    db_path: str,
    backup_dir: str | None = None,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
    warn_size_mb: float = DEFAULT_WARN_SIZE_MB,
) -> dict:
    """一键维护: backup -> prune -> vacuum -> health。

    Returns:
        dict 含 4 步结果
    """
    results: dict = {}
    if backup_dir:
        results["backup"] = backup_to(db_path, backup_dir).to_dict()
    results["prune"] = prune_checkpoints(db_path, keep_last=keep_last).to_dict()
    results["vacuum"] = vacuum(db_path).to_dict()
    results["health"] = health_check(db_path, warn_size_mb=warn_size_mb).to_dict()
    return results
