from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvoiceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    semester: str
    amount_due: Decimal
    status: str
    version: int


class TuitionView(BaseModel):
    mssv: str
    full_name: str
    total_unpaid: Decimal
    invoices: list[InvoiceView]


class ReservationSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    invoice_id: int = Field(gt=0)
    version: int = Field(gt=0)


class ReserveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payment_id: UUID
    mssv: str = Field(min_length=1, max_length=24)
    items: list[ReservationSelection] = Field(min_length=1, max_length=100)
    expected_total: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    require_all_unpaid: bool = False

    @model_validator(mode='after')
    def unique_items(self):
        if len({item.invoice_id for item in self.items}) != len(self.items):
            raise ValueError('invoice_id không được trùng')
        return self


class ReservationView(BaseModel):
    payment_id: str
    status: str
    mssv: str | None
    total_amount: Decimal
    invoice_ids: list[int]
