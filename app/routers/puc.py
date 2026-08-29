from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import PucEntry, User, UserRole
from app.schemas import PucEntryCreate, PucEntryOut, PucEntryUpdate

router = APIRouter(
    prefix="/api/puc",
    tags=["puc"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


@router.get("", response_model=list[PucEntryOut])
def list_puc_entries(db: Session = Depends(get_db)):
    return db.query(PucEntry).order_by(PucEntry.date.desc(), PucEntry.id.desc()).all()


@router.post("", response_model=PucEntryOut, status_code=201)
def create_puc_entry(
    payload: PucEntryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    entry = PucEntry(**payload.model_dump(), created_by_id=user.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=PucEntryOut)
def get_puc_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(PucEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="PUC entry not found")
    return entry


@router.put("/{entry_id}", response_model=PucEntryOut)
def update_puc_entry(entry_id: int, payload: PucEntryUpdate, db: Session = Depends(get_db)):
    entry = db.get(PucEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="PUC entry not found")
    for field, value in payload.model_dump().items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_puc_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(PucEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="PUC entry not found")
    db.delete(entry)
    db.commit()
