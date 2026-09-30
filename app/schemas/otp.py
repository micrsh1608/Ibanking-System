from pydantic import BaseModel, EmailStr


class SendOTPRequest(BaseModel):
    transaction_id: str
    mssv: str
    email: EmailStr


class SendOTPResponse(BaseModel):
    transaction_id: str
    message: str
    expires_in: int


class VerifyOTPRequest(BaseModel):
    transaction_id: str
    otp: str


class VerifyOTPResponse(BaseModel):
    transaction_id: str
    verified: bool
    message: str
