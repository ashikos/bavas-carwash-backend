import hashlib
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.excel_import import ExcelImportError, ParsedDay, parse_workbook
from app.models import (
    CarEntry,
    DayClosing,
    Expense,
    ImportBatch,
    ImportedDay,
    PucEntry,
    User,
    UserRole,
)
from app.schemas import ImportBatchOut, ImportResult

router = APIRouter(
    prefix="/api/imports",
    tags=["imports"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_SUFFIXES = (".xlsx", ".xlsm")


@router.get("", response_model=list[ImportBatchOut])
def list_imports(db: Session = Depends(get_db)):
    return db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()


def _write_day(db: Session, day: ParsedDay, imported_day: ImportedDay) -> dict[str, int]:
    """Insert one parsed day's rows, all linked to `imported_day`."""
    written = {"car_entries": 0, "expenses": 0, "puc": 0, "closings": 0}

    for entry in day.car_entries:
        db.add(
            CarEntry(
                date=day.date,
                car_model=entry["car_model"][:120],
                reg_no=entry["reg_no"][:32],
                phone=entry["phone"][:20],
                service_type=entry["service_type"][:200],
                amount_paid=entry["amount_paid"],
                amount_pending=entry["amount_pending"],
                imported_day_id=imported_day.id,
            )
        )
        written["car_entries"] += 1

    for expense in day.expenses:
        db.add(
            Expense(
                date=day.date,
                description=expense["description"],
                amount=expense["amount"],
                imported_day_id=imported_day.id,
            )
        )
        written["expenses"] += 1

    if day.puc is not None:
        db.add(
            PucEntry(
                date=day.date,
                collection_amount=day.puc["collection_amount"],
                discount=day.puc["discount"],
                imported_day_id=imported_day.id,
            )
        )
        written["puc"] += 1

    if day.day_closing is not None:
        db.add(
            DayClosing(
                date=day.date,
                imported_day_id=imported_day.id,
                **day.day_closing,
            )
        )
        written["closings"] += 1

    return written


@router.post("", response_model=ImportResult)
async def import_workbook(
    file: UploadFile = File(...),
    year: int = Form(...),
    month: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a monthly workbook, writing only the days that are new or changed.

    Safe to run repeatedly: each day is fingerprinted, so uploading the same month
    again after filling in more days touches only the days that actually differ.
    """
    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Month must be between 1 and 12")
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=422, detail="That year doesn't look right")
    if not (file.filename or "").lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(status_code=422, detail="Please upload an .xlsx or .xlsm file")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="That file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 15MB")

    file_hash = hashlib.sha256(content).hexdigest()

    try:
        days = parse_workbook(io.BytesIO(content), year, month)
    except ExcelImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    notes: list[str] = []
    previous = (
        db.query(ImportBatch)
        .filter(ImportBatch.file_hash == file_hash)
        .order_by(ImportBatch.created_at.desc())
        .first()
    )
    if previous is not None:
        notes.append(
            "This is the same file that was uploaded on "
            f"{previous.created_at.strftime('%-d %b %Y')} — nothing will have changed."
        )

    if not days:
        raise HTTPException(
            status_code=422,
            detail=f"No filled-in days found for {datetime(year, month, 1):%B %Y} in that file",
        )

    batch = ImportBatch(
        year=year,
        month=month,
        filename=(file.filename or "workbook.xlsx")[:255],
        file_hash=file_hash,
        created_by_id=user.id,
    )
    db.add(batch)
    db.flush()

    totals = {"car_entries": 0, "expenses": 0, "puc": 0, "closings": 0}
    created = updated = unchanged = 0

    existing_by_date = {
        row.date: row
        for row in db.query(ImportedDay).filter(
            ImportedDay.date.in_([d.date for d in days])
        )
    }
    # Day closings entered by hand must not be clobbered by an import.
    manual_closings = {
        row.date
        for row in db.query(DayClosing).filter(
            DayClosing.date.in_([d.date for d in days]),
            DayClosing.imported_day_id.is_(None),
        )
    }

    for day in days:
        fingerprint = day.fingerprint()
        existing = existing_by_date.get(day.date)

        if existing is not None and existing.fingerprint == fingerprint:
            unchanged += 1
            continue

        if existing is not None:
            # Deleting cascades this day's previously imported rows away.
            db.delete(existing)
            db.flush()
            updated += 1
        else:
            created += 1

        if day.date in manual_closings and day.day_closing is not None:
            day.day_closing = None
            notes.append(
                f"{day.date:%-d %b}: kept the end-of-day figures entered in the app "
                "and ignored the ones in the sheet."
            )

        imported_day = ImportedDay(
            date=day.date, fingerprint=fingerprint, import_batch_id=batch.id
        )
        db.add(imported_day)
        db.flush()

        for key, count in _write_day(db, day, imported_day).items():
            totals[key] += count

    batch.days_created = created
    batch.days_updated = updated
    batch.days_unchanged = unchanged
    db.commit()

    skipped = sum(d.skipped_credit_rows for d in days)
    if skipped:
        notes.append(
            f"Skipped {skipped} credit-repayment row(s) — the app doesn't track repayments yet."
        )

    return ImportResult(
        batch_id=batch.id,
        year=year,
        month=month,
        filename=batch.filename,
        days_created=created,
        days_updated=updated,
        days_unchanged=unchanged,
        car_entries_written=totals["car_entries"],
        expenses_written=totals["expenses"],
        puc_entries_written=totals["puc"],
        day_closings_written=totals["closings"],
        skipped_credit_rows=skipped,
        notes=notes,
    )
