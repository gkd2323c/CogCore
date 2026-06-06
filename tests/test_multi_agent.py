"""M5.3 场景 4 — 多 Agent 协作测试。"""
from __future__ import annotations

from cogcore.multi_agent import AgentPool, SharedStore


# ============================================================
# SharedStore
# ============================================================


def test_shared_store_put_get(tmp_path):
    store = SharedStore(path=str(tmp_path / "shared.db"))
    store.put("ns1", "key1", {"value": 42})
    assert store.get("ns1", "key1") == {"value": 42}


def test_shared_store_list_keys(tmp_path):
    store = SharedStore(path=str(tmp_path / "shared.db"))
    store.put("ns1", "a", 1)
    store.put("ns1", "b", 2)
    keys = store.list_keys("ns1")
    assert sorted(keys) == ["a", "b"]


# ============================================================
# AgentPool
# ============================================================


def test_spawn_agent():
    pool = AgentPool()
    agent = pool.spawn(name="test-agent")
    assert agent.id
    assert agent.name == "test-agent"
    assert agent.service is not None


def test_agent_independent_pools():
    pool = AgentPool()
    a1 = pool.spawn()
    a2 = pool.spawn()
    # 各自有独立状态池
    assert a1.service._pool is not a2.service._pool


def test_delegate_task(tmp_path):
    pool = AgentPool(shared_store=SharedStore(path=str(tmp_path / "shared.db")))
    a1 = pool.spawn()
    a2 = pool.spawn()
    result = pool.delegate({"action": "say_hello"}, a1.id, a2.id)
    assert "task_id" in result
    assert result["status"] == "delegated"
    # 目标 Agent 的 shared store 中有任务（key 格式为 task_<task_id>）
    task_key = f"task_{result['task_id']}"
    assert pool.shared_store().get(a2.id, task_key) is not None


def test_delegate_to_missing_agent():
    pool = AgentPool()
    a1 = pool.spawn()
    result = pool.delegate({"action": "test"}, a1.id, "missing")
    assert "error" in result


def test_list_and_remove():
    pool = AgentPool()
    a1 = pool.spawn()
    a2 = pool.spawn()
    assert len(pool.list_agents()) == 2
    assert pool.remove(a1.id) is True
    assert len(pool.list_agents()) == 1
    assert pool.remove("missing") is False
