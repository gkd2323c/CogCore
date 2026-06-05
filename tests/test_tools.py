"""工具系统测试（M1.3）。"""
from __future__ import annotations

import pytest

from cogcore.hdb import HDB
from cogcore.state_pool import StatePool
from cogcore.tools import LongTermExperienceTools, ToolRegistry


# ============================================================
# ToolRegistry
# ============================================================


def test_register_and_execute_tool():
    r = ToolRegistry()
    r.register_tool("greet", lambda name: f"Hello {name}", {"name": "string"})
    r.add_to_allowlist("greet")
    result = r.execute_tool("greet", {"name": "CogCore"})
    assert result == "Hello CogCore"


def test_execute_unregistered_raises():
    r = ToolRegistry()
    r.add_to_allowlist("missing")
    with pytest.raises(KeyError):
        r.execute_tool("missing")


def test_execute_not_in_allowlist_raises():
    r = ToolRegistry()
    r.register_tool("blocked", lambda: "nope", {})
    with pytest.raises(PermissionError):
        r.execute_tool("blocked")


def test_allowlist_controls_visibility():
    r = ToolRegistry()
    r.register_tool("a", lambda: 1, {})
    r.register_tool("b", lambda: 2, {})
    r.set_allowlist({"a"})
    assert r.get_available_tools() == ["a"]


def test_add_to_allowlist():
    r = ToolRegistry()
    r.register_tool("x", lambda: "x", {})
    r.add_to_allowlist("x")
    assert "x" in r.get_available_tools()


def test_execute_without_params():
    r = ToolRegistry()
    r.register_tool("ping", lambda: "pong", {})
    r.add_to_allowlist("ping")
    assert r.execute_tool("ping") == "pong"


# ============================================================
# LongTermExperienceTools — Diary
# ============================================================


def _tools():
    return LongTermExperienceTools(HDB(), StatePool())


def test_write_diary_returns_id():
    t = _tools()
    eid = t.write_diary("title", "content")
    assert isinstance(eid, str)
    assert len(eid) > 10  # UUID


def test_read_diary_finds_by_title():
    t = _tools()
    t.write_diary("Architecture Meeting", "Discussed the system design")
    results = t.read_diary("Architecture")
    assert len(results) == 1
    assert results[0]["title"] == "Architecture Meeting"


def test_read_diary_finds_by_content():
    t = _tools()
    t.write_diary("Notes", "Remember to refactor the HDB module")
    results = t.read_diary("refactor")
    assert len(results) == 1


def test_read_diary_empty_query_returns_all():
    t = _tools()
    t.write_diary("A", "a")
    t.write_diary("B", "b")
    t.write_diary("C", "c")
    results = t.read_diary()  # no query = all
    assert len(results) == 3


def test_read_diary_no_match():
    t = _tools()
    t.write_diary("Test", "hello")
    results = t.read_diary("nonexistent")
    assert len(results) == 0


def test_write_diary_with_tags():
    t = _tools()
    eid = t.write_diary("Work", "Done", tags=["work", "important"])
    results = t.read_diary("Work")
    assert results[0]["tags"] == ["work", "important"]


# ============================================================
# LongTermExperienceTools — Tasks
# ============================================================


def test_schedule_task_creates_entry():
    t = _tools()
    tid = t.schedule_task("daily report", "generate_report", period=30)
    tasks = t.list_tasks()
    assert len(tasks) == 1


def test_cancel_task_removes():
    t = _tools()
    tid = t.schedule_task("task1", "action1", 10)
    assert len(t.list_tasks()) == 1
    t.cancel_task(tid)
    assert len(t.list_tasks()) == 0


def test_list_tasks_empty_by_default():
    t = _tools()
    assert t.list_tasks() == []


def test_cancel_nonexistent_task_returns_false():
    t = _tools()
    result = t.cancel_task("nonexistent-id")
    assert result is False


def test_schedule_multiple_tasks():
    t = _tools()
    t.schedule_task("t1", "a", 5)
    t.schedule_task("t2", "b", 10)
    assert len(t.list_tasks()) == 2
