from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# `pool_pre_ping` issues a cheap SELECT 1 before handing a pooled connection
# to a request and quietly replaces it if it has died. Without it, the first
# request after the database drops a connection fails with a 500 and only the
# retry succeeds — the app looks broken after any idle spell. Connections do
# die routinely: the laptop suspends, a NAT or firewall reaps an idle socket,
# and in production Neon autosuspends and closes everything it was holding.
#
# `pool_recycle` retires connections after 25 minutes regardless, so none is
# ever old enough for a middlebox to have silently dropped it underneath us.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1500,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
