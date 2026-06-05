"""节点级重试测试 (M3.4 L1)。"""
from __future__ import annotations

import time

import pytest

from cogcore.retry import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    NonRetryableError,
    is_retryable,
    run_with_retry,
    with_retry,
)


# ============================================================
# is_retryable 分类
# ============================================================


def test_is_retryable_network():
    assert is_retryable(ConnectionError()) is True
    assert is_retryable(TimeoutError()) is True
    assert is_retryable(OSError()) is True


def test_is_retryable_programming_errors():
    assert is_retryable(TypeError()) is False
    assert is_retryable(ValueError()) is False
    assert is_retryable(AttributeError()) is False
    assert is_retryable(KeyError()) is False
    assert is_retryable(NotImplementedError()) is False


def test_is_retryable_non_retryable_marker():
    assert is_retryable(NonRetryableError("bad")) is False


def test_is_retryable_unknown_defaults_to_false():
    """未明确分类的异常默认不可重试, 防止意外循环。"""
    assert is_retryable(RuntimeError()) is False
    assert is_retryable(ZeroDivisionError()) is False


# ============================================================
# with_retry 装饰器
# ============================================================


def test_with_retry_succeeds_first_try():
    calls = []

    @with_retry(max_attempts=3)
    def fn(x):
        calls.append(x)
        return x * 2

    assert fn(5) == 10
    assert len(calls) == 1


def test_with_retry_eventually_succeeds():
    calls = []

    @with_retry(max_attempts=3, base_delay_sec=0.01, max_delay_sec=0.05)
    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("transient")
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 3


def test_with_retry_gives_up_after_max_attempts():
    calls = []

    @with_retry(max_attempts=3, base_delay_sec=0.01, max_delay_sec=0.05)
    def fn():
        calls.append(1)
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        fn()
    assert len(calls) == 3  # 3 attempts


def test_with_retry_does_not_retry_programming_errors():
    calls = []

    @with_retry(max_attempts=5)
    def fn():
        calls.append(1)
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        fn()
    assert len(calls) == 1  # 不重试, 立即失败


def test_with_retry_does_not_retry_non_retryable_marker():
    calls = []

    @with_retry(max_attempts=3)
    def fn():
        calls.append(1)
        raise NonRetryableError("explicit")

    with pytest.raises(NonRetryableError):
        fn()
    assert len(calls) == 1


def test_with_retry_custom_retryable():
    calls = []

    @with_retry(max_attempts=3, base_delay_sec=0.01, retryable=(RuntimeError,))
    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("transient")
        return "done"

    assert fn() == "done"
    assert len(calls) == 2


def test_with_retry_exponential_backoff_takes_time():
    """3 次重试 + 退避至少花 0.5s。"""

    @with_retry(max_attempts=3, base_delay_sec=0.1, max_delay_sec=0.5)
    def fn():
        raise ConnectionError("x")

    t0 = time.time()
    with pytest.raises(ConnectionError):
        fn()
    elapsed = time.time() - t0
    # 3 attempts, 2 inter-attempt waits
    # delays: ~0.1*rand(0,1), ~0.1*rand(1,2) = ~0.15 minimum
    assert elapsed >= 0.1  # 至少有点退避


# ============================================================
# run_with_retry 单次调用
# ============================================================


def test_run_with_retry_basic():
    def fn(x, y):
        return x + y

    assert run_with_retry(fn, 2, 3) == 5


def test_run_with_retry_eventually_succeeds():
    counter = {"n": 0}

    def fn():
        counter["n"] += 1
        if counter["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert run_with_retry(fn, max_attempts=5, base_delay_sec=0.01) == "ok"
    assert counter["n"] == 3


def test_run_with_retry_propagates_original_exception():
    def fn():
        raise ConnectionError("original error")

    with pytest.raises(ConnectionError) as exc_info:
        run_with_retry(fn, max_attempts=2, base_delay_sec=0.01)
    assert "original error" in str(exc_info.value)


# ============================================================
# 集成：图节点级重试
# ============================================================


def test_graph_node_with_retry_integration():
    """图节点用 with_retry 包装, 临时错误会被重试。"""
    from cogcore.graph import build_cogcore_graph, invoke_cogcore
    from cogcore.state_pool import StatePool
    from cogcore.hdb import HDB
    from cogcore.attention import Attention
    from cogcore.cfs import CognitiveFeelingSystem
    from cogcore.nt import NeurotransmitterSystem
    from cogcore.action_system import ActionSystem
    from cogcore.adaptive_tuner import AdaptiveTuner

    modules = {
        "pool": StatePool(),
        "hdb": HDB(),
        "cfs": CognitiveFeelingSystem(),
        "attention": Attention(),
        "nt_sys": NeurotransmitterSystem(),
        "action_sys": ActionSystem(),
        "tuner": AdaptiveTuner(),
    }
    g = build_cogcore_graph(modules)
    state = invoke_cogcore(g, "retry test input", 0, "retry-test")
    # 10 个 stage 全部跑通
    assert len(state.get("stages_log", [])) == 10
