from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User
from app.security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    with SessionLocal() as db:
        yield db


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    auth_error = HTTPException(
        status_code=401,
        detail="Token không hợp lệ hoặc đã hết hạn",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise auth_error

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])

        if user_id <= 0 or user_id > 9223372036854775807:
            raise ValueError("ID không hợp lệ")

    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise auth_error from None

    user = db.get(User, user_id)

    if user is None:
        raise auth_error

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Người dùng đã bị vô hiệu hóa",
        )

    return user