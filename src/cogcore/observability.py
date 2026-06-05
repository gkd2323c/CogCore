"""可观察性接口（Observatory）：白箱审计与诊断。

接口与 docs/CogCore-通用认知内核架构设计.md §6.3 完全对齐。
所有报告数据应包含 SHA-256 哈希锚点，确保可追溯。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash(data: Any) -> str:
    """计算任意 JSON 可序列化对象的 SHA-256。"""
    raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Observatory:
    """白箱观测台。

    论文 4.7 节"observatory/_app.py" + 主文档 §6.3。
    """

    def __init__(
        self,
        states: list[Any] | None = None,
        hdb: Any | None = None,
        action_sys: Any | None = None,
    ) -> None:
        self.states = states or []
        self.hdb = hdb
        self.action_sys = action_sys

    def get_tick_report(self, tick: int) -> dict:
        """获取单轮的完整报告（含 SHA-256 哈希锚点）。"""
        state = None
        for s in self.states:
            s_tick = s.tick if hasattr(s, "tick") else s.get("tick", 0)
            if s_tick == tick:
                state = s
                break
        if state is None:
            return {}

        if hasattr(state, "model_dump"):
            report = state.model_dump()
        elif isinstance(state, dict):
            report = state.copy()
        else:
            report = {}

        report["hash"] = self.hash_report(report)
        return report

    def get_state_snapshot(self) -> dict:
        """获取当前全局状态快照。"""
        if not self.states:
            return {}
        latest = self.states[-1]
        if hasattr(latest, "model_dump"):
            snapshot = latest.model_dump()
        elif isinstance(latest, dict):
            snapshot = latest.copy()
        else:
            snapshot = {}

        snapshot["hash"] = self.hash_report(snapshot)
        return snapshot

    def get_structure_graph(self) -> dict:
        """获取 HDB 结构拓扑图。"""
        if self.hdb is None:
            return {}
        return self.hdb.get_hdb_report()

    def get_energy_timeline(self, ticks: int) -> list[dict]:
        """获取能量变化时间线。"""
        timeline = []
        for s in self.states[-ticks:]:
            tick_val = s.tick if hasattr(s, "tick") else s.get("tick", 0)
            if hasattr(s, "pool_snapshot") and s.pool_snapshot:
                summary = s.pool_snapshot.energy_summary
                if hasattr(summary, "model_dump"):
                    summary_dict = summary.model_dump()
                else:
                    summary_dict = dict(summary)
            else:
                summary_dict = s.get("pool_snapshot", {}).get("energy_summary", {})
            timeline.append({
                "tick": tick_val,
                "energy_summary": summary_dict
            })
        return timeline

    def get_action_log(self, limit: int) -> list[dict]:
        """获取行动日志。"""
        if self.action_sys is None:
            return []
        report = self.action_sys.get_action_report()
        return report.get("nodes", [])[:limit]

    def export_experiment_data(self, path: str) -> None:
        """导出实验数据到指定 JSON 文件中。"""
        import os
        dir_name = os.path.dirname(os.path.abspath(path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        serialized = []
        for s in self.states:
            if hasattr(s, "model_dump"):
                serialized.append(s.model_dump())
            else:
                serialized.append(s)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, default=str)

    @staticmethod
    def hash_report(report: dict) -> str:
        """所有报告数据应包含 SHA-256 哈希锚点。"""
        # Exclude hash itself from hash calculation to be pure
        rep_copy = {k: v for k, v in report.items() if k != "hash"}
        return _hash(rep_copy)
