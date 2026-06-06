"""M5.1 serve CLI 测试。"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cogcore.serve import _build_parser, _ensure_data_dir, main, serve


# ============================================================
# 参数解析
# ============================================================


def test_parser_defaults():
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.reload is False
    assert args.data_dir == "cogcore_data"
    assert args.workers == 1


def test_parser_custom_args():
    parser = _build_parser()
    args = parser.parse_args(["--host", "0.0.0.0", "--port", "8080", "--reload", "--data-dir", "/tmp/cogcore", "--workers", "2"])
    assert args.host == "0.0.0.0"
    assert args.port == 8080
    assert args.reload is True
    assert args.data_dir == "/tmp/cogcore"
    assert args.workers == 2


# ============================================================
# 数据目录
# ============================================================


def test_ensure_data_dir_creates(tmp_path):
    sub = tmp_path / "new_sub" / "cogcore"
    result = _ensure_data_dir(str(sub))
    assert Path(result).exists()
    assert Path(result).is_dir()


def test_ensure_data_dir_expands_tilde(monkeypatch, tmp_path):
    # Windows uses USERPROFILE, not HOME
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _ensure_data_dir("~/cogcore_test")
    assert result.startswith(str(tmp_path))
    assert Path(result).exists()


# ============================================================
# serve() 启动
# ============================================================


def test_serve_sets_env_var(tmp_path):
    data_dir = str(tmp_path / "data")
    with patch("cogcore.serve._setup_signal_handlers"):
        with patch("uvicorn.run") as mock_uvicorn:
            serve(host="127.0.0.1", port=9000, data_dir=data_dir)
    assert os.environ.get("COGCORE_SERVICE_DATA_DIR") == data_dir
    mock_uvicorn.assert_called_once()
    call_kwargs = mock_uvicorn.call_args.kwargs
    assert call_kwargs["host"] == "127.0.0.1"
    assert call_kwargs["port"] == 9000


def test_serve_reload_forces_single_worker(tmp_path):
    data_dir = str(tmp_path / "data")
    with patch("cogcore.serve._setup_signal_handlers"):
        with patch("uvicorn.run") as mock_uvicorn:
            serve(data_dir=data_dir, reload=True, workers=4)
    call_kwargs = mock_uvicorn.call_args.kwargs
    assert call_kwargs["reload"] is True
    assert call_kwargs["workers"] == 1


def test_serve_no_reload_uses_workers(tmp_path):
    data_dir = str(tmp_path / "data")
    with patch("cogcore.serve._setup_signal_handlers"):
        with patch("uvicorn.run") as mock_uvicorn:
            serve(data_dir=data_dir, reload=False, workers=3)
    call_kwargs = mock_uvicorn.call_args.kwargs
    assert call_kwargs["reload"] is False
    assert call_kwargs["workers"] == 3


def test_serve_uvicorn_import_error(tmp_path, monkeypatch):
    data_dir = str(tmp_path / "data")
    monkeypatch.setitem(os.environ, "COGCORE_SERVICE_DATA_DIR", data_dir)
    with patch.dict("sys.modules", {"uvicorn": None}):
        rc = serve(data_dir=data_dir)
    assert rc == 1


# ============================================================
# main() CLI 入口
# ============================================================


def test_main_cli_passthrough(tmp_path):
    data_dir = str(tmp_path / "data")
    with patch("cogcore.serve._setup_signal_handlers"):
        with patch("uvicorn.run") as mock_uvicorn:
            rc = main(["--port", "7777", "--data-dir", data_dir])
    assert rc == 0
    call_kwargs = mock_uvicorn.call_args.kwargs
    assert call_kwargs["port"] == 7777


# ============================================================
# 信号处理
# ============================================================


def test_signal_handler_calls_service_stop():
    from cogcore.serve import _setup_signal_handlers
    mock_svc = MagicMock()
    with patch("app.deps.get_service", return_value=mock_svc):
        with patch("signal.signal") as mock_signal:
            _setup_signal_handlers()
    # 至少注册了 SIGINT
    calls = [c for c in mock_signal.call_args_list if c.args[0] == 2]  # signal.SIGINT = 2
    assert len(calls) >= 1
