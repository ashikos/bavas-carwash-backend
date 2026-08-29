from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field

from app.models import UserRole


# ---- Auth ----
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    username: str


# ---- Customers ----
class CustomerBase(BaseModel):
    name: str
    phone: str


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ---- Car entries ----
class CarEntryBase(BaseModel):
    date: date
    car_model: str
    reg_no: str
    phone: str
    service_type: str
    amount_paid: Decimal = Decimal("0")
    amount_pending: Decimal = Decimal("0")


class CarEntryCreate(CarEntryBase):
    pass


class CarEntryUpdate(CarEntryBase):
    pass


class CarEntryOut(CarEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ---- Invoices ----
class InvoiceItemBase(BaseModel):
    description: str
    amount: Decimal = Decimal("0")


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemOut(InvoiceItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class InvoiceBase(BaseModel):
    date: date
    customer_name: str


class InvoiceCreate(InvoiceBase):
    items: list[InvoiceItemCreate]


class InvoiceUpdate(InvoiceBase):
    items: list[InvoiceItemCreate]


class InvoiceOut(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    items: list[InvoiceItemOut]
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def total(self) -> Decimal:
        return sum((item.amount for item in self.items), Decimal("0"))


# ---- Expenses ----
class ExpenseBase(BaseModel):
    date: date
    description: str
    amount: Decimal = Decimal("0")


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(ExpenseBase):
    pass


class ExpenseOut(ExpenseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---- PUC entries ----
class PucEntryBase(BaseModel):
    date: date
    collection_amount: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")


class PucEntryCreate(PucEntryBase):
    pass


class PucEntryUpdate(PucEntryBase):
    pass


class PucEntryOut(PucEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
