"""依赖注入：单例 service / bridge / registry。

设计原则：
- 进程内单例（避免每请求重建）
- 支持测试覆盖（get_service() 等接口可在 fixture 里替换）
- 不引入 Docker / 任何外部服务
"""
from __future__ import annotations

import os
from functools import lru_cache

from cogcore.agent import CogCoreAgent
from cogcore.config import load_config
from cogcore.llm_bridge import LLMBridge
from cogcore.service import CogCoreService
from cogcore.tools import (
    LongTermExperienceTools,
    ToolRegistry,
    register_default_tools,
    register_long_term_tools,
)
from cogcore.tool_executor import ToolExecutor


@lru_cache(maxsize=1)
def get_config():
    """加载配置（单例）。"""
    return load_config()


@lru_cache(maxsize=1)
def get_service() -> CogCoreService:
    """获取 CogCoreService 单例。

    data_dir 从环境变量 COGCORE_SERVICE_DATA_DIR 读取，
    默认 ~/.cogcore 或 cogcore_data/。
    """
    data_dir = os.environ.get("COGCORE_SERVICE_DATA_DIR", "cogcore_data")
    svc = CogCoreService()
    svc.config.service.data_dir = data_dir
    svc.config.service.tick_interval = 0  # API 模式下不自动 tick
    return svc


@lru_cache(maxsize=1)
def get_bridge() -> LLMBridge:
    """LLM 桥接（单例）。"""
    return LLMBridge()


@lru_cache(maxsize=1)
def get_long_term_tools() -> LongTermExperienceTools:
    """长期经验工具（单例）。

    跟 service 的 hdb / pool 绑定。
    """
    svc = get_service()
    return LongTermExperienceTools(
        svc._hdb,
        svc._pool,
        db_path=os.path.join(svc._data_dir, "diary.db"),
    )


@lru_cache(maxsize=1)
def get_registry() -> ToolRegistry:
    """工具注册中心（单例）。"""
    tr = ToolRegistry()
    register_default_tools(tr)
    register_long_term_tools(tr, get_long_term_tools())
    return tr


@lru_cache(maxsize=1)
def get_executor() -> ToolExecutor:
    """工具执行器（单例）。"""
    return ToolExecutor(get_registry())


@lru_cache(maxsize=1)
def get_agent() -> CogCoreAgent:
    """完整 Agent（单例）。"""
    return CogCoreAgent(
        service=get_service(),
        bridge=get_bridge(),
        registry=get_registry(),
    )


def reset_singletons() -> None:
    """清空所有单例缓存（用于测试或 hot-reload）。"""
    get_config.cache_clear()
    get_service.cache_clear()
    get_bridge.cache_clear()
    get_long_term_tools.cache_clear()
    get_registry.cache_clear()
    get_executor.cache_clear()
    get_agent.cache_clear()
