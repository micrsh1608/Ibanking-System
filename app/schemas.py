from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: str
    phone: str | None


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