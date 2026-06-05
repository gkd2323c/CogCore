"""PA 运行模式测试（M1.4）。"""
from __future__ import annotations

import pytest

from cogcore.llm_bridge import LLMBridge
from cogcore.modes import AgentMode, WakeController, WakeDecision


# ============================================================
# AgentMode
# ============================================================


def test_agent_mode_values():
    assert AgentMode.FULL_SILENT.value == "full_silent"
    assert AgentMode.AP_AGENCY.value == "ap_agency"
    assert AgentMode.REINFORCED_AGENCY.value == "reinforced_agency"


# ============================================================
# WakeController — external input
# ============================================================


def test_wake_with_external_input():
    wc = WakeController(mode=AgentMode.FULL_SILENT)
    d = wc.should_wake(event={"raw_input": "hello"})
    assert d.should_wake is True
    assert "external input" in d.reason


def test_wake_with_external_input_flag():
    wc = WakeController(mode=AgentMode.FULL_SILENT)
    d = wc.should_wake(event={"has_external_input": True})
    assert d.should_wake is True


# ============================================================
# WakeController — full_silent
# ============================================================


def test_full_silent_no_input_no_wake():
    wc = WakeController(mode=AgentMode.FULL_SILENT)
    d = wc.should_wake(event={})
    assert d.should_wake is False
    assert "full_silent" in d.reason


# ============================================================
# WakeController — ap_agency
# ============================================================


def test_ap_agency_wakes_with_high_drive():
    wc = WakeController(mode=AgentMode.AP_AGENCY, wake_drive_threshold=0.5)
    state = {"pool_snapshot": {"energy_summary": {"active_count": 10, "total_energy": 8.0}}}
    d = wc.should_wake(event={}, cogcore_state=state)
    assert d.should_wake is True
    assert d.wake_drive >= 0.5


def test_ap_agency_does_not_wake_with_low_drive():
    wc = WakeController(mode=AgentMode.AP_AGENCY, wake_drive_threshold=0.9)
    state = {"pool_snapshot": {"energy_summary": {"active_count": 1, "total_energy": 0.5}}}
    d = wc.should_wake(event={}, cogcore_state=state)
    assert d.should_wake is False


def test_ap_agency_drive_result():
    wc = WakeController(mode=AgentMode.AP_AGENCY, wake_drive_threshold=0.3)
    state = {"pool_snapshot": {"energy_summary": {"active_count": 5, "total_energy": 4.0}}}
    d = wc.should_wake(event={}, cogcore_state=state)
    assert isinstance(d.wake_drive, float)
    assert 0.0 <= d.wake_drive <= 1.0


# ============================================================
# WakeController — reinforced_agency
# ============================================================


def test_reinforced_teacher_gate_allows():
    wc = WakeController(mode=AgentMode.REINFORCED_AGENCY, wake_drive_threshold=0.3)
    state = {"pool_snapshot": {"energy_summary": {"active_count": 10, "total_energy": 8.0}}}
    d = wc.should_wake(event={}, cogcore_state=state, teacher_gate=lambda e, s: True)
    assert d.should_wake is True


def test_reinforced_teacher_gate_blocks():
    wc = WakeController(mode=AgentMode.REINFORCED_AGENCY, wake_drive_threshold=0.3)
    state = {"pool_snapshot": {"energy_summary": {"active_count": 10, "total_energy": 8.0}}}
    d = wc.should_wake(event={}, cogcore_state=state, teacher_gate=lambda e, s: False)
    assert d.should_wake is False
    assert "teacher gate rejected" in d.reason


# ============================================================
# WakeDecision
# ============================================================


def test_wake_decision_bool():
    assert bool(WakeDecision(True, "")) is True
    assert bool(WakeDecision(False, "")) is False


# ============================================================
# teacher_gate_should_wake (LLMBridge)
# ============================================================


def test_teacher_gate_allows_normal_state():
    b = LLMBridge()
    state = {"error_log": [], "pool_snapshot": {"energy_summary": {"cognitive_pressure": 0.3, "active_count": 3, "total_energy": 5.0}}, "nt_values": {"fatigue": 0.2}}
    assert b.teacher_gate_should_wake({}, state) is True


def test_teacher_gate_blocks_high_pressure():
    b = LLMBridge()
    state = {"error_log": [], "pool_snapshot": {"energy_summary": {"cognitive_pressure": 0.9, "active_count": 3, "total_energy": 5.0}}, "nt_values": {"fatigue": 0.2}}
    assert b.teacher_gate_should_wake({}, state) is False


def test_teacher_gate_blocks_high_fatigue():
    b = LLMBridge()
    state = {"error_log": [], "pool_snapshot": {"energy_summary": {"cognitive_pressure": 0.3, "active_count": 3, "total_energy": 5.0}}, "nt_values": {"fatigue": 0.9}}
    assert b.teacher_gate_should_wake({}, state) is False


def test_teacher_gate_blocks_errors():
    b = LLMBridge()
    state = {"error_log": ["err1", "err2", "err3"], "pool_snapshot": {"energy_summary": {"cognitive_pressure": 0.3, "active_count": 3, "total_energy": 5.0}}, "nt_values": {"fatigue": 0.2}}
    assert b.teacher_gate_should_wake({}, state) is False


def test_teacher_gate_empty_state():
    b = LLMBridge()
    assert b.teacher_gate_should_wake({}, {}) is True
