"""Shared JWT/API-key validation, with no cross-service database access."""
import os
import secrets
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError

from shared.config import PROJECT_ROOT

bearer = HTTPBearer(auto_error=False)
internal_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: int
    token: str


def require_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    error = HTTPException(401, "Token không hợp lệ hoặc hết hạn", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise error
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")
    try:
        claims = jwt.decode(credentials.credentials, secret, algorithms=["HS256"],
            audience="ibanking", issuer="account-service",
            options={"require": ["sub", "iat", "exp", "iss", "aud"]})
        user_id = int(claims["sub"])
        if not 0 < user_id <= 9223372036854775807:
            raise ValueError("Invalid subject")
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise error from None
    return Principal(user_id, credentials.credentials)


def require_internal_key(value: str | None = Security(internal_header)):
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if len(expected) < 32:
        raise RuntimeError("INTERNAL_API_KEY must contain at least 32 characters")
    if value is None or not secrets.compare_digest(value.encode(), expected.encode()):
        raise HTTPException(401, "Khóa API nội bộ không hợp lệ")
