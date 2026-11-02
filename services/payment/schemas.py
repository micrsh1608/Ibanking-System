from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    mssv: str = Field(min_length=1, max_length=24)
    selection_mode: Literal['SELECTED', 'ALL_UNPAID']
    invoice_ids: list[int] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def selection(self):
        if self.selection_mode == 'ALL_UNPAID' and self.invoice_ids:
            raise ValueError('ALL_UNPAID không nhận invoice_ids')
        if self.selection_mode == 'SELECTED' and not self.invoice_ids:
            raise ValueError('Chọn ít nhất một hóa đơn')
        if any(value <= 0 or value > 2147483647 for value in self.invoice_ids):
            raise ValueError('invoice_id không hợp lệ')
        if len(set(self.invoice_ids)) != len(self.invoice_ids):
            raise ValueError('invoice_ids không được trùng')
        self.invoice_ids.sort()
        return self


class PaymentItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    invoice_id: int
    invoice_version: int
    semester: str
    amount: Decimal


class OTPChallengeView(BaseModel):
    challenge_id: str
    expires_at: datetime
    resend_after_seconds: int = 60
    demo_mode: bool = False
    delivery_address: str

    @field_serializer('expires_at')
    def utc_dates(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat()


class PaymentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    payment_id: str
    transaction_code: str
    payer_user_id: int
    account_id: int
    mssv: str
    student_name: str
    selection_mode: str
    total_amount: Decimal
    status: Literal['PENDING_OTP', 'OTP_VERIFIED', 'PROCESSING', 'PENDING_RECONCILIATION', 'SUCCEEDED', 'FAILED', 'REFUNDED']
    phase: Literal['RESERVE', 'DEBIT', 'FINALIZE', 'CANCEL', 'DONE']
    items: list[PaymentItemView]
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    receipt_status: Literal['PENDING', 'SENT'] | None
    active_challenge: OTPChallengeView | None

    @field_serializer('created_at', 'updated_at', 'completed_at')
    def utc_dates(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class OTPVerifyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    challenge_id: UUID
    otp: str = Field(pattern=r'^\d{6}$')


class PaymentPage(BaseModel):
    items: list[PaymentView]
    next_cursor: str | None


class OTPVerifiedView(BaseModel):
    payment_id: str
    status: Literal['OTP_VERIFIED']


