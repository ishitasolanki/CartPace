"""POST /api/auth/login, GET /api/auth/me."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth import create_token, verify_password
from backend.db import get_db
from backend.deps import current_user
from backend.models import User
from backend.schemas import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    # Same error for "no such user" and "wrong password" -- distinguishing them
    # tells an attacker which usernames exist.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                           "invalid username or password")
    token = create_token(user.id, user.username, user.role)
    return TokenResponse(access_token=token, role=user.role)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(current_user)):
    return MeResponse(id=user.id, username=user.username, role=user.role)
