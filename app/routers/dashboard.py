"""Admin dashboard figures.

Deliberately reports work volume only — job counts, vehicles, service mix — and
no money. The client asked for an operations view, so nothing here exposes
revenue, expenses or cash.
"""

import calendar
from collections import Counter
from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import CarEntry, User, UserRole
from app.schemas import DashboardSummary, DayCount, LabelCount, MonthCount
from app.services import NOT_SPECIFIED, canonical_service

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    # Both roles: the same dashboard is shown in the staff module as well.
    # It carries no money figures, so there is nothing here staff shouldn't see.
    dependencies=[Depends(require_role(UserRole.staff, UserRole.admin))],
)

WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
TOP_N = 8


def _month_bounds(year: int, month: int) -> tuple[date_type, date_type]:
    last = calendar.monthrange(year, month)[1]
    return date_type(year, month, 1), date_type(year, month, last)


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _allowed_months(user: User) -> set[str] | None:
    """Which months this user may look at, or None for no restriction.

    Staff see the current month and the one before it — enough to finish off last
    month's paperwork, without opening up the whole history. Admins see everything.
    Enforced here rather than by hiding buttons, since the period is a query
    parameter anyone could type.
    """
    if user.role == UserRole.admin:
        return None
    today = date_type.today()
    this_month = date_type(today.year, today.month, 1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    return {_month_key(d.year, d.month) for d in (this_month, last_month)}


def _repeat_band(visits: int) -> str:
    if visits == 1:
        return "Once"
    if visits == 2:
        return "Twice"
    if visits <= 4:
        return "3-4 times"
    return "5 or more"


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
):
    """Everything the dashboard draws, in one call.

    Defaults to the most recent month the user may see that has any entries, so
    the page has something to show without the user picking a period first.
    """
    months_present = [
        row[0]
        for row in db.query(func.to_char(CarEntry.date, "YYYY-MM"))
        .distinct()
        .order_by(func.to_char(CarEntry.date, "YYYY-MM").desc())
        .all()
    ]

    allowed = _allowed_months(user)
    if allowed is not None:
        months_present = [m for m in months_present if m in allowed]

    if year is None or month is None:
        today = date_type.today()
        if months_present:
            latest_year, latest_month = months_present[0].split("-")
            year, month = int(latest_year), int(latest_month)
        else:
            year, month = today.year, today.month
    elif allowed is not None and _month_key(year, month) not in allowed:
        raise HTTPException(
            status_code=403,
            detail="You can only view the current month and the one before it.",
        )

    start, end = _month_bounds(year, month)
    in_month = (CarEntry.date >= start, CarEntry.date <= end)

    # ---- Daily counts drive the headline figures and the weekday averages ----
    daily_rows = (
        db.query(CarEntry.date, func.count(CarEntry.id))
        .filter(*in_month)
        .group_by(CarEntry.date)
        .order_by(CarEntry.date)
        .all()
    )
    daily = [DayCount(date=d, count=n) for d, n in daily_rows]
    jobs = sum(d.count for d in daily)
    days_recorded = len(daily)

    busiest = max(daily, key=lambda d: d.count) if daily else None
    quietest = min(daily, key=lambda d: d.count) if daily else None

    # Average per weekday, not total — months hold four of some weekdays and five
    # of others, so totals would make the five-day weekdays look busier.
    by_weekday: dict[int, list[int]] = {}
    for d in daily:
        # Python's weekday() is Monday-based; shift so Sunday leads, as the labels do.
        by_weekday.setdefault((d.date.weekday() + 1) % 7, []).append(d.count)
    weekday = [
        LabelCount(
            label=WEEKDAYS[i],
            count=round(sum(by_weekday[i]) / len(by_weekday[i])) if by_weekday.get(i) else 0,
        )
        for i in range(7)
    ]

    # ---- Service mix, folded onto canonical names ----
    service_rows = (
        db.query(CarEntry.service_type, func.count(CarEntry.id))
        .filter(*in_month)
        .group_by(CarEntry.service_type)
        .all()
    )
    tally: Counter[str] = Counter()
    for raw, n in service_rows:
        tally[canonical_service(raw)] += n
    services = [LabelCount(label=name, count=n) for name, n in tally.most_common()]

    # ---- Vehicles ----
    vehicles = (
        db.query(func.count(func.distinct(CarEntry.reg_no)))
        .filter(*in_month, CarEntry.reg_no != "")
        .scalar()
        or 0
    )
    top_vehicles = [
        LabelCount(label=model, count=n)
        for model, n in db.query(CarEntry.car_model, func.count(CarEntry.id))
        .filter(*in_month, CarEntry.car_model != "")
        .group_by(CarEntry.car_model)
        .order_by(func.count(CarEntry.id).desc(), CarEntry.car_model)
        .limit(TOP_N)
        .all()
    ]

    visit_rows = (
        db.query(func.count(CarEntry.id))
        .filter(*in_month, CarEntry.reg_no != "")
        .group_by(CarEntry.reg_no)
        .all()
    )
    bands: Counter[str] = Counter(_repeat_band(n) for (n,) in visit_rows)
    repeat_visits = [
        LabelCount(label=band, count=bands[band])
        for band in ("Once", "Twice", "3-4 times", "5 or more")
        if bands[band]
    ]

    # Staff type an account name into the mobile column for regulars such as
    # dealerships, so anything containing a letter is an account, not a number.
    accounts = [
        LabelCount(label=name, count=n)
        for name, n in db.query(CarEntry.phone, func.count(CarEntry.id))
        .filter(*in_month, CarEntry.phone.op("~")("[A-Za-z]"))
        .group_by(CarEntry.phone)
        .order_by(func.count(CarEntry.id).desc(), CarEntry.phone)
        .limit(6)
        .all()
    ]

    # ---- Jobs per month across the year ----
    year_rows = dict(
        db.query(extract("month", CarEntry.date), func.count(CarEntry.id))
        .filter(extract("year", CarEntry.date) == year)
        .group_by(extract("month", CarEntry.date))
        .all()
    )
    # Every month's total is shown to everyone, including staff who may only open
    # the detail for recent months. A month with no entries stays None so the chart
    # can draw it as absent rather than as a month with zero jobs.
    monthly = [
        MonthCount(month=m, count=int(year_rows[m]) if m in year_rows else None)
        for m in range(1, 13)
    ]

    return DashboardSummary(
        year=year,
        month=month,
        jobs=jobs,
        days_recorded=days_recorded,
        jobs_per_day=round(jobs / days_recorded, 1) if days_recorded else 0.0,
        vehicles=vehicles,
        unspecified_services=tally.get(NOT_SPECIFIED, 0),
        busiest=busiest,
        quietest=quietest,
        monthly=monthly,
        daily=daily,
        services=services,
        weekday=weekday,
        top_vehicles=top_vehicles,
        accounts=accounts,
        repeat_visits=repeat_visits,
        available_months=months_present,
        restricted=allowed is not None,
    )
