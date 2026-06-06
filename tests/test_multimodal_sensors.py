"""M5.4 E24 — 多模态感受器测试。"""
from __future__ import annotations

from cogcore.multimodal_sensors import AudioSensor, ImageSensor, ToolStateSensor
from cogcore.state_pool import StatePool


# ============================================================
# ImageSensor
# ============================================================


def test_image_sensor_with_metadata():
    sensor = ImageSensor()
    atoms = sensor.parse("fake_b64", {"color": "red", "object": "car"}, birth_tick=5)
    assert len(atoms) == 2
    contents = [a.content for a in atoms]
    assert "image_color_red" in contents
    assert "image_object_car" in contents
    assert atoms[0].modality.value == "visual"
    assert atoms[0].birth_tick == 5


def test_image_sensor_unknown():
    sensor = ImageSensor()
    atoms = sensor.parse("fake_b64", {}, birth_tick=0)
    assert len(atoms) == 1
    assert atoms[0].content == "image_unknown"


# ============================================================
# AudioSensor
# ============================================================


def test_audio_sensor_emotion():
    sensor = AudioSensor()
    atoms = sensor.parse("I am very happy today", {}, birth_tick=1)
    contents = [a.content for a in atoms]
    assert any("happy" in c for c in contents)
    assert atoms[0].modality.value == "audio"


def test_audio_sensor_neutral():
    sensor = AudioSensor()
    atoms = sensor.parse("The weather is fine", {}, birth_tick=0)
    assert len(atoms) == 1
    assert atoms[0].content == "audio_neutral"


# ============================================================
# ToolStateSensor
# ============================================================


def test_tool_state_sensor_success():
    sensor = ToolStateSensor()
    atoms = sensor.parse({"tool": "read_file", "status": "ok", "output": "hello"}, {}, birth_tick=2)
    assert len(atoms) == 1
    assert atoms[0].content == "tool_read_file_ok"
    assert atoms[0].modality.value == "tool_state"


def test_tool_state_sensor_error():
    sensor = ToolStateSensor()
    atoms = sensor.parse({"tool": "run_tests", "status": "error", "output": "AssertionError"}, {}, birth_tick=0)
    assert len(atoms) == 2
    contents = [a.content for a in atoms]
    assert "tool_run_tests_error" in contents
    assert "tool_run_tests_error_signal" in contents


# ============================================================
# 入池集成
# ============================================================


def test_multimodal_atoms_enter_pool():
    """多模态 atoms 能进入 StatePool。"""
    pool = StatePool()
    img = ImageSensor()
    audio = AudioSensor()
    tool = ToolStateSensor()

    pool.add(img.parse("b64", {"color": "blue"}, 0)[0])
    pool.add(audio.parse("sad mood", {}, 0)[0])
    pool.add(tool.parse({"tool": "git_status", "status": "ok"}, {}, 0)[0])

    all_atoms = pool.get_all()
    contents = [a.content for a in all_atoms]
    assert "image_color_blue" in contents
    assert any("sad" in c for c in contents)
    assert "tool_git_status_ok" in contents
