from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Invoice, InvoiceItem, User, UserRole
from app.schemas import InvoiceCreate, InvoiceOut, InvoicePage, InvoiceUpdate

router = APIRouter(
    prefix="/api/invoices",
    tags=["invoices"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


def _to_item(item) -> InvoiceItem:
    return InvoiceItem(
        description=item.description, quantity=item.quantity, amount=item.amount
    )


def _get_invoice_or_404(invoice_id: int, db: Session) -> Invoice:
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("", response_model=InvoicePage)
def list_invoices(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """One page of invoices, newest first, each with its line items."""
    total = db.query(Invoice).count()
    items = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .order_by(Invoice.date.desc(), Invoice.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return InvoicePage(items=items, total=total, has_more=offset + len(items) < total)


@router.post("", response_model=InvoiceOut, status_code=201)
def create_invoice(
    payload: InvoiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    invoice = Invoice(
        date=payload.date,
        customer_name=payload.customer_name,
        amount_received=payload.amount_received,
        created_by_id=user.id,
    )
    invoice.items = [_to_item(item) for item in payload.items]
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return _get_invoice_or_404(invoice.id, db)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return _get_invoice_or_404(invoice_id, db)


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(invoice_id, db)
    invoice.date = payload.date
    invoice.customer_name = payload.customer_name
    invoice.amount_received = payload.amount_received
    invoice.items = [_to_item(item) for item in payload.items]
    db.commit()
    db.refresh(invoice)
    return _get_invoice_or_404(invoice.id, db)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(invoice_id, db)
    db.delete(invoice)
    db.commit()
