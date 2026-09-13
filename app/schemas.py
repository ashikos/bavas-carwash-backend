from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.models import CASH_DENOMINATIONS, UserRole


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


class CarEntryPage(BaseModel):
    """One page of entries, plus what the caller needs to ask for the next.

    The register goes back years and runs to tens of thousands of rows, so this
    endpoint never returns the whole table.
    """

    items: list[CarEntryOut]
    total: int
    has_more: bool


# ---- Invoices ----
class InvoiceItemBase(BaseModel):
    description: str
    quantity: int = 1
    amount: Decimal = Decimal("0")


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemOut(InvoiceItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class InvoiceBase(BaseModel):
    date: date
    customer_name: str
    amount_received: Decimal = Decimal("0")


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

    @computed_field
    @property
    def balance(self) -> Decimal:
        return self.total - self.amount_received

    @computed_field
    @property
    def payment_status(self) -> str:
        """Wording for the Payment line on the printed invoice."""
        if self.amount_received <= 0:
            return "Pending"
        return "Received" if self.balance <= 0 else "Part paid"


class InvoicePage(BaseModel):
    items: list[InvoiceOut]
    total: int
    has_more: bool


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


class ExpensePage(BaseModel):
    items: list[ExpenseOut]
    total: int
    has_more: bool


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


class PucEntryPage(BaseModel):
    items: list[PucEntryOut]
    total: int
    has_more: bool


# ---- Day closings (end-of-day cash reconciliation) ----
class DayClosingBase(BaseModel):
    date: date
    opening_cash: Decimal = Decimal("0")
    cash_collected: Decimal = Decimal("0")
    cash_expenses: Decimal = Decimal("0")
    cash_to_partner: Decimal = Decimal("0")
    opening_bank: Decimal = Decimal("0")
    closing_bank: Decimal = Decimal("0")
    denominations: dict[str, int] = {}
    notes: str | None = None

    @field_validator("denominations")
    @classmethod
    def validate_denominations(cls, value: dict[str, int]) -> dict[str, int]:
        unknown = set(value) - {str(d) for d in CASH_DENOMINATIONS}
        if unknown:
            raise ValueError(f"unknown denominations: {', '.join(sorted(unknown))}")
        if any(qty < 0 for qty in value.values()):
            raise ValueError("denomination quantities cannot be negative")
        return value


class DayClosingCreate(DayClosingBase):
    pass


class DayClosingUpdate(DayClosingBase):
    pass


class DayClosingOut(DayClosingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def counted_cash(self) -> Decimal:
        """What the physical note count actually adds up to."""
        return sum((Decimal(d) * qty for d, qty in self.denominations.items()), Decimal("0"))

    @computed_field
    @property
    def expected_cash(self) -> Decimal:
        """What should be in the drawer before anything is handed over."""
        return self.opening_cash + self.cash_collected - self.cash_expenses

    @computed_field
    @property
    def difference(self) -> Decimal:
        """Counted minus expected. Zero means the day balanced."""
        return self.counted_cash - self.expected_cash

    @computed_field
    @property
    def closing_cash(self) -> Decimal:
        """What stays in the box overnight, and so opens tomorrow."""
        return self.counted_cash - self.cash_to_partner


class ImportResult(BaseModel):
    """What one workbook upload actually changed."""

    batch_id: int
    year: int
    month: int
    filename: str
    days_created: int = 0
    days_updated: int = 0
    days_unchanged: int = 0
    car_entries_written: int = 0
    expenses_written: int = 0
    puc_entries_written: int = 0
    day_closings_written: int = 0
    skipped_credit_rows: int = 0
    notes: list[str] = []


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    month: int
    filename: str
    days_created: int
    days_updated: int
    days_unchanged: int
    created_at: datetime


# ---- Admin dashboard ----
class LabelCount(BaseModel):
    label: str
    count: int


class DayCount(BaseModel):
    date: date
    count: int


class MonthCount(BaseModel):
    month: int
    # None means no data has been imported for that month — which a chart must
    # show as absent rather than as a month with zero jobs.
    count: int | None = None


class DashboardSummary(BaseModel):
    year: int
    month: int
    jobs: int
    days_recorded: int
    jobs_per_day: float
    vehicles: int
    unspecified_services: int
    busiest: DayCount | None = None
    quietest: DayCount | None = None
    monthly: list[MonthCount] = []
    daily: list[DayCount] = []
    services: list[LabelCount] = []
    weekday: list[LabelCount] = []
    top_vehicles: list[LabelCount] = []
    accounts: list[LabelCount] = []
    repeat_visits: list[LabelCount] = []
    available_months: list[str] = []
    # True when the viewer may only see some months, so the page can say so
    # instead of claiming the hidden months were never imported.
    restricted: bool = False


class DayClosingSummary(BaseModel):
    """Figures the end-of-day screen prefills from data already recorded."""

    date: date
    car_entries_total: Decimal
    puc_total: Decimal
    expenses_total: Decimal
    suggested_opening_cash: Decimal
    suggested_opening_bank: Decimal
    existing_closing_id: int | None = None
