"""Password hashing and JWT issue/verify.

Two roles per project.md section 4: health_worker, supervisor. No self-signup
route -- users are seeded, since this is a single-clinic deployment, not a
public service (project.md section 15, out of scope).
"""

import datetime as dt
import os

from jose import JWTError, jwt
from passlib.context import CryptContext

ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _secret() -> str:
    s = os.environ.get("JWT_SECRET")
    if not s:
        raise RuntimeError(
            "JWT_SECRET is not set. Copy .env.example to .env and generate one: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    return s


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd.verify(password, password_hash)


def create_token(user_id: int, username: str, role: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


class InvalidToken(Exception):
    pass


def decode_token(token: str) -> dict:
    """Raises InvalidToken for anything wrong with it -- expired, malformed,
    wrong signature -- so callers have exactly one exception to handle rather
    than needing to know jose's exception hierarchy."""
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError as e:
        raise InvalidToken(str(e)) from e
