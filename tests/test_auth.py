"""M5.2 JWT 测试。"""
from __future__ import annotations

import time
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException

from app.auth.jwt import JWTAuth, get_current_user, require_auth


# ============================================================
# 签发
# ============================================================


def test_create_token_returns_string():
    token = JWTAuth.create_token("user_123")
    assert isinstance(token, str)
    assert len(token) > 20


def test_create_token_contains_payload():
    token = JWTAuth.create_token("user_123", expires_hours=1)
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"], options={"verify_signature": False})
    assert payload["sub"] == "user_123"
    assert "exp" in payload
    assert "iat" in payload


# ============================================================
# 校验
# ============================================================


def test_verify_valid_token():
    with patch("app.auth.jwt._get_secret", return_value="test-secret"):
        token = jwt.encode({"sub": "u1", "exp": int(time.time()) + 3600}, "test-secret", algorithm="HS256")
        payload = JWTAuth.verify_token(token)
    assert payload["sub"] == "u1"


def test_verify_expired_token():
    with patch("app.auth.jwt._get_secret", return_value="test-secret"):
        token = jwt.encode({"sub": "u1", "exp": int(time.time()) - 10}, "test-secret", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            JWTAuth.verify_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_verify_invalid_token():
    with patch("app.auth.jwt._get_secret", return_value="test-secret"):
        with pytest.raises(HTTPException) as exc_info:
            JWTAuth.verify_token("not.a.token")
    assert exc_info.value.status_code == 401


# ============================================================
# FastAPI 依赖
# ============================================================


def test_get_current_user_none():
    assert get_current_user(None) is None


def test_require_auth_none():
    with pytest.raises(HTTPException) as exc_info:
        require_auth(None)
    assert exc_info.value.status_code == 401
    assert "required" in exc_info.value.detail.lower()


def test_health_no_auth_needed(client):
    """health 端点无需 JWT。"""
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
