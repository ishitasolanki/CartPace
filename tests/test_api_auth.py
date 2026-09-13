"""API auth tests: 401 unauthenticated, 403 wrong role, expired token
rejected, body validation (AC10).

Each test gets its own in-memory SQLite database via dependency override, so
tests cannot leak state into each other -- a shared file-backed DB would make
test order matter, which is exactly the kind of flaky failure this avoids.
"""

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

from backend.auth import ALGORITHM, hash_password       # noqa: E402
from backend.db import Base, get_db                     # noqa: E402
from backend.main import app                             # noqa: E402
from backend.models import User                          # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine("sqlite://",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    TestSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    db = TestSession()
    db.add(User(username="nurse", password_hash=hash_password("pw12345"),
               role="health_worker"))
    db.add(User(username="boss", password_hash=hash_password("pw12345"),
               role="supervisor"))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client, username, password):
    r = client.post("/api/auth/login",
                    json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- login -------------------------------------------------------------


def test_login_succeeds_with_correct_credentials(client):
    token = login(client, "nurse", "pw12345")
    assert token


def test_login_rejects_wrong_password(client):
    r = client.post("/api/auth/login",
                    json={"username": "nurse", "password": "wrong"})
    assert r.status_code == 401


def test_login_rejects_unknown_user(client):
    r = client.post("/api/auth/login",
                    json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_login_error_does_not_distinguish_unknown_user_from_wrong_password(client):
    """Same message either way -- a differing one would let an attacker
    enumerate valid usernames."""
    r1 = client.post("/api/auth/login",
                     json={"username": "nobody", "password": "x"})
    r2 = client.post("/api/auth/login",
                     json={"username": "nurse", "password": "wrong"})
    assert r1.json()["detail"] == r2.json()["detail"]


def test_login_rejects_empty_body(client):
    r = client.post("/api/auth/login", json={})
    assert r.status_code == 422


# --- 401 unauthenticated -------------------------------------------------


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_runs_list_requires_auth(client):
    assert client.get("/api/runs").status_code == 401


def test_garbage_token_is_401(client):
    r = client.get("/api/auth/me", headers=auth("not-a-real-token"))
    assert r.status_code == 401


def test_me_succeeds_with_valid_token(client):
    token = login(client, "nurse", "pw12345")
    r = client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["username"] == "nurse"
    assert r.json()["role"] == "health_worker"


# --- 403 wrong role -------------------------------------------------------


def test_health_worker_can_create_run(client):
    """project.md section 4: "Run the clinic day" is a health_worker
    capability. An earlier cut of the API required supervisor for this,
    which contradicted the spec -- fixed once the frontend build made the
    mismatch obvious."""
    token = login(client, "nurse", "pw12345")
    r = client.post("/api/runs",
                    json={"scenario": "calm", "seed": 1, "n_days": 5},
                    headers=auth(token))
    assert r.status_code == 201
    assert r.json()["scenario"] == "calm"


def test_supervisor_can_create_run(client):
    token = login(client, "boss", "pw12345")
    r = client.post("/api/runs",
                    json={"scenario": "calm", "seed": 1, "n_days": 5},
                    headers=auth(token))
    assert r.status_code == 201
    assert r.json()["scenario"] == "calm"


def test_health_worker_can_list_runs(client):
    """Reading is not supervisor-only -- only budget/scenario control is,
    and this cut has no mutable budget/scenario route at all (see
    routes/config.py), so nothing in the current API surface is actually
    supervisor-exclusive."""
    token = login(client, "nurse", "pw12345")
    r = client.get("/api/runs", headers=auth(token))
    assert r.status_code == 200


# --- expired token ---------------------------------------------------------


def test_expired_token_is_401(client):
    token = login(client, "nurse", "pw12345")
    payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[ALGORITHM])
    expired = jwt.encode(
        {**payload, "exp": dt.datetime.now(dt.timezone.utc)
                          - dt.timedelta(minutes=1)},
        os.environ["JWT_SECRET"], algorithm=ALGORITHM)
    r = client.get("/api/auth/me", headers=auth(expired))
    assert r.status_code == 401


def test_token_signed_with_wrong_secret_is_401(client):
    token = login(client, "nurse", "pw12345")
    payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[ALGORITHM])
    forged = jwt.encode(payload, "wrong-secret", algorithm=ALGORITHM)
    r = client.get("/api/auth/me", headers=auth(forged))
    assert r.status_code == 401


# --- body validation (AC10 extends to every endpoint, not only auth) -------


def test_create_run_rejects_unknown_scenario(client):
    token = login(client, "boss", "pw12345")
    r = client.post("/api/runs", json={"scenario": "not_a_scenario", "seed": 1},
                    headers=auth(token))
    assert r.status_code == 422


def test_create_run_rejects_negative_seed(client):
    token = login(client, "boss", "pw12345")
    r = client.post("/api/runs", json={"scenario": "calm", "seed": -1},
                    headers=auth(token))
    assert r.status_code == 422


def test_create_run_rejects_missing_fields(client):
    token = login(client, "boss", "pw12345")
    r = client.post("/api/runs", json={}, headers=auth(token))
    assert r.status_code == 422


def test_get_missing_run_is_404(client):
    token = login(client, "nurse", "pw12345")
    r = client.get("/api/runs/999999", headers=auth(token))
    assert r.status_code == 404


def test_starting_a_missing_run_is_404(client):
    token = login(client, "boss", "pw12345")
    r = client.post("/api/runs/999999/start", headers=auth(token))
    assert r.status_code == 404


# --- health --------------------------------------------------------------


def test_health_needs_no_auth(client):
    assert client.get("/api/health").status_code == 200
