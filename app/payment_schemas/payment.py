from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    payer_id: int = Field(gt=0)
    student_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, decimal_places=2)

class PaymentResponse(BaseModel):
    id: int
    transaction_code: str
    payer_id: int
    student_id: int
    amount: Decimal
    status: str

    model_config = {
        "from_attributes": True
    }
    
class PaymentValidationRequest(BaseModel):
    payer_id: int = Field(gt=0)
    student_id: int = Field(gt=0)

class PaymentValidationResponse(BaseModel):
    payer_id: int
    student_id: int
    balance: Decimal
    amount_due: Decimal
    sufficient_balance: bool
    tuition_status: str
    message: str
    
class OTPVerifyRequest(BaseModel):
    otp: str = Field(min_length=6, max_length=6)

class OTPVerifyResponse(BaseModel):
    transaction_code: str
    status: str
    message: str
    
class PaymentProcessResponse(BaseModel):
    transaction_code: str
    status: str
    payer_id: int
    student_id: int
    amount: Decimal
    remaining_balance: Decimal
    message: str