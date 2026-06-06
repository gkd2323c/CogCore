"""CogCore 后台认知服务（M2.1）。

让 CogCore 从「每次手动调 invoke」变成「持续运行的后台服务」：
- 定时 tick 调度
- 外源输入注入
- 自动写日记
- 健康监控
- 通过 SQLite 持久化状态
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from cogcore.action_system import ActionSystem
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.config import load_config
from cogcore.graph import _HAS_SQLITE, build_cogcore_graph, build_cogcore_graph_persistent, invoke_cogcore
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool
from cogcore.tools import LongTermExperienceTools

logger = logging.getLogger(__name__)


class CogCoreService:
    """持续运行的 CogCore 认知服务。

    用法：
        service = CogCoreService()
        service.start()           # 后台线程开始自动 tick
        service.inject_input("北京天气")  # 注入外源输入
        status = service.get_status()
        service.stop()
    """

    def __init__(self, config_path: str | None = None) -> None:
        self.config = load_config(config_path)
        self._running = False
        self._tick_count = 0
        self._last_diary_tick = 0
        self._last_report_tick = 0
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._pending_input: list[str] = []
        self._thread_id = f"service-{uuid4().hex[:8]}"

        # 数据目录
        self._ensure_data_dir()

        # 初始化模块
        self._pool = StatePool()
        self._hdb = HDB()
        self._cfs = CognitiveFeelingSystem()
        self._attention = Attention()
        self._nt_sys = NeurotransmitterSystem()
        self._action_sys = ActionSystem()
        self._tuner = AdaptiveTuner()
        diary_db_path = os.path.join(self._data_dir, "diary.db")
        self._tools = LongTermExperienceTools(self._hdb, self._pool, db_path=diary_db_path)

        self._modules = {
            "pool": self._pool,
            "hdb": self._hdb,
            "cfs": self._cfs,
            "attention": self._attention,
            "nt_sys": self._nt_sys,
            "action_sys": self._action_sys,
            "tuner": self._tuner,
        }

        # 构造持久化图。缺少 langgraph-checkpoint-sqlite 时降级到内存图，
        # 让 API/Agent 在最小开发环境仍可运行；正式安装通过 pyproject 声明该依赖。
        sqlite_path = os.path.join(self._data_dir, "state.db")
        self._sqlite_path = sqlite_path
        if _HAS_SQLITE:
            self._graph = build_cogcore_graph_persistent(
                self._modules, sqlite_path=sqlite_path
            )
            self._persistence_backend = "sqlite"
        else:
            logger.warning(
                "langgraph-checkpoint-sqlite not installed; "
                "CogCoreService is using in-memory graph fallback"
            )
            self._graph = build_cogcore_graph(self._modules)
            self._persistence_backend = "memory_fallback"
            self._ensure_fallback_state_db()

    def _ensure_data_dir(self) -> None:
        self._data_dir = self.config.service.data_dir
        os.makedirs(self._data_dir, exist_ok=True)

    def _ensure_fallback_state_db(self) -> None:
        """Create a minimal state DB marker when SQLite checkpointer is unavailable."""
        import sqlite3

        conn = sqlite3.connect(self._sqlite_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO service_metadata(key, value) VALUES (?, ?)",
                ("persistence_backend", self._persistence_backend),
            )
            conn.commit()
        finally:
            conn.close()

    # ============================================================
    # 生命周期
    # ============================================================

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动后台服务。"""
        if self._running:
            logger.warning("Service already running")
            return

        self._running = True
        self._stop_event.clear()

        interval = self.config.service.tick_interval
        if interval > 0:
            self._thread = Thread(
                target=self._run_loop,
                daemon=True,
                name="cogcore-service",
            )
            self._thread.start()
            logger.info(f"CogCoreService started (tick_interval={interval}s)")
        else:
            logger.info("CogCoreService started (manual tick mode)")

    def stop(self) -> None:
        """停止后台服务。"""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("CogCoreService stopped")

    def _run_loop(self) -> None:
        """后台 tick 循环。"""
        interval = self.config.service.tick_interval
        while not self._stop_event.is_set():
            # 检查是否有待处理输入
            if self._pending_input:
                text = self._pending_input.pop(0)
                self._do_tick(raw_input=text)
            else:
                self._do_tick()

            self._stop_event.wait(timeout=interval)

    # ============================================================
    # Tick
    # ============================================================

    def _do_tick(self, raw_input: str = "", modality: str = "text") -> dict:
        """执行一次认知 tick。"""
        self._tick_count += 1
        tick = self._tick_count

        self._hdb.set_tick(tick)
        self._cfs.set_tick(tick)
        self._nt_sys.set_tick(tick)

        state = invoke_cogcore(
            self._graph,
            raw_input=raw_input,
            tick=tick,
            thread_id=self._thread_id,
            modality=modality,
        )

        # 自动写日记
        self._check_auto_diary(state)
        # 状态报告
        self._check_report(tick)

        return state

    def tick(self, raw_input: str = "", modality: str = "text") -> dict:
        """手动触发一次 tick。"""
        return self._do_tick(raw_input=raw_input, modality=modality)

    def inject_input(self, text: str) -> None:
        """注入外源输入。后台循环会在下一 tick 处理。"""
        self._pending_input.append(text)
        logger.info(f"Input queued: {text[:50]}...")

    # ============================================================
    # 自动维护
    # ============================================================

    def _check_auto_diary(self, state: dict) -> None:
        """检查是否应该自动写日记。"""
        interval = self.config.service.diary_interval
        if interval <= 0:
            return

        if self._tick_count - self._last_diary_tick >= interval:
            nt = state.get("nt_values", {})

            def get_nt(key):
                if hasattr(nt, key):
                    return getattr(nt, key)
                if isinstance(nt, dict):
                    return nt.get(key, 0.0)
                return 0.0

            summary = (
                f"Tick {self._tick_count}: "
                f"arousal={get_nt('arousal'):.2f}, "
                f"caution={get_nt('caution'):.2f}, "
                f"fatigue={get_nt('fatigue'):.2f}"
            )
            self._tools.write_diary(
                title=f"Auto Diary @ tick {self._tick_count}",
                content=summary,
                importance=0.3,
            )
            self._last_diary_tick = self._tick_count
            logger.info(f"Auto diary written at tick {self._tick_count}")

    def _check_report(self, tick: int) -> None:
        """定期打印状态报告。"""
        interval = self.config.service.report_interval
        if interval <= 0:
            return
        if tick - self._last_report_tick >= interval:
            logger.info(
                f"Service status: tick={tick}, "
                f"pool={self._pool.get_energy_summary().active_count} active, "
                f"hdb={self._hdb.get_hdb_report()['structure_count']} structures"
            )
            self._last_report_tick = tick

    # ============================================================
    # 状态查询
    # ============================================================

    def get_status(self) -> dict:
        """当前服务状态报告。"""
        pool_summary = self._pool.get_energy_summary()
        hdb_report = self._hdb.get_hdb_report()

        return {
            "running": self._running,
            "tick_count": self._tick_count,
            "pending_inputs": len(self._pending_input),
            "pool": {
                "active": pool_summary.active_count,
                "total_energy": round(pool_summary.total_energy, 3),
                "pressure": round(pool_summary.cognitive_pressure, 3),
            },
            "hdb": {
                "structures": hdb_report.get("structure_count", 0),
                "episodic": hdb_report.get("episodic_count", 0),
            },
            "nt": {
                "arousal": round(self._nt_sys.current.arousal, 3),
                "caution": round(self._nt_sys.current.caution, 3),
                "fatigue": round(self._nt_sys.current.fatigue, 3),
            },
            "diary_tools": {
                "diary_count": len(self._tools._diary_store),
            },
            "persistence": {
                "backend": self._persistence_backend,
                "state_db": self._sqlite_path,
            },
        }
