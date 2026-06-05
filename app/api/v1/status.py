"""GET /v1/status — 服务状态端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_service
from cogcore.service import CogCoreService

router = APIRouter(prefix="/v1", tags=["status"])


@router.get("/status")
def status(svc: CogCoreService = Depends(get_service)) -> dict:
    """返回当前服务状态。"""
    return svc.get_status()


@router.get("/health")
def health() -> dict:
    """轻量级健康检查（不依赖 service）。"""
    return {"status": "ok"}
