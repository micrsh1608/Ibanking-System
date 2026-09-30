from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TuitionResponse(BaseModel):
    mssv: str
    full_name: str
    email: str
    amount: Decimal
    status: str
    paid_at: datetime | None = None
    paid_transaction_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MarkPaidRequest(BaseModel):
    transaction_id: str
