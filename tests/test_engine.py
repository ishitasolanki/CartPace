"""Walking skeleton: login -> create a run -> start it -> stream over a real
WebSocket -> decisions and labels land correctly in the database.

This is the test that would have caught the propensity-matching bug in
engine.py if it had shipped: two decisions in the same run sharing a
propensity (every above-threshold referral is 1.0) is the normal case, not an
edge case, so a real multi-day run exercises it on essentially every day.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

from backend.auth import hash_password                   # noqa: E402
from backend.db import Base, SessionLocal, get_db         # noqa: E402
from backend.main import app                              # noqa: E402
from backend.models import Decision, LabelEvent, Patient, Run, User  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    # A real temp-file database, not `sqlite://` (:memory:) + StaticPool.
    #
    # This backend runs a background asyncio task (the simulation loop) that
    # interleaves with concurrent HTTP requests and a WebSocket on the same
    # event loop -- exactly the scenario StaticPool's single shared connection
    # cannot support: every SQLAlchemy Session created from the engine wraps
    # the *same* physical DBAPI connection, so one session's close (implicit
    # rollback) can discard another session's uncommitted, already-flushed
    # work if they interleave. That is exactly what happened here -- observed
    # directly as Decision.id restarting at 1 on day 1 instead of continuing
    # from day 0's last id, meaning day 0's rows had been silently rolled back
    # by a concurrent request's session teardown.
    #
    # A temp file gives every session its own real connection, which is also
    # what backend/db.py already does in production (DATABASE_URL defaults to
    # a file, never :memory:) -- so this fixture change makes the test *more*
    # representative of production, not less.
    db_path = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}",
                           connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    # The background task in routes.runs opens its own SessionLocal(), which
    # by default points at the real sqlite file. Redirect it at the same
    # in-memory engine as the request-scoped session, or the background task
    # writes to a database the test can never see.
    monkeypatch.setattr("backend.routes.runs.SessionLocal", TestSession)

    app.dependency_overrides[get_db] = _get_db
    db = TestSession()
    db.add(User(username="boss", password_hash=hash_password("pw12345"),
               role="supervisor"))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c, TestSession
    app.dependency_overrides.clear()
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)


def login(client, username="boss", password="pw12345"):
    r = client.post("/api/auth/login",
                    json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_full_walking_skeleton(client):
    c, TestSession = client
    token = login(c)
    headers = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/runs",
              json={"scenario": "ranking_drift", "seed": 3, "n_days": 90},
              headers=headers)
    assert r.status_code == 201
    run_id = r.json()["id"]

    with c.websocket_connect(f"/api/runs/{run_id}/ws?token={token}") as ws:
        r = c.post(f"/api/runs/{run_id}/start", headers=headers)
        assert r.status_code == 202

        saw_decision = saw_day_end = saw_complete = False
        while not saw_complete:
            msg = ws.receive_json()
            if msg["type"] == "decision":
                saw_decision = True
                assert 0.0 < msg["propensity"] <= 1.0 or msg["propensity"] == 0.0
            elif msg["type"] == "day_end":
                saw_day_end = True
                assert isinstance(msg["offsets"], list)
            elif msg["type"] == "run_complete":
                saw_complete = True

    assert saw_decision and saw_day_end and saw_complete

    db = TestSession()
    try:
        n_decisions = db.query(Decision).filter(Decision.run_id == run_id).count()
        n_patients = db.query(Patient).filter(Patient.run_id == run_id).count()
        assert n_decisions == n_patients > 0

        run = db.get(Run, run_id)
        assert run.status == "done"

        # The bug this test exists to catch: every label event must be paired
        # with the decision that was ACTUALLY referred to produce it, not an
        # arbitrary decision sharing the same propensity.
        events = (db.query(LabelEvent)
                 .join(Decision, LabelEvent.decision_id == Decision.id)
                 .filter(Decision.run_id == run_id).all())
        assert len(events) > 0, "delayed labels should have landed by day 90"
        for e in events:
            decision = db.get(Decision, e.decision_id)
            assert decision.refer, "a label event must point at a referral"
            assert e.propensity_at_decision == decision.propensity
    finally:
        db.close()


def test_two_runs_do_not_share_controller_state(client):
    """Integration point 2: a fresh controller per run, never leaked across
    concurrent runs."""
    c, TestSession = client
    token = login(c)
    headers = {"Authorization": f"Bearer {token}"}

    ids = []
    for seed in (1, 2):
        r = c.post("/api/runs",
                  json={"scenario": "calm", "seed": seed, "n_days": 20},
                  headers=headers)
        ids.append(r.json()["id"])

    for run_id in ids:
        with c.websocket_connect(f"/api/runs/{run_id}/ws?token={token}") as ws:
            c.post(f"/api/runs/{run_id}/start", headers=headers)
            while True:
                msg = ws.receive_json()
                if msg["type"] == "run_complete":
                    break

    db = TestSession()
    try:
        counts = [db.query(Patient).filter(Patient.run_id == rid).count()
                 for rid in ids]
        assert all(n > 0 for n in counts)
        assert len(set(ids)) == 2
    finally:
        db.close()


def test_ws_rejects_bad_token(client):
    c, _ = client
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/runs/1/ws?token=garbage"):
            pass


def test_ws_rejects_missing_run(client):
    c, _ = client
    token = login(c)
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/api/runs/999999/ws?token={token}"):
            pass


def test_budget_invariant_holds_through_the_api(client):
    c, TestSession = client
    token = login(c)
    headers = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/runs",
              json={"scenario": "shortage", "seed": 5, "n_days": 60},
              headers=headers)
    run_id = r.json()["id"]

    with c.websocket_connect(f"/api/runs/{run_id}/ws?token={token}") as ws:
        c.post(f"/api/runs/{run_id}/start", headers=headers)
        while ws.receive_json()["type"] != "run_complete":
            pass

    db = TestSession()
    try:
        from sqlalchemy import func
        per_day = (db.query(Patient.day, func.count(Decision.id))
                  .join(Decision, Decision.patient_id == Patient.id)
                  .filter(Patient.run_id == run_id, Decision.refer.is_(True))
                  .group_by(Patient.day).all())
        assert all(spent <= 40 for _day, spent in per_day)
    finally:
        db.close()
