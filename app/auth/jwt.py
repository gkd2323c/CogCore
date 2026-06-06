"""M5.2 JWT 签发/校验。

密钥从 config.toml [auth] secret 读取，缺省随机生成 + 警告。
算法 HS256，依赖 PyJWT（轻量，不引入 python-jose）。
"""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any

import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# 全局缓存（进程内单例）
_SECRET: str | None = None


def _get_secret() -> str:
    """读取或生成 JWT 密钥。"""
    global _SECRET
    if _SECRET is not None:
        return _SECRET

    try:
        from cogcore.config import load_config
        cfg = load_config()
        secret = getattr(cfg, "auth", {}).get("secret", "")
    except Exception:
        secret = ""

    if not secret:
        secret = secrets.token_urlsafe(32)
        logger.warning(
            "JWT secret not configured in config.toml [auth] secret; "
            f"using ephemeral random key (restart invalidates tokens): {secret[:8]}..."
        )

    _SECRET = secret
    return secret


ALGORITHM = "HS256"


class JWTAuth:
    """JWT 签发/校验器。"""

    @staticmethod
    def create_token(user_id: str, expires_hours: int = 24) -> str:
        """签发 JWT access token。"""
        payload = {
            "sub": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_hours * 3600,
        }
        return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> dict[str, Any]:
        """校验 token，返回 payload；失败抛 HTTPException 401。"""
        try:
            return jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")


# FastAPI 依赖
security = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = None) -> dict[str, Any] | None:
    """FastAPI Depends 用：从 Authorization header 提取并校验 JWT。

    返回 payload dict 或 None（当 auto_error=False 且无 token 时）。
    路由层自行判断：None → 401。
    """
    if credentials is None:
        return None
    return JWTAuth.verify_token(credentials.credentials)


def require_auth(credentials: HTTPAuthorizationCredentials | None = None) -> dict[str, Any]:
    """强制认证版：无 token 或无效时直接抛 401。"""
    user = get_current_user(credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
