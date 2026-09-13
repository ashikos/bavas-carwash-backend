from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Expense, User, UserRole
from app.schemas import ExpenseCreate, ExpenseOut, ExpensePage, ExpenseUpdate

router = APIRouter(
    prefix="/api/expenses",
    tags=["expenses"],
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)


@router.get("", response_model=ExpensePage)
def list_expenses(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """One page of expenses, newest first."""
    query = db.query(Expense)
    total = query.count()
    items = (
        query.order_by(Expense.date.desc(), Expense.id.desc()).offset(offset).limit(limit).all()
    )
    return ExpensePage(items=items, total=total, has_more=offset + len(items) < total)


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(
    payload: ExpenseCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    expense = Expense(**payload.model_dump(), created_by_id=user.id)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    for field, value in payload.model_dump().items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
