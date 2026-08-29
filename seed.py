"""Create initial staff and admin users. Run once after migrations."""

from app.auth import hash_password
from app.database import SessionLocal
from app.models import User, UserRole

SEED_USERS = [
    {"username": "staff1", "password": "staff123", "role": UserRole.staff},
    {"username": "admin1", "password": "admin123", "role": UserRole.admin},
]


def main():
    db = SessionLocal()
    try:
        for u in SEED_USERS:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if existing:
                print(f"skip: {u['username']} already exists")
                continue
            user = User(username=u["username"], password_hash=hash_password(u["password"]), role=u["role"])
            db.add(user)
            print(f"created: {u['username']} ({u['role'].value}) / password: {u['password']}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
