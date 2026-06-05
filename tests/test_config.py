"""CogCore 配置模块测试。覆盖 TOML 加载、环境变量覆盖、缓存、查找。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from cogcore.config import CogCoreConfig, LLMConfig, PersistenceConfig, RuntimeConfig, load_config, get_config


# ============================================================
# Config 模型
# ============================================================

def test_llm_config_defaults():
    c = LLMConfig()
    assert c.api_type == "openai"
    assert c.endpoint == "http://localhost:11434/v1"
    assert c.api_key is None
    assert c.model is not None
    assert 0.0 <= c.temperature <= 2.0
    assert 64 <= c.max_tokens <= 65536


def test_runtime_config_defaults():
    c = RuntimeConfig()
    assert c.log_level == "INFO"
    assert c.mode == "full_silent"


def test_persistence_config_defaults():
    c = PersistenceConfig()
    assert c.backend == "memory"
    assert c.postgres_uri is None
    assert c.sqlite_path is None


def test_cogcore_config_defaults():
    c = CogCoreConfig()
    assert c.llm.model is not None
    assert c.persistence.backend == "memory"
    assert c.runtime.mode == "full_silent"


# ============================================================
# TOML 加载
# ============================================================

def test_load_from_toml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8") as f:
        f.write('''
[llm]
endpoint = "http://192.168.1.100:11434"
model = "llama3.2:3b"
temperature = 0.3

[runtime]
log_level = "DEBUG"
mode = "ap_agency"
''')
        tmp = f.name

    try:
        cfg = load_config(tmp, use_cache=False)
        assert cfg.llm.endpoint == "http://192.168.1.100:11434"
        assert cfg.llm.model == "llama3.2:3b"
        assert cfg.llm.temperature == 0.3
        assert cfg.runtime.log_level == "DEBUG"
        assert cfg.runtime.mode == "ap_agency"
        # 未设置的字段保持默认
        assert cfg.llm.max_tokens == 4096
        assert cfg.persistence.backend == "memory"
    finally:
        os.unlink(tmp)


def test_load_from_partial_toml():
    """部分设置时，未填字段保持默认值。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8") as f:
        f.write('[llm]\nmodel = "test-model"\n')
        tmp = f.name

    try:
        cfg = load_config(tmp, use_cache=False)
        assert cfg.llm.model == "test-model"
        assert cfg.llm.endpoint == "http://localhost:11434/v1"  # 默认
        assert cfg.llm.temperature == 0.7  # 默认
    finally:
        os.unlink(tmp)


# ============================================================
# 环境变量覆盖
# ============================================================

def test_env_override():
    """环境变量 COGCORE_LLM_MODEL 应覆盖 TOML 中的 model。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8") as f:
        f.write('[llm]\nmodel = "toml-model"\n')
        tmp = f.name

    os.environ["COGCORE_LLM_MODEL"] = "env-model"
    os.environ["COGCORE_LLM_ENDPOINT"] = "http://env:11434"
    os.environ["COGCORE_RUNTIME_LOG_LEVEL"] = "DEBUG"

    try:
        cfg = load_config(tmp, use_cache=False)
        assert cfg.llm.model == "env-model"  # 环境变量优先
        assert cfg.llm.endpoint == "http://env:11434"
        assert cfg.runtime.log_level == "DEBUG"
    finally:
        del os.environ["COGCORE_LLM_MODEL"]
        del os.environ["COGCORE_LLM_ENDPOINT"]
        del os.environ["COGCORE_RUNTIME_LOG_LEVEL"]


def test_env_override_boolean():
    os.environ["COGCORE_LLM_STREAM"] = "true"
    try:
        cfg = load_config(use_cache=False)
        assert cfg.llm.stream is True
    finally:
        del os.environ["COGCORE_LLM_STREAM"]


def test_env_override_int():
    os.environ["COGCORE_LLM_TIMEOUT"] = "120"
    try:
        cfg = load_config(use_cache=False)
        assert cfg.llm.timeout == 120
    finally:
        del os.environ["COGCORE_LLM_TIMEOUT"]


# ============================================================
# 缓存
# ============================================================

def test_config_cache_out_of_order():
    """get_config 在未初始化时应自动调用 load_config。"""
    from cogcore import config as cfg_module
    cfg_module._CONFIG_CACHE = None
    c = get_config()
    assert c.llm.model == "qwen3.5:latest"
    assert isinstance(c, CogCoreConfig)


def test_config_cache_hit():
    """load_config 两次应返回同一对象（use_cache=True）。"""
    a = load_config(use_cache=True)
    b = load_config(use_cache=True)
    assert a is b


def test_config_cache_miss():
    """use_cache=False 应每次都加载。"""
    a = load_config(use_cache=False)
    b = load_config(use_cache=False)
    assert a is not b
