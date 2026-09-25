import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from pwdlib import PasswordHash


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SECRET_KEY = os.environ["JWT_SECRET_KEY"]

if (
    SECRET_KEY == "DAN_CHUOI_VUA_TAO_VAO_DAY"
    or len(SECRET_KEY) < 32
):
    raise ValueError("Hãy tạo và điền JWT_SECRET_KEY vào file .env")

ALGORITHM = "HS256"
ISSUER = "account-service"
AUDIENCE = "ibanking"

TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

password_hasher = PasswordHash.recommended()

# Dùng để vẫn thực hiện kiểm tra hash khi username không tồn tại.
DUMMY_HASH = password_hasher.hash("dummy-password-for-timing")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
        "iss": ISSUER,
        "aud": AUDIENCE,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={
            "require": ["sub", "iat", "exp", "iss", "aud"]
        },
    )