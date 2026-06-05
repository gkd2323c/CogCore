"""CogCore 后台服务测试（M2.1）。"""
from __future__ import annotations

import os
import time

import pytest

from cogcore.service import CogCoreService


@pytest.fixture
def service():
    s = CogCoreService()
    s.config.service.tick_interval = 0
    s._tick_count = 0
    s._last_diary_tick = 0
    s._last_report_tick = 0
    s._pending_input = []
    s._tools._diary_store = []
    return s


def test_service_created(service):
    assert service._tick_count == 0


def test_manual_tick(service):
    state = service.tick("test")
    assert len(state["stages_log"]) == 10
    assert service._tick_count == 1


def test_multiple_ticks(service):
    service.tick("a")
    service.tick("b")
    service.tick("c")
    assert service._tick_count == 3


def test_inject_input(service):
    service.inject_input("hello")
    assert len(service._pending_input) == 1


def test_get_status(service):
    service.tick("status")
    status = service.get_status()
    assert status["tick_count"] == 1
    assert "pool" in status
    assert "hdb" in status
    assert "nt" in status


def test_start_stop(service):
    service.config.service.tick_interval = 0
    service.start()
    assert service.running is True
    service.stop()
    assert service.running is False


def test_auto_diary(service):
    service.config.service.diary_interval = 2
    service._last_diary_tick = 0
    service.tick("d1")
    service.tick("d2")
    assert len(service._tools._diary_store) >= 1


def test_auto_diary_interval(service):
    service.config.service.diary_interval = 5
    service._last_diary_tick = 0
    for i in range(4):
        service.tick(f"x{i}")
    assert len(service._tools._diary_store) == 0
    service.tick("x5")
    assert len(service._tools._diary_store) >= 1


def test_background_thread():
    s = CogCoreService()
    s.config.service.tick_interval = 0.05
    s.start()
    time.sleep(0.15)
    s.stop()
    assert s._tick_count > 0


def test_background_processes_input():
    s = CogCoreService()
    s.config.service.tick_interval = 0.05
    s.start()
    s.inject_input("bg test")
    time.sleep(0.15)
    s.stop()
    assert len(s._pending_input) == 0


def test_persistence_directory():
    s = CogCoreService()
    assert os.path.exists(s.config.service.data_dir)
    db = os.path.join(s.config.service.data_dir, "state.db")
    s.tick("persist")
    assert os.path.exists(db)
