from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, car_entries, customers, expenses, invoices, puc

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


@app.get("/api/health")
def health():
    return {"status": "ok"}
