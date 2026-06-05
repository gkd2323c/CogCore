"""CogCore 配置管理——从 config.toml 加载并校验。

用法：
    from cogcore.config import load_config, CogCoreConfig

    config = load_config()                          # 默认从项目根 config.toml
    config = load_config("path/to/config.toml")     # 指定路径
    config = load_config(env_prefix="COGCORE_")     # 环境变量覆盖

设计原则：
- TOML 作为唯一声明式来源
- 环境变量可覆盖（COGCORE_LLM_ENDPOINT 等）
- Pydantic 校验类型和边界
- 不硬编码任何敏感信息
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# Pydantic 配置模型
# ============================================================


class LLMConfig(BaseModel):
    """LLM 连接配置。"""

    endpoint: str = Field(default="http://localhost:11434", description="Ollama/vLLM 服务地址")
    model: str = Field(default="qwen3:8b", description="模型名称")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="生成温度")
    max_tokens: int = Field(default=4096, ge=64, le=65536, description="单次生成最大 token 数")
    timeout: int = Field(default=60, ge=5, le=600, description="API 请求超时秒数")
    max_turns: int = Field(default=10, ge=1, le=1000, description="对话循环最大轮数")
    stream: bool = Field(default=False, description="是否启用流式输出")


class PersistenceConfig(BaseModel):
    """持久化配置。"""

    backend: Literal["memory", "postgres", "sqlite"] = Field(default="memory", description="持久化后端")
    postgres_uri: str | None = Field(default=None, description="Postgres 连接字符串")
    sqlite_path: str | None = Field(default=None, description="SQLite 文件路径")


class RuntimeConfig(BaseModel):
    """运行时配置。"""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO", description="日志级别")
    mode: Literal["full_silent", "ap_agency", "reinforced_agency"] = Field(
        default="full_silent", description="运行模式"
    )


class CogCoreConfig(BaseModel):
    """CogCore 完整配置。"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


# ============================================================
# 加载器
# ============================================================


_CONFIG_CACHE: CogCoreConfig | None = None


def _find_config_toml() -> Path:
    """从 CWD 向上找 config.toml，找不到时回退到 CWD。"""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / "config.toml"
        if candidate.exists():
            return candidate
    return cwd / "config.toml"


def _apply_env_overrides(config: CogCoreConfig, prefix: str = "COGCORE_") -> CogCoreConfig:
    """用环境变量覆盖配置字段。

    COGCORE_LLM_ENDPOINT → config.llm.endpoint
    COGCORE_LLM_MODEL    → config.llm.model
    COGCORE_PERSISTENCE_BACKEND → config.persistence.backend
    COGCORE_RUNTIME_LOG_LEVEL   → config.runtime.log_level
    """
    mapping = {
        "LLM_ENDPOINT": ("llm", "endpoint"),
        "LLM_MODEL": ("llm", "model"),
        "LLM_TEMPERATURE": ("llm", "temperature"),
        "LLM_MAX_TOKENS": ("llm", "max_tokens"),
        "LLM_TIMEOUT": ("llm", "timeout"),
        "LLM_MAX_TURNS": ("llm", "max_turns"),
        "LLM_STREAM": ("llm", "stream"),
        "PERSISTENCE_BACKEND": ("persistence", "backend"),
        "PERSISTENCE_POSTGRES_URI": ("persistence", "postgres_uri"),
        "PERSISTENCE_SQLITE_PATH": ("persistence", "sqlite_path"),
        "RUNTIME_LOG_LEVEL": ("runtime", "log_level"),
        "RUNTIME_MODE": ("runtime", "mode"),
    }

    for env_key, (section, field) in mapping.items():
        full_key = f"{prefix}{env_key}"
        value = os.environ.get(full_key)
        if value is not None:
            section_obj = getattr(config, section)
            # 类型转换
            field_type = type(getattr(section_obj, field))
            if field_type is bool:
                parsed = value.lower() in ("true", "1", "yes")
            else:
                parsed = field_type(value)
            setattr(section_obj, field, parsed)

    return config


def load_config(path: str | None = None, *, use_cache: bool = True) -> CogCoreConfig:
    """加载 CogCore 配置。

    Args:
        path: TOML 文件路径。为 None 时自动查找。
        use_cache: 是否使用缓存（模块级单例）。默认 True。

    Returns:
        CogCoreConfig 实例。
    """
    global _CONFIG_CACHE

    if use_cache and _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    # 1. 确定路径
    config_path = Path(path) if path else _find_config_toml()

    # 2. 解析 TOML
    raw: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)

    # 3. 构造 Pydantic 模型（自动校验）
    config = CogCoreConfig(**raw)

    # 4. 环境变量覆盖
    config = _apply_env_overrides(config)

    if use_cache:
        _CONFIG_CACHE = config

    return config


def get_config() -> CogCoreConfig:
    """获取缓存的配置。未加载时自动调用 load_config。"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        return load_config()
    return _CONFIG_CACHE
