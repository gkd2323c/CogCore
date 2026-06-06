"""M5.3 场景 3 — 人工干预 (HITL) 状态机。

Human-in-the-loop：当 reinforced_agency 模式下教师门控拒绝时，
生成人工干预请求，挂起 Agent 直到人工审批通过。

与 WakeController.teacher_gate 联动：
  teacher_gate(event, state) → False → HITLManager.create_request() → Agent 挂起
  人工 POST /hitl/respond/{id} → HITLManager.approve() → teacher_gate 下次返回 True
"""
from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Any, Callable


@dataclasses.dataclass
class HITLRequest:
    """人工干预请求。"""

    id: str
    status: str  # pending / approved / rejected / timeout
    prompt: str
    response: str = ""
    created_ts: float = 0.0
    timeout_ts: float = 0.0
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class HITLManager:
    """人工干预管理器。

    维护 pending 请求队列，提供 teacher_gate 函数给 WakeController。
    """

    def __init__(self, default_timeout: int = 300) -> None:
        self._requests: dict[str, HITLRequest] = {}
        self._default_timeout = default_timeout
        self._approved_ids: set[str] = set()
        self._rejected_ids: set[str] = set()

    # ============================================================
    # 请求生命周期
    # ============================================================

    def create_request(self, prompt: str, metadata: dict[str, Any] | None = None) -> HITLRequest:
        """创建新的人工干预请求。"""
        now = time.time()
        req = HITLRequest(
            id=str(uuid.uuid4())[:8],
            status="pending",
            prompt=prompt,
            created_ts=now,
            timeout_ts=now + self._default_timeout,
            metadata=metadata or {},
        )
        self._requests[req.id] = req
        return req

    def approve(self, request_id: str, response: str = "approved") -> HITLRequest | None:
        """人工审批通过。"""
        req = self._requests.get(request_id)
        if req is None:
            return None
        req.status = "approved"
        req.response = response
        self._approved_ids.add(request_id)
        return req

    def reject(self, request_id: str, response: str = "rejected") -> HITLRequest | None:
        """人工审批拒绝。"""
        req = self._requests.get(request_id)
        if req is None:
            return None
        req.status = "rejected"
        req.response = response
        self._rejected_ids.add(request_id)
        return req

    def get_request(self, request_id: str) -> HITLRequest | None:
        """获取单个请求。"""
        return self._requests.get(request_id)

    def list_pending(self) -> list[HITLRequest]:
        """列出所有 pending 请求（自动清理超时）。"""
        now = time.time()
        pending = []
        for req in list(self._requests.values()):
            if req.status == "pending" and req.timeout_ts < now:
                req.status = "timeout"
            if req.status == "pending":
                pending.append(req)
        return pending

    def list_all(self) -> list[HITLRequest]:
        """列出所有请求。"""
        return list(self._requests.values())

    # ============================================================
    # teacher_gate 集成
    # ============================================================

    def teacher_gate(self, event: dict, state: dict) -> bool:
        """作为 WakeController 的 teacher_gate 函数使用。

        逻辑：
        - 如果有已批准的请求 → 通过（清除批准记录）
        - 如果有 pending 请求 → 拒绝（等待人工）
        - 无请求 → 通过（首次放行）
        """
        # 检查是否有已批准的请求（人工已回复）
        if self._approved_ids:
            # 消费一个批准，允许本次唤醒
            self._approved_ids.pop()
            return True

        # 检查是否有 pending 请求（还在等人工）
        pending = self.list_pending()
        if pending:
            return False

        # 无历史请求 → 通过
        return True

    def teacher_gate_with_auto_create(
        self,
        event: dict,
        state: dict,
        prompt: str = "Agent requests human approval for next action",
    ) -> bool:
        """增强版 teacher_gate：拒绝时自动创建 HITL 请求。"""
        result = self.teacher_gate(event, state)
        if not result:
            # 已经因为 pending 而拒绝，无需重复创建
            pending = self.list_pending()
            if not pending:
                self.create_request(prompt, metadata={"event": event, "state": state})
        return result

    # ============================================================
    # 统计
    # ============================================================

    def stats(self) -> dict[str, Any]:
        all_reqs = self.list_all()
        return {
            "total": len(all_reqs),
            "pending": sum(1 for r in all_reqs if r.status == "pending"),
            "approved": sum(1 for r in all_reqs if r.status == "approved"),
            "rejected": sum(1 for r in all_reqs if r.status == "rejected"),
            "timeout": sum(1 for r in all_reqs if r.status == "timeout"),
        }
