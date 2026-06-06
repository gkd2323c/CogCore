"""M5.1 单进程部署 CLI 入口。

用法:
    python -m cogcore serve
    python -m cogcore serve --port 8080 --host 0.0.0.0
    python -m cogcore serve --reload
    python -m cogcore serve --data-dir ~/.cogcore
    cogcore serve  # pip install 后
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cogcore serve", description="CogCore HTTP/WebSocket 服务")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="端口 (默认 8000)")
    parser.add_argument("--reload", action="store_true", help="开发热重载")
    parser.add_argument("--data-dir", default="cogcore_data", help="数据目录 (默认 cogcore_data)")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数 (默认 1)")
    return parser


def _ensure_data_dir(data_dir: str) -> str:
    """解析并创建数据目录。"""
    path = Path(data_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    data_dir: str = "cogcore_data",
    workers: int = 1,
) -> int:
    """启动 CogCore FastAPI 服务。

    Returns:
        exit code (0 = success, 1 = error)
    """
    _setup_logging()

    # 确保数据目录存在
    resolved_dir = _ensure_data_dir(data_dir)
    os.environ["COGCORE_SERVICE_DATA_DIR"] = resolved_dir

    # 启动日志
    logger.info(f"CogCore M5.1 serve starting")
    logger.info(f"  version: 0.5.0")
    logger.info(f"  data_dir: {resolved_dir}")
    logger.info(f"  bind: {host}:{port}")
    logger.info(f"  reload: {reload}")
    logger.info(f"  workers: {workers}")

    try:
        import uvicorn
    except ImportError as e:
        logger.error(f"uvicorn not installed: {e}")
        return 1

    # 优雅关闭信号处理
    _setup_signal_handlers()

    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=reload,
            workers=workers if not reload else 1,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Serve failed: {e}")
        return 1

    return 0


def _setup_signal_handlers() -> None:
    """注册 SIGINT/SIGTERM 处理器，尝试优雅关闭 service。"""
    def _handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, shutting down...")
        try:
            from app.deps import get_service
            svc = get_service()
            if hasattr(svc, "stop"):
                svc.stop()
                logger.info("Service stopped.")
        except Exception as e:
            logger.warning(f"Error stopping service: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return serve(
        host=args.host,
        port=args.port,
        reload=args.reload,
        data_dir=args.data_dir,
        workers=args.workers,
    )


if __name__ == "__main__":
    sys.exit(main())
