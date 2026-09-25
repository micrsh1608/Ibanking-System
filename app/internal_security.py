import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]

if (
    INTERNAL_API_KEY == "DAN_KHOA_VUA_TAO_VAO_DAY"
    or len(INTERNAL_API_KEY) < 32
):
    raise ValueError("Hãy tạo INTERNAL_API_KEY hợp lệ trong .env")


internal_key_header = APIKeyHeader(
    name="X-Internal-Key",
    scheme_name="InternalAPIKey",
    auto_error=False,
)


def require_internal_key(
    api_key: str | None = Security(internal_key_header),
):
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Thiếu khóa API nội bộ",
        )

    valid = secrets.compare_digest(
        api_key.encode("utf-8"),
        INTERNAL_API_KEY.encode("utf-8"),
    )

    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Khóa API nội bộ không hợp lệ",
        )