"""M3.4 节点级重试包装器。

使用 tenacity 实现指数退避随机抖动。
默认 3 次尝试，捕获可重试异常（网络/超时），不重试不可重试异常（编程错误）。

三层错误处理总览（M3.4）：
  L1 节点级 retry (本模块)
     - 临时错误（网络/超时）→ 指数退避重试
     - 编程错误（TypeError, ValueError, NotImplementedError）→ 立即失败
  L2 模型级 fallback (llm_registry.py)
     - LLM 调用失败 → 切下一个 provider
  L3 系统级教师门控 (modes.py / llm_bridge.teacher_gate_should_wake)
     - 持续异常 → 教师反馈合并 / 进入修复模式
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# ============================================================
# 错误分类
# ============================================================


# 默认可重试的异常（网络/超时/资源暂时不可用）
DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class NonRetryableError(Exception):
    """显式标记不可重试的异常。

    业务逻辑用 raise NonRetryableError("bad input") 可绕过重试。
    """


def is_retryable(exc: BaseException) -> bool:
    """判断一个异常是否属于"可重试"类。"""
    # 显式 NonRetryableError 不可重试
    if isinstance(exc, NonRetryableError):
        return False
    # 编程错误（永久）不可重试
    if isinstance(exc, (TypeError, ValueError, AttributeError, KeyError, NotImplementedError)):
        return False
    # 默认列表里的（网络/超时）可重试
    if isinstance(exc, DEFAULT_RETRYABLE_EXCEPTIONS):
        return True
    # 其他类型：保守起见**不**重试（防止意外循环）
    return False


# ============================================================
# 装饰器
# ============================================================


def with_retry(
    max_attempts: int = 3,
    base_delay_sec: float = 0.5,
    max_delay_sec: float = 8.0,
    retryable: tuple[type[BaseException], ...] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """装饰器：用 tenacity 给 fn 加重试。

    Args:
        max_attempts: 总尝试次数（包括第一次）
        base_delay_sec: 指数退避的基数
        max_delay_sec: 退避上限
        retryable: 自定义可重试异常元组（默认 DEFAULT_RETRYABLE_EXCEPTIONS）

    用法：
        @with_retry(max_attempts=3)
        def my_node(state):
            ...

    注意：LangGraph 节点是 bound closure，装饰节点函数体即可
    （不是在 graph.add_node 时包），因为 retry 在 fn 内部发生。
    """
    retry_types = retryable if retryable is not None else DEFAULT_RETRYABLE_EXCEPTIONS

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                for attempt in Retrying(
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_random_exponential(
                        multiplier=base_delay_sec, max=max_delay_sec
                    ),
                    retry=retry_if_exception_type(retry_types),
                    reraise=True,
                ):
                    with attempt:
                        return fn(*args, **kwargs)
            except RetryError as e:
                # tenacity 在最后一次失败时把原异常透传
                # (reraise=True)，所以这里几乎不会触发
                logger.error(
                    f"[retry] {fn.__name__} failed after {max_attempts} attempts: {e}"
                )
                raise e.last_attempt.exception() from e  # type: ignore[union-attr]

        return wrapper

    return decorator


# ============================================================
# 工具函数
# ============================================================


def run_with_retry(
    fn: Callable[..., T],
    *args: object,
    max_attempts: int = 3,
    base_delay_sec: float = 0.5,
    max_delay_sec: float = 8.0,
    retryable: tuple[type[BaseException], ...] | None = None,
) -> T:
    """单次调用版（不装饰，直接传 fn + args）。

    用法：
        run_with_retry(my_fn, arg1, arg2, max_attempts=5)
    """
    retry_types = retryable if retryable is not None else DEFAULT_RETRYABLE_EXCEPTIONS
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_random_exponential(
                multiplier=base_delay_sec, max=max_delay_sec
            ),
            retry=retry_if_exception_type(retry_types),
            reraise=True,
        ):
            with attempt:
                return fn(*args)
    except RetryError as e:
        logger.error(
            f"[retry] {fn.__name__} failed after {max_attempts} attempts: {e}"
        )
        raise e.last_attempt.exception() from e  # type: ignore[union-attr]
