from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.routers import (
    auth,
    car_entries,
    customers,
    dashboard,
    day_closings,
    expenses,
    imports,
    invoices,
    puc,
)

app = FastAPI(title="Bavas Group Car Wash API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(car_entries.router)
app.include_router(invoices.router)
app.include_router(expenses.router)
app.include_router(puc.router)
app.include_router(day_closings.router)
app.include_router(imports.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Liveness check, and the target of the keep-alive ping.

    It deliberately runs a query rather than just returning a constant: the ping
    needs to keep the Neon compute awake as well as the Render web service, and
    only a real round trip to the database does that.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503, content={"status": "degraded", "database": "unreachable"}
        )
    return {"status": "ok", "database": "ok"}
