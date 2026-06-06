"""M5.3 场景 4 — 多 Agent 协作协调器。

同进程内管理多个 CogCoreService 实例，通过 SQLite SharedStore 共享状态。
不引入 LangGraph Store 外部依赖。
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import threading
import time
import uuid
from typing import Any

from cogcore.service import CogCoreService


@dataclasses.dataclass
class AgentInstance:
    """一个 Agent 实例的元数据。"""

    id: str
    name: str
    service: CogCoreService
    created_ts: float
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


class SharedStore:
    """基于 SQLite 的跨 Agent 状态共享。

    每个 Agent 写入自己的 namespace，其他 Agent 可读取。
    """

    def __init__(self, path: str = "cogcore_data/shared_store.db") -> None:
        self.path = path
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    UNIQUE(namespace, key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shared_ns_key ON shared_entries(namespace, key)"
            )

    def put(self, namespace: str, key: str, value: Any) -> None:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    """
                    INSERT INTO shared_entries(namespace, key, value, created_ts)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(namespace, key) DO UPDATE SET
                        value=excluded.value,
                        created_ts=excluded.created_ts
                    """,
                    (namespace, key, json.dumps(value, ensure_ascii=False), time.time()),
                )

    def get(self, namespace: str, key: str) -> Any | None:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                row = conn.execute(
                    "SELECT value FROM shared_entries WHERE namespace = ? AND key = ?",
                    (namespace, key),
                ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def list_keys(self, namespace: str) -> list[str]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                rows = conn.execute(
                    "SELECT key FROM shared_entries WHERE namespace = ?",
                    (namespace,),
                ).fetchall()
        return [r[0] for r in rows]


class AgentPool:
    """多 Agent 协调器。

    管理多个 CogCoreService 实例 + SharedStore 共享。
    """

    def __init__(self, shared_store: SharedStore | None = None) -> None:
        self._agents: dict[str, AgentInstance] = {}
        self._shared = shared_store or SharedStore()
        self._lock = threading.Lock()

    def spawn(self, name: str = "", metadata: dict[str, Any] | None = None) -> AgentInstance:
        """创建新 Agent 实例。"""
        agent_id = str(uuid.uuid4())[:8]
        svc = CogCoreService()
        agent = AgentInstance(
            id=agent_id,
            name=name or f"agent-{agent_id}",
            service=svc,
            created_ts=time.time(),
            metadata=metadata or {},
        )
        with self._lock:
            self._agents[agent_id] = agent
        return agent

    def get(self, agent_id: str) -> AgentInstance | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentInstance]:
        return list(self._agents.values())

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                return True
            return False

    def delegate(
        self,
        task: dict[str, Any],
        from_agent_id: str,
        to_agent_id: str,
    ) -> dict[str, Any]:
        """任务委派：把 task 写入 to_agent 的 shared namespace。"""
        to_agent = self.get(to_agent_id)
        if to_agent is None:
            return {"error": f"target agent {to_agent_id} not found"}

        task_id = str(uuid.uuid4())[:8]
        entry = {
            "task_id": task_id,
            "from": from_agent_id,
            "to": to_agent_id,
            "payload": task,
            "ts": time.time(),
        }
        self._shared.put(to_agent_id, f"task_{task_id}", entry)

        # 把任务 atom 注入目标 Agent 的状态池
        try:
            from cogcore.types import AtomEnergy, Modality, StimulusAtom, StimulusSource
            atom = StimulusAtom(
                content=json.dumps(task),
                source=StimulusSource.INTERNAL,
                modality=Modality.TEXT,
                energy=AtomEnergy(real=1.0),
                trace={"type": "delegated_task", "task_id": task_id},
            )
            to_agent.service._pool.add_atom(atom)
        except Exception:
            pass  # 状态池注入失败不阻塞委派

        return {"task_id": task_id, "status": "delegated"}

    def shared_store(self) -> SharedStore:
        return self._shared
