from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import CarEntry, UserRole
from app.schemas import CarEntryCreate, CarEntryOut, CarEntryPage, CarEntryUpdate

router = APIRouter(
    prefix="/api/car-entries",
    tags=["car-entries"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


@router.get("", response_model=CarEntryPage)
def list_car_entries(
    q: str | None = None,
    start: date_type | None = Query(None, description="Only entries on or after this date"),
    end: date_type | None = Query(None, description="Only entries on or before this date"),
    limit: int = Query(50, ge=1, le=200, description="How many entries to return"),
    offset: int = Query(0, ge=0, description="How many to skip"),
    db: Session = Depends(get_db),
):
    """One page of entries, newest first, optionally narrowed by search and date range.

    Both ends of the range are inclusive, and either may be given on its own.
    The list is deliberately paged: the register holds years of history, and
    returning it whole would send megabytes and lock up the browser rendering it.
    """
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="The 'from' date is after the 'to' date")

    query = db.query(CarEntry)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(CarEntry.car_model.ilike(like), CarEntry.reg_no.ilike(like), CarEntry.phone.ilike(like))
        )
    if start:
        query = query.filter(CarEntry.date >= start)
    if end:
        query = query.filter(CarEntry.date <= end)

    total = query.count()
    # Ordering by (date, id) rather than date alone keeps paging stable — with
    # ~40 entries sharing a date, an unordered tiebreak could repeat or skip rows
    # between one page and the next.
    items = (
        query.order_by(CarEntry.date.desc(), CarEntry.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return CarEntryPage(items=items, total=total, has_more=offset + len(items) < total)


@router.post("", response_model=CarEntryOut, status_code=201)
def create_car_entry(payload: CarEntryCreate, db: Session = Depends(get_db)):
    entry = CarEntry(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=CarEntryOut)
def get_car_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(CarEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Car entry not found")
    return entry


@router.put("/{entry_id}", response_model=CarEntryOut)
def update_car_entry(entry_id: int, payload: CarEntryUpdate, db: Session = Depends(get_db)):
    entry = db.get(CarEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Car entry not found")
    for field, value in payload.model_dump().items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_car_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(CarEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Car entry not found")
    db.delete(entry)
    db.commit()
