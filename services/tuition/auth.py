"""Validate the existing Account Service's JWT, without querying its database."""
import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError

bearer = HTTPBearer(auto_error=False)


def require_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail='Thiếu Bearer token')
    secret = os.getenv('JWT_SECRET_KEY', '')
    if len(secret) < 32:
        raise RuntimeError('JWT_SECRET_KEY phải trùng khóa Account Service, tối thiểu 32 ký tự')
    try:
        claims = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=['HS256'],
            audience='ibanking',
            issuer='account-service',
            options={'require': ['sub', 'iat', 'exp', 'iss', 'aud']},
        )
        user_id = int(claims['sub'])
        if user_id <= 0:
            raise ValueError('Invalid user id')
        return user_id
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=401, detail='Token không hợp lệ hoặc hết hạn') from None
