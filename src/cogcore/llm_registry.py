"""LLMRegistry + LLMService：多 LLM provider 注册与 circular fallback。

M3.2 交付：
- LLMRegistry：管理多个 LLMBridge 实例（按 priority 排序）
- LLMService：调用入口，按优先级轮转，单个失败自动切下一个
- circular fallback：第一失败 → 第二 → ... → 回到第一（如果冷却已过）

设计原则：
- 健康状态：provider 有 "cooldown" 概念，失败后 N 秒内不再尝试
- 选择策略：跳过 cooldown 中的 provider，按 priority 升序选第一个健康者
- 完全失败：所有 provider 都 cooldown 中，抛 AllProvidersFailedError
- 不重试：单 provider 内不重试（避免 hang），失败直接跳下一个

用法：

    from cogcore.llm_registry import LLMRegistry, LLMService
    from cogcore.config import load_config

    cfg = load_config()
    registry = LLMRegistry.from_config(cfg.llm)
    service = LLMService(registry)
    response = service.chat([{"role": "user", "content": "hi"}])
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from cogcore.config import LLMConfig, LLMProviderConfig
from cogcore.llm_bridge import LLMBridge

logger = logging.getLogger(__name__)


# ============================================================
# 错误
# ============================================================


class AllProvidersFailedError(RuntimeError):
    """所有 LLM provider 都尝试失败。"""


# ============================================================
# Provider 包装
# ============================================================


@dataclass
class ManagedProvider:
    """一个被 registry 管理的 provider。"""

    config: LLMProviderConfig
    bridge: LLMBridge
    last_failure_at: float = 0.0  # unix timestamp
    consecutive_failures: int = 0
    total_calls: int = 0
    total_failures: int = 0

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_healthy(self) -> bool:
        """是否在冷却中（最近失败过且未到冷却时间）。"""
        if not self.config.enabled:
            return False
        if self.consecutive_failures == 0:
            return True
        return time.time() - self.last_failure_at > self._cooldown

    @property
    def _cooldown(self) -> float:
        if hasattr(self, "_custom_cooldown"):
            return self._custom_cooldown
        return float(self.config.timeout)  # 用 timeout 当 cooldown（简化）


# ============================================================
# Registry
# ============================================================


class LLMRegistry:
    """多 LLM provider 注册表。"""

    def __init__(self) -> None:
        self._providers: list[ManagedProvider] = []
        self._last_used_index: int = 0

    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> "LLMRegistry":
        """从 LLMConfig 构造 registry。

        - 如果 llm_config.providers 非空, 用 providers 列表
        - 否则回落到顶层 endpoint/model/api_key 构造单 provider
        """
        reg = cls()
        if llm_config.providers:
            for p in llm_config.providers:
                reg.add(
                    name=p.name,
                    endpoint=p.endpoint,
                    model=p.model,
                    api_key=p.api_key,
                    priority=p.priority,
                    enabled=p.enabled,
                    timeout=p.timeout,
                )
        else:
            # 顶层单 provider 模式
            reg.add(
                name="default",
                endpoint=llm_config.endpoint,
                model=llm_config.model,
                api_key=llm_config.api_key,
                priority=0,
                enabled=True,
                timeout=llm_config.timeout,
            )
        return reg

    def add(
        self,
        name: str,
        endpoint: str,
        model: str,
        bridge: LLMBridge | None = None,
        api_key: str | None = None,
        priority: int = 0,
        enabled: bool = True,
        timeout: int = 60,
    ) -> None:
        """注册一个 provider。"""
        cfg = LLMProviderConfig(
            name=name,
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            priority=priority,
            enabled=enabled,
            timeout=timeout,
        )
        if bridge is None:
            bridge = LLMBridge(
                api_type="openai",
                endpoint=endpoint,
                model=model,
                api_key=api_key,
                timeout=timeout,
            )
        self._providers.append(ManagedProvider(config=cfg, bridge=bridge))
        self._sort()

    def _sort(self) -> None:
        """按 priority 升序排序（数字小的优先）。"""
        self._providers.sort(key=lambda p: p.config.priority)

    def get(self, name: str) -> ManagedProvider | None:
        for p in self._providers:
            if p.name == name:
                return p
        return None

    def names(self) -> list[str]:
        return [p.name for p in self._providers]

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self):
        return iter(self._providers)

    def health_report(self) -> list[dict]:
        """每个 provider 的健康状态（用于 /v1/status 暴露）。"""
        return [
            {
                "name": p.name,
                "endpoint": p.config.endpoint,
                "model": p.config.model,
                "priority": p.config.priority,
                "enabled": p.config.enabled,
                "healthy": p.is_healthy,
                "consecutive_failures": p.consecutive_failures,
                "total_calls": p.total_calls,
                "total_failures": p.total_failures,
            }
            for p in self._providers
        ]


# ============================================================
# Service
# ============================================================


class LLMService:
    """LLM 调用服务：自动 fallback 到健康 provider。"""

    def __init__(
        self,
        registry: LLMRegistry,
        max_attempts: int = 3,
    ) -> None:
        self.registry = registry
        self.max_attempts = max_attempts

    def _select_healthy(self) -> ManagedProvider | None:
        """选一个健康的 provider。优先使用 last_used 之后的下一个，循环轮转。"""
        providers = list(self.registry)
        if not providers:
            return None
        n = len(providers)
        start = self.registry._last_used_index % n
        for offset in range(n):
            idx = (start + offset) % n
            p = providers[idx]
            if p.is_healthy:
                return p
        return None

    def _mark_failure(self, p: ManagedProvider, err: Exception) -> None:
        p.consecutive_failures += 1
        p.total_failures += 1
        p.last_failure_at = time.time()
        logger.warning(
            f"LLM provider '{p.name}' failed ({p.consecutive_failures}x): {err}"
        )

    def _mark_success(self, p: ManagedProvider) -> None:
        p.consecutive_failures = 0
        p.total_calls += 1
        self.registry._last_used_index = list(self.registry).index(p)
        logger.debug(f"LLM provider '{p.name}' OK")

    def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        **kwargs: object,
    ) -> str:
        """调用 LLM，自动 fallback。

        失败重试逻辑：
        - 最多 max_attempts 次尝试
        - 每次失败后跳到下一个健康 provider
        - 全部失败抛 AllProvidersFailedError

        失败检测：LLMBridge.chat() 会把异常转成 "[LLM Error: ...]" 字符串。
        本方法检测该前缀作为失败信号。
        """
        last_err: Exception | None = None
        last_err_str: str | None = None
        tried: set[str] = set()

        for attempt in range(self.max_attempts):
            p = self._select_healthy()
            if p is None:
                break
            if p.name in tried:
                break
            tried.add(p.name)
            try:
                result = p.bridge.chat(messages, system=system, **kwargs)
            except Exception as e:
                last_err = e
                self._mark_failure(p, e)
                logger.info(
                    f"Fallback from '{p.name}' (attempt {attempt + 1}/{self.max_attempts})"
                )
                continue

            # 检测 LLMBridge 把异常转为字符串的情况
            if isinstance(result, str) and result.startswith("[LLM Error:"):
                last_err_str = result
                err = RuntimeError(result)
                self._mark_failure(p, err)
                logger.info(
                    f"Fallback from '{p.name}' (attempt {attempt + 1}/{self.max_attempts}): {result}"
                )
                continue

            self._mark_success(p)
            return result

        msg = (
            f"All {len(self.registry)} LLM providers failed "
            f"(tried: {tried}, last error: {last_err or last_err_str})"
        )
        raise AllProvidersFailedError(msg)

    def build_context_packet(self, *args: object, **kwargs: object) -> str:
        """透传第一个健康 provider 的 build_context_packet。"""
        p = self._select_healthy()
        if p is None:
            raise AllProvidersFailedError("No healthy provider available")
        return p.bridge.build_context_packet(*args, **kwargs)

    def parse_llm_output(self, text: str) -> list:
        """透传第一个健康 provider 的 parse_llm_output。"""
        p = self._select_healthy()
        if p is None:
            raise AllProvidersFailedError("No healthy provider available")
        return p.bridge.parse_llm_output(text)
