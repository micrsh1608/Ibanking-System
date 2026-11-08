from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_serializer, model_validator


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    mssv: str = Field(min_length=1, max_length=24)
    selection_mode: Literal['ALL_UNPAID'] = 'ALL_UNPAID'
    terms_accepted: StrictBool

    @model_validator(mode='after')
    def selection(self):
        if self.terms_accepted is not True:
            raise ValueError('Cần đồng ý điều khoản thanh toán trước khi xác nhận giao dịch')
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
    email_delivery: Literal['smtp', 'not_configured'] = 'not_configured'

    @field_serializer('expires_at')
    def utc_dates(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat()


class PaymentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    payment_id: str
    transaction_code: str
    payer_user_id: int
    account_id: int
    payer_email: str
    email_delivery: Literal['smtp', 'not_configured'] = 'not_configured'
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
    terms_version: str | None
    terms_accepted_at: datetime | None

    @field_serializer('created_at', 'updated_at', 'completed_at', 'terms_accepted_at')
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


