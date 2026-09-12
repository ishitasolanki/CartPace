"""Seed the two demo users. No self-signup route exists (see routes/auth.py),
so this is how accounts get created for a single-clinic deployment.

Run: python -m backend.seed
"""

from backend.auth import hash_password
from backend.db import SessionLocal, init_db
from backend.models import User


def main():
    init_db()
    db = SessionLocal()
    try:
        seeds = [
            ("nurse", "change-me-nurse", "health_worker"),
            ("supervisor", "change-me-supervisor", "supervisor"),
        ]
        for username, password, role in seeds:
            if db.query(User).filter(User.username == username).first():
                continue
            db.add(User(username=username,
                       password_hash=hash_password(password), role=role))
        db.commit()
        print("seeded:", [u for u, _, _ in seeds])
    finally:
        db.close()


if __name__ == "__main__":
    main()
