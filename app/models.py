import enum
from datetime import date as date_type, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Note denominations counted at the end of the day. Mirrors the denominations the
# client already counts on their Excel sheet, plus the 2 rupee coin.
CASH_DENOMINATIONS = (2000, 500, 200, 100, 50, 20, 10, 5, 2, 1)


class UserRole(str, enum.Enum):
    staff = "staff"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CarEntry(Base):
    __tablename__ = "car_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    car_model: Mapped[str] = mapped_column(String(120))
    reg_no: Mapped[str] = mapped_column(String(32), index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    service_type: Mapped[str] = mapped_column(String(200))
    amount_paid: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    amount_pending: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    imported_day_id: Mapped[int | None] = mapped_column(
        ForeignKey("imported_days.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    # What the customer has actually paid. Drives the Payment/Balance box on the
    # printed invoice, so it is a real figure rather than a fixed "Received".
    amount_received: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[User | None] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.id"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    invoice: Mapped[Invoice] = relationship(back_populates="items")
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(default=1)
    # The line total, not a unit price — matches the "Price" column on the
    # client's invoice template.
    amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[User | None] = relationship()
    imported_day_id: Mapped[int | None] = mapped_column(
        ForeignKey("imported_days.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    """One upload of the client's monthly workbook."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column()
    month: Mapped[int] = mapped_column()
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    days_created: Mapped[int] = mapped_column(default=0)
    days_updated: Mapped[int] = mapped_column(default=0)
    days_unchanged: Mapped[int] = mapped_column(default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[User | None] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportedDay(Base):
    """A single day that came in from a workbook, and what it hashed to.

    Rows imported for this day point back here with `ON DELETE CASCADE`, so
    re-importing a day that changed is just: delete this row, insert afresh.
    Hand-entered rows have a null reference and are never touched.
    """

    __tablename__ = "imported_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, unique=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DayClosing(Base):
    """End-of-day cash and bank reconciliation — one row per day.

    Replaces the cash block on the client's daily Excel sheet. The physical note
    count is stored in `denominations` as {"500": 12, ...}; everything derived from
    it (counted cash, expected cash, difference, closing balance) is computed in the
    schema rather than stored, so the numbers can never drift out of sync.
    """

    __tablename__ = "day_closings"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, unique=True, index=True)
    opening_cash: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cash_collected: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cash_expenses: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cash_to_partner: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    denominations: Mapped[dict] = mapped_column(JSON, default=dict)
    opening_bank: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    closing_bank: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[User | None] = relationship()
    imported_day_id: Mapped[int | None] = mapped_column(
        ForeignKey("imported_days.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PucEntry(Base):
    __tablename__ = "puc_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    collection_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[User | None] = relationship()
    imported_day_id: Mapped[int | None] = mapped_column(
        ForeignKey("imported_days.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
