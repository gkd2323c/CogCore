"""M5.3 场景 3 — HITL 测试。"""
from __future__ import annotations

import time

from cogcore.hitl import HITLManager, HITLRequest


# ============================================================
# HITLManager 单元测试
# ============================================================


def test_create_request():
    mgr = HITLManager()
    req = mgr.create_request("Test prompt", {"key": "val"})
    assert isinstance(req, HITLRequest)
    assert req.status == "pending"
    assert req.prompt == "Test prompt"
    assert req.metadata == {"key": "val"}
    assert len(req.id) > 0


def test_approve_and_reject():
    mgr = HITLManager()
    req = mgr.create_request("Approve me")
    assert mgr.approve(req.id, "go ahead").status == "approved"
    assert mgr.get_request(req.id).response == "go ahead"

    req2 = mgr.create_request("Reject me")
    assert mgr.reject(req2.id, "no way").status == "rejected"
    assert mgr.get_request(req2.id).response == "no way"


def test_list_pending_and_timeout():
    mgr = HITLManager(default_timeout=1)
    req = mgr.create_request("Will timeout")
    pending = mgr.list_pending()
    assert len(pending) == 1
    assert pending[0].id == req.id

    time.sleep(1.1)
    pending_after = mgr.list_pending()
    assert len(pending_after) == 0
    assert mgr.get_request(req.id).status == "timeout"


def test_teacher_gate_flow():
    """teacher_gate 完整流程：首次通过 → 创建 pending → 拒绝 → 批准 → 通过。"""
    mgr = HITLManager()

    # 首次无历史 → 通过
    assert mgr.teacher_gate({}, {}) is True

    # 创建 pending 请求
    req = mgr.create_request("Need approval")
    # 有 pending → 拒绝
    assert mgr.teacher_gate({}, {}) is False

    # 人工批准
    mgr.approve(req.id)
    # 有 approved → 通过（消费掉）
    assert mgr.teacher_gate({}, {}) is True
    # 消费后再次拒绝（因为 pending 已清）
    assert mgr.teacher_gate({}, {}) is True  # 无 pending，通过


def test_teacher_gate_auto_create():
    mgr = HITLManager()
    # 首次通过，不会创建
    assert mgr.teacher_gate_with_auto_create({}, {}) is True
    assert len(mgr.list_pending()) == 0

    # 模拟：手动创建 pending，下次 gate 自动创建（如果无 pending）
    # 实际上 auto_create 只在 teacher_gate 返回 False 且无 pending 时创建
    # 这里直接测试：有 pending 时不重复创建
    req = mgr.create_request("Existing")
    assert mgr.teacher_gate_with_auto_create({}, {}) is False
    assert len(mgr.list_pending()) == 1  # 不重复创建


# ============================================================
# API 集成测试
# ============================================================


def test_api_create_request(client):
    r = client.post("/v1/hitl/request", json={"prompt": "API test", "metadata": {"x": 1}})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pending"
    assert data["prompt"] == "API test"


def test_api_list_pending(client):
    client.post("/v1/hitl/request", json={"prompt": "P1"})
    client.post("/v1/hitl/request", json={"prompt": "P2"})
    r = client.get("/v1/hitl/pending")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2


def test_api_respond_approve(client):
    create_r = client.post("/v1/hitl/request", json={"prompt": "Approve this"})
    req_id = create_r.json()["id"]
    r = client.post(f"/v1/hitl/respond/{req_id}", json={"response": "OK", "action": "approve"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_api_respond_reject(client):
    create_r = client.post("/v1/hitl/request", json={"prompt": "Reject this"})
    req_id = create_r.json()["id"]
    r = client.post(f"/v1/hitl/respond/{req_id}", json={"response": "NO", "action": "reject"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_api_stats(client):
    r = client.get("/v1/hitl/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "pending" in data
