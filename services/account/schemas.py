from decimal import Decimal
from datetime import datetime, timezone
import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ContactDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: str = Field(min_length=2, max_length=100, pattern=r'^[^\x00-\x1f\x7f]+$')
    email: str = Field(min_length=5, max_length=255, pattern=r'^[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+$')
    phone: str | None = Field(default=None, max_length=20, pattern=r'^[+0-9 ()-]{7,20}$')
    identity_number: str | None = Field(default=None, max_length=20, pattern=r'^[A-Za-z0-9 -]{6,20}$')

    @field_validator('full_name', 'email', 'phone', 'identity_number', mode='before')
    @classmethod
    def trim_contact(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('phone')
    @classmethod
    def phone_digits(cls, value):
        if value is not None and not 7 <= len(re.sub(r'\D', '', value)) <= 15:
            raise ValueError('Số điện thoại phải có từ 7 đến 15 chữ số')
        return value


class ProfileUpdate(ContactDetails):
    current_password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EmailChallengeView(BaseModel):
    challenge_id: str
    expires_at: datetime
    resend_after_seconds: int
    delivery_address: str

    @field_serializer('expires_at')
    def utc_date(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat()


class EmailVerificationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    challenge_id: UUID
    code: str = Field(pattern=r'^[0-9]{6}$')


class EmailResendRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: str
    phone: str | None
    identity_number: str | None
    email_verified: bool
    email_delivery: Literal['smtp', 'not_configured']
    pending_email: str | None
    email_verification: EmailChallengeView | None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_number: str
    balance: Decimal
    status: str


class DebitRequest(BaseModel):
    payment_id: UUID

    account_id: int = Field(
        gt=0, le=9223372036854775807
    )

    payer_user_id: int = Field(
        gt=0, le=9223372036854775807
    )

    amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
    )


class RefundRequest(BaseModel):
    payment_id: UUID


class OperationResponse(BaseModel):
    payment_id: str
    account_id: int
    amount: Decimal
    status: str
