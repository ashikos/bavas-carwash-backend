from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import CarEntry, DayClosing, Expense, PucEntry, User, UserRole
from app.schemas import DayClosingCreate, DayClosingOut, DayClosingSummary, DayClosingUpdate

router = APIRouter(
    prefix="/api/day-closings",
    tags=["day-closings"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


def _total(db: Session, column, model, on: date_type) -> Decimal:
    value = db.query(func.coalesce(func.sum(column), 0)).filter(model.date == on).scalar()
    return Decimal(value or 0)


@router.get("", response_model=list[DayClosingOut])
def list_day_closings(
    db: Session = Depends(get_db),
    start: date_type | None = Query(None, description="Only closings on or after this date"),
    end: date_type | None = Query(None, description="Only closings on or before this date"),
):
    query = db.query(DayClosing)
    if start is not None:
        query = query.filter(DayClosing.date >= start)
    if end is not None:
        query = query.filter(DayClosing.date <= end)
    return query.order_by(DayClosing.date.desc()).all()


@router.get("/summary", response_model=DayClosingSummary)
def day_summary(date: date_type, db: Session = Depends(get_db)):
    """Prefill figures for the end-of-day screen.

    Collections and expenses come from what staff already entered for the day;
    the opening balances come from the previous closing, so the box carries over
    the same way it does on the Excel sheet.
    """
    previous = (
        db.query(DayClosing)
        .filter(DayClosing.date < date)
        .order_by(DayClosing.date.desc())
        .first()
    )
    previous_cash = Decimal("0")
    if previous is not None:
        counted = sum(
            (Decimal(d) * qty for d, qty in (previous.denominations or {}).items()),
            Decimal("0"),
        )
        previous_cash = counted - Decimal(previous.cash_to_partner)

    existing = db.query(DayClosing).filter(DayClosing.date == date).first()

    return DayClosingSummary(
        date=date,
        car_entries_total=_total(db, CarEntry.amount_paid, CarEntry, date),
        puc_total=_total(db, PucEntry.collection_amount, PucEntry, date),
        expenses_total=_total(db, Expense.amount, Expense, date),
        suggested_opening_cash=previous_cash,
        suggested_opening_bank=Decimal(previous.closing_bank) if previous else Decimal("0"),
        existing_closing_id=existing.id if existing else None,
    )


@router.post("", response_model=DayClosingOut, status_code=201)
def create_day_closing(
    payload: DayClosingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.query(DayClosing).filter(DayClosing.date == payload.date).first() is not None:
        raise HTTPException(status_code=409, detail="This day has already been closed")
    closing = DayClosing(**payload.model_dump(), created_by_id=user.id)
    db.add(closing)
    db.commit()
    db.refresh(closing)
    return closing


@router.get("/{closing_id}", response_model=DayClosingOut)
def get_day_closing(closing_id: int, db: Session = Depends(get_db)):
    closing = db.get(DayClosing, closing_id)
    if closing is None:
        raise HTTPException(status_code=404, detail="Day closing not found")
    return closing


@router.put("/{closing_id}", response_model=DayClosingOut)
def update_day_closing(closing_id: int, payload: DayClosingUpdate, db: Session = Depends(get_db)):
    closing = db.get(DayClosing, closing_id)
    if closing is None:
        raise HTTPException(status_code=404, detail="Day closing not found")
    clash = (
        db.query(DayClosing)
        .filter(DayClosing.date == payload.date, DayClosing.id != closing_id)
        .first()
    )
    if clash is not None:
        raise HTTPException(status_code=409, detail="Another closing already exists for that date")
    for field, value in payload.model_dump().items():
        setattr(closing, field, value)
    db.commit()
    db.refresh(closing)
    return closing


@router.delete("/{closing_id}", status_code=204)
def delete_day_closing(closing_id: int, db: Session = Depends(get_db)):
    closing = db.get(DayClosing, closing_id)
    if closing is None:
        raise HTTPException(status_code=404, detail="Day closing not found")
    db.delete(closing)
    db.commit()
