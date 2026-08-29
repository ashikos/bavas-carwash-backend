from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import CarEntry, UserRole
from app.schemas import CarEntryCreate, CarEntryOut, CarEntryUpdate

router = APIRouter(
    prefix="/api/car-entries",
    tags=["car-entries"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


@router.get("", response_model=list[CarEntryOut])
def list_car_entries(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(CarEntry)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(CarEntry.car_model.ilike(like), CarEntry.reg_no.ilike(like), CarEntry.phone.ilike(like))
        )
    return query.order_by(CarEntry.date.desc(), CarEntry.id.desc()).all()


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
