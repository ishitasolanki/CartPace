"""Shared FastAPI dependencies: current_user and require_role.

One shared dependency so no route can be silently unguarded, per
modular-plan.md. A route that needs supervisor access takes
Depends(require_role("supervisor")) rather than writing its own check --
inventing a second way to gate a route is how one gets forgotten.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.auth import InvalidToken, decode_token
from backend.db import get_db
from backend.models import User

_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                           "not authenticated",
                           headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_token(creds.credentials)
    except InvalidToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                           "invalid or expired token",
                           headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


def require_role(role: str):
    def _check(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                               f"requires role '{role}'")
        return user
    return _check


async def current_user_ws(token: str, db: Session) -> User | None:
    """WebSocket auth: no header on a WS handshake in a browser client, so the
    token travels as a query parameter instead. Returns None rather than
    raising, since the caller needs to close the socket with a WS close code,
    not an HTTP status."""
    try:
        payload = decode_token(token)
    except InvalidToken:
        return None
    return db.get(User, int(payload["sub"]))
