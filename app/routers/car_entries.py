from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import CarEntry, UserRole
from app.schemas import (
    BulkDeleteRequest,
    BulkDeleteResult,
    CarEntryCreate,
    CarEntryOut,
    CarEntryPage,
    CarEntryUpdate,
)

# A guard against a runaway request, not a limit anyone should hit by hand.
MAX_BULK_DELETE = 500

router = APIRouter(
    prefix="/api/car-entries",
    tags=["car-entries"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


def _filtered(db: Session, q: str | None, start: date_type | None, end: date_type | None):
    """The list's filter, in one place so a delete can never match a different
    set of rows than the list that was on screen."""
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
    return query


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
    query = _filtered(db, q, start, end)
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


# Declared before the "/{entry_id}" routes so "bulk-delete" is never read as an id.
@router.post("/bulk-delete", response_model=BulkDeleteResult)
def bulk_delete_car_entries(payload: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Delete ticked rows, or everything the list's filter matches.

    Deleting by filter exists because the alternative does not work: to remove a
    month the user would have to scroll every one of its rows into the browser
    just to tick them. The filter is the same one the list used, so what is
    deleted is exactly what was on screen.
    """
    if payload.match_filter:
        # Refuse to wipe the whole table from a filter. Clearing everything is a
        # deliberate act, not something a stray click should reach.
        if not (payload.q or payload.start or payload.end):
            raise HTTPException(
                status_code=422,
                detail="Narrow the list with a search or date range before deleting everything in it",
            )

        query = _filtered(db, payload.q, payload.start, payload.end)
        matched = query.count()
        if matched == 0:
            raise HTTPException(status_code=422, detail="Nothing matches that filter")

        # The count the user was shown must still hold. If someone added or
        # removed rows in the meantime, stop rather than delete a different set.
        if payload.expected is not None and payload.expected != matched:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This now matches {matched} entries, not {payload.expected}. "
                    "Refresh the list and try again."
                ),
            )

        deleted = query.delete(synchronize_session=False)
        db.commit()
        return BulkDeleteResult(deleted=deleted, requested=matched)

    if not payload.ids:
        raise HTTPException(status_code=422, detail="No entries were selected")
    if len(payload.ids) > MAX_BULK_DELETE:
        raise HTTPException(
            status_code=422,
            detail=f"Please delete at most {MAX_BULK_DELETE} entries at a time",
        )

    ids = set(payload.ids)
    deleted = (
        db.query(CarEntry).filter(CarEntry.id.in_(ids)).delete(synchronize_session=False)
    )
    db.commit()
    return BulkDeleteResult(deleted=deleted, requested=len(ids))


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
