"""LLMBridge 单元测试。mock OpenAI 客户端，不依赖真实 LLM。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cogcore.types import StimulusAtom, Modality, StimulusSource
from cogcore.llm_bridge import LLMBridge


# ============================================================
# fixture: mock OpenAI 客户端
# ============================================================

@pytest.fixture
def mock_openai():
    """构造 mock OpenAI 客户端，返回固定回复。"""
    client = MagicMock()
    # mock chat.completions.create
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "这是 LLM 的回复。"
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    client.chat.completions.create.return_value = mock_response
    return client


@pytest.fixture
def bridge(mock_openai):
    return LLMBridge(client=mock_openai)


# ============================================================
# 初始化
# ============================================================

def test_init_with_custom_client(mock_openai):
    b = LLMBridge(client=mock_openai)
    assert b._client is mock_openai


def test_init_reads_config_defaults():
    """无参数时从 config 读取默认值（不创建真实客户端）。"""
    b = LLMBridge()
    assert b.model is not None
    assert b.temperature > 0
    assert b.max_tokens > 0


# ============================================================
# chat
# ============================================================

def test_chat_returns_response(bridge):
    r = bridge.chat([{"role": "user", "content": "hello"}])
    assert r == "这是 LLM 的回复。"


def test_chat_passes_correct_params(bridge, mock_openai):
    bridge.chat([{"role": "user", "content": "test"}], temperature=0.5)
    mock_openai.chat.completions.create.assert_called_once()
    _, kwargs = mock_openai.chat.completions.create.call_args
    assert kwargs["temperature"] == 0.5
    assert kwargs["stream"] is False


def test_chat_error_returns_error_string(bridge, mock_openai):
    mock_openai.chat.completions.create.side_effect = Exception("connection refused")
    r = bridge.chat([{"role": "user", "content": "ping"}])
    assert r.startswith("[LLM Error")


# ============================================================
# chat_with_state
# ============================================================

def _make_mock_state(overrides=None):
    state = {
        "raw_input": "测试输入",
        "tick": 0,
        "nt_values": {"focus": 0.5, "arousal": 0.3, "caution": 0.4, "exploration": 0.2, "fatigue": 0.1, "stability": 0.6},
        "pool_snapshot": {"energy_summary": {"active_count": 3, "total_energy": 5.0, "cognitive_pressure": 0.5}},
        "cam": None,
        "hdb_snapshot": None,
        "feeling_signals": [],
        "new_atoms": [],
        "stages_log": ["stage_1", "stage_2"],
    }
    if overrides:
        state.update(overrides)
    return state


def test_chat_with_state_returns_tuple(bridge):
    packet, response = bridge.chat_with_state(_make_mock_state())
    assert isinstance(packet, str)
    assert isinstance(response, str)
    assert "[CURRENT INPUT]" in packet
    assert "测试输入" in packet


def test_chat_with_state_includes_8_audit_fields(bridge):
    packet, _ = bridge.chat_with_state(_make_mock_state())
    sections = [
        "[CURRENT INPUT]",
        "[ENERGY STATE]",
        "[NEUROTRANSMITTERS]",
        "[COGNITIVE FEELINGS]",
        "[ATTENTION FOCUS",
        "[MEMORY ANCHORS",
        "[ACTION CANDIDATES",
        "[PROMPT INSTRUCTIONS]",
    ]
    for s in sections:
        assert s in packet, f"Missing section: {s}"


def test_chat_with_state_with_feelings(bridge):
    state = _make_mock_state({
        "feeling_signals": [
            {"type": type("FT", (), {"value": "dissonance"})(), "intensity": 0.8},
        ]
    })
    packet, _ = bridge.chat_with_state(state)
    assert "dissonance" in packet


def test_chat_with_state_with_cam(bridge):
    cam_obj = {
        "items": [
            type("A", (), {
                "content": "重要记忆",
                "id": "abc-123",
                "source": type("S", (), {"value": "external"})(),
                "energy": type("E", (), {"real": 0.9, "virtual": 0.3})(),
            })(),
        ]
    }
    state = _make_mock_state({"cam": cam_obj})
    packet, _ = bridge.chat_with_state(state)
    assert "重要记忆" in packet


# ============================================================
# build_context_packet
# ============================================================

def test_build_context_packet_handles_empty_state(bridge):
    packet = bridge.build_context_packet({}, 1000)
    assert isinstance(packet, str)
    assert len(packet) > 0


def test_build_context_packet_truncation(bridge):
    """max_tokens 参数应缩短输出。"""
    short = bridge.build_context_packet({"raw_input": "x" * 500}, max_tokens=10)
    long = bridge.build_context_packet({"raw_input": "x" * 500}, max_tokens=500)
    assert len(short) < len(long)


# ============================================================
# parse_llm_output
# ============================================================

def test_parse_llm_output_returns_atoms(bridge):
    atoms = bridge.parse_llm_output("hello world")
    assert len(atoms) == 2
    assert all(isinstance(a, StimulusAtom) for a in atoms)
    assert atoms[0].content == "hello"
    assert atoms[1].content == "world"


def test_parse_llm_output_marks_internal_source(bridge):
    atoms = bridge.parse_llm_output("test")
    assert atoms[0].source == StimulusSource.INTERNAL


def test_parse_llm_output_empty(bridge):
    atoms = bridge.parse_llm_output("")
    assert atoms == []


# ============================================================
# teacher_gate
# ============================================================

def test_teacher_gate_default_wakes(bridge):
    assert bridge.teacher_gate_should_wake({}) is True


# ============================================================
# queue / merge teacher feedback
# ============================================================

def test_queue_and_merge_teacher_feedback(bridge):
    bridge.queue_teacher_feedback({"label": "good"})
    merged = bridge.merge_pending_teacher_feedback()
    assert isinstance(merged, list)
