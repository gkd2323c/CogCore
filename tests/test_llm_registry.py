"""LLMRegistry + LLMService 单元测试（M3.2）。

不发起真实 LLM 调用, 全部用 mock。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cogcore.config import LLMConfig, LLMProviderConfig
from cogcore.llm_bridge import LLMBridge
from cogcore.llm_registry import (
    AllProvidersFailedError,
    LLMRegistry,
    LLMService,
    ManagedProvider,
)


# ============================================================
# Fixtures
# ============================================================


def _mock_bridge(response: str = "Mocked") -> LLMBridge:
    """构造一个返回固定文本的 mock LLMBridge。"""
    client = MagicMock()
    mr = MagicMock()
    mc = MagicMock()
    mc.content = response
    mr.choices = [type("c", (), {"message": mc})()]
    client.chat.completions.create.return_value = mr
    return LLMBridge(client=client)


def _failing_bridge(error: Exception | None = None) -> LLMBridge:
    """构造一个调用就抛错的 mock LLMBridge。"""
    client = MagicMock()
    client.chat.completions.create.side_effect = error or RuntimeError("provider down")
    return LLMBridge(client=client)


# ============================================================
# Registry 基础
# ============================================================


def test_registry_empty():
    reg = LLMRegistry()
    assert len(reg) == 0
    assert reg.names() == []


def test_registry_add_and_get():
    reg = LLMRegistry()
    bridge = _mock_bridge("ok")
    reg.add(name="a", endpoint="http://a", model="ma", bridge=bridge, priority=1)
    reg.add(name="b", endpoint="http://b", model="mb", bridge=_mock_bridge("ok"), priority=2)
    assert len(reg) == 2
    assert reg.names() == ["a", "b"]  # priority 升序
    assert reg.get("a").name == "a"


def test_registry_priority_sort():
    reg = LLMRegistry()
    reg.add(name="z", endpoint="x", model="y", bridge=_mock_bridge(), priority=99)
    reg.add(name="a", endpoint="x", model="y", bridge=_mock_bridge(), priority=1)
    reg.add(name="m", endpoint="x", model="y", bridge=_mock_bridge(), priority=50)
    assert reg.names() == ["a", "m", "z"]


def test_registry_from_config_top_level():
    cfg = LLMConfig(
        endpoint="http://x",
        model="m1",
        api_key="k1",
    )
    reg = LLMRegistry.from_config(cfg)
    assert len(reg) == 1
    p = list(reg)[0]
    assert p.config.endpoint == "http://x"
    assert p.config.model == "m1"
    assert p.config.api_key == "k1"


def test_registry_from_config_providers():
    cfg = LLMConfig(
        providers=[
            LLMProviderConfig(name="p1", endpoint="http://1", model="m1", priority=2),
            LLMProviderConfig(name="p2", endpoint="http://2", model="m2", priority=1),
        ]
    )
    reg = LLMRegistry.from_config(cfg)
    assert len(reg) == 2
    assert reg.names() == ["p2", "p1"]  # priority 升序


def test_registry_health_report():
    reg = LLMRegistry()
    reg.add("a", "http://a", "m", _mock_bridge("ok"), priority=1)
    reg.add("b", "http://b", "m", _failing_bridge(), priority=2)
    report = reg.health_report()
    assert len(report) == 2
    assert report[0]["name"] == "a"
    assert report[0]["healthy"] is True
    assert report[1]["name"] == "b"


# ============================================================
# Service：fallback 行为
# ============================================================


def test_service_first_provider_succeeds():
    reg = LLMRegistry()
    reg.add("primary", "http://1", "m", _mock_bridge("P1"), priority=1)
    reg.add("backup", "http://2", "m", _mock_bridge("P2"), priority=2)
    svc = LLMService(reg, max_attempts=3)
    result = svc.chat([{"role": "user", "content": "hi"}])
    assert result == "P1"


def test_service_fallback_to_backup():
    reg = LLMRegistry()
    reg.add("primary", "http://1", "m", _failing_bridge(), priority=1)
    reg.add("backup", "http://2", "m", _mock_bridge("BACKUP"), priority=2)
    svc = LLMService(reg, max_attempts=3)
    result = svc.chat([{"role": "user", "content": "hi"}])
    assert result == "BACKUP"


def test_service_all_providers_fail():
    reg = LLMRegistry()
    reg.add("a", "http://1", "m", _failing_bridge(), priority=1)
    reg.add("b", "http://2", "m", _failing_bridge(), priority=2)
    svc = LLMService(reg, max_attempts=3)
    with pytest.raises(AllProvidersFailedError) as exc_info:
        svc.chat([{"role": "user", "content": "hi"}])
    assert "a" in str(exc_info.value) or "b" in str(exc_info.value)


def test_service_skip_cooldown_provider():
    """失败过的 provider 进入冷却, 第二次 chat 不再尝试它。"""
    reg = LLMRegistry()
    reg.add("flaky", "http://1", "m", _failing_bridge(), priority=1)
    reg.add("good", "http://2", "m", _mock_bridge("GOOD"), priority=2)
    svc = LLMService(reg, max_attempts=3)
    # 第一次：flaky 失败, 走 good
    r1 = svc.chat([{"role": "user", "content": "hi"}])
    assert r1 == "GOOD"
    # flaky 现在 consecutive_failures > 0, 在冷却中
    flaky = reg.get("flaky")
    assert flaky.consecutive_failures == 1
    assert flaky.is_healthy is False
    # 第二次：直接选 good
    r2 = svc.chat([{"role": "user", "content": "hi"}])
    assert r2 == "GOOD"


def test_service_disabled_provider_skipped():
    reg = LLMRegistry()
    reg.add("disabled", "http://1", "m", _mock_bridge("D"), priority=1, enabled=False)
    reg.add("enabled", "http://2", "m", _mock_bridge("E"), priority=2)
    svc = LLMService(reg, max_attempts=3)
    result = svc.chat([{"role": "user", "content": "hi"}])
    assert result == "E"


def test_service_max_attempts_limit():
    """max_attempts=2 时只尝试 2 次, 第 3 个 provider 不被尝试。"""
    reg = LLMRegistry()
    reg.add("a", "http://1", "m", _failing_bridge(), priority=1)
    reg.add("b", "http://2", "m", _failing_bridge(), priority=2)
    reg.add("c", "http://3", "m", _mock_bridge("C"), priority=3)
    svc = LLMService(reg, max_attempts=2)
    with pytest.raises(AllProvidersFailedError):
        svc.chat([{"role": "user", "content": "hi"}])


def test_service_skip_disabled_provider():
    """disabled provider 永远被跳过。"""
    reg = LLMRegistry()
    reg.add("a", "http://1", "m", _mock_bridge("A"), priority=1, enabled=False)
    reg.add("b", "http://2", "m", _mock_bridge("B"), priority=2)
    svc = LLMService(reg, max_attempts=3)
    result = svc.chat([{"role": "user", "content": "hi"}])
    assert result == "B"


# ============================================================
# Health report
# ============================================================


def test_health_report_after_calls():
    """两个 provider 都有调用记录, 失败次数递增。"""
    reg = LLMRegistry()
    reg.add("a", "http://1", "m", _failing_bridge(), priority=1)
    reg.add("b", "http://2", "m", _mock_bridge("B"), priority=2)
    svc = LLMService(reg, max_attempts=2)
    # a 失败 → fallback 到 b 成功
    result = svc.chat([{"role": "user", "content": "hi"}])
    assert result == "B"
    report = reg.health_report()
    a = next(r for r in report if r["name"] == "a")
    b = next(r for r in report if r["name"] == "b")
    assert a["total_failures"] == 1
    assert a["consecutive_failures"] == 1
    assert b["total_calls"] == 1
    assert b["consecutive_failures"] == 0
