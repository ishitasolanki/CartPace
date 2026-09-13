"""Stats routes: certificate, per-stratum offsets, day stats, baseline
comparison.

Same fixture pattern as test_engine.py -- a real temp-file SQLite database,
because these tests exercise a run through the background task and the
:memory:+StaticPool hazard documented there applies here too.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

from backend.auth import hash_password              # noqa: E402
from backend.db import Base, get_db                  # noqa: E402
from backend.main import app                          # noqa: E402
from backend.models import User                       # noqa: E402


@pytest.fixture()
def client(monkeypatch):
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

    monkeypatch.setattr("backend.routes.runs.SessionLocal", TestSession)
    app.dependency_overrides[get_db] = _get_db

    db = TestSession()
    db.add(User(username="boss", password_hash=hash_password("pw12345"),
               role="supervisor"))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)


def login(c):
    r = c.post("/api/auth/login", json={"username": "boss", "password": "pw12345"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def run_to_completion(c, headers, scenario="ranking_drift", seed=3, n_days=90):
    r = c.post("/api/runs", json={"scenario": scenario, "seed": seed,
                                  "n_days": n_days}, headers=headers)
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    with c.websocket_connect(f"/api/runs/{run_id}/ws?token={headers['Authorization'].split()[1]}") as ws:
        c.post(f"/api/runs/{run_id}/start", headers=headers)
        while ws.receive_json()["type"] != "run_complete":
            pass
    return run_id


def test_certificate_identifiable_and_bracketing(client):
    """G5 through the API: the certificate should be identifiable and, since
    ranking_drift exercises exploration, report a non-trivial estimate."""
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers)

    r = client.get(f"/api/runs/{run_id}/certificate", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["identifiable"] is True
    assert body["fnr_hat"] is not None
    assert 0.0 <= body["fnr_hat"] <= 1.0
    assert body["halfwidth"] is not None and body["halfwidth"] >= 0.0


def test_certificate_before_any_run_is_not_identifiable(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/runs", json={"scenario": "calm", "seed": 1, "n_days": 5},
                    headers=headers)
    run_id = r.json()["id"]
    r = client.get(f"/api/runs/{run_id}/certificate", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"fnr_hat": None, "halfwidth": None, "identifiable": False}


def test_strata_latest_day_only_by_default(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers)

    r = client.get(f"/api/runs/{run_id}/strata", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    from sim.scenarios import N_STRATA
    assert len(rows) == N_STRATA
    assert {row["stratum"] for row in rows} == set(range(N_STRATA))


def test_strata_specific_day(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers)

    r = client.get(f"/api/runs/{run_id}/strata", params={"day": 0}, headers=headers)
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_strata_offset_tracks_the_drifted_stratum(client):
    """The mechanism made visible: by the end of a ranking_drift run, the
    offset for the drifted stratum should have moved meaningfully, and the
    others should not have."""
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers, scenario="ranking_drift", seed=7)

    from sim.scenarios import get as get_scenario
    drifted = get_scenario("ranking_drift").rank_drift_stratum

    r = client.get(f"/api/runs/{run_id}/strata", headers=headers)
    rows = {row["stratum"]: row["offset"] for row in r.json()}
    assert abs(rows[drifted]) > 0.3, "drifted stratum's offset should have moved"


def test_daystats_are_ordered_and_cover_every_day(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers, n_days=20)

    r = client.get(f"/api/runs/{run_id}/daystats", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert [row["day"] for row in rows] == list(range(20))
    assert all(row["spent"] <= row["budget"] for row in rows)
    assert all(row["caught"] <= row["cases"] for row in rows)


def test_compare_includes_the_mandatory_ablation(client):
    """project.md section 13: ClockPacer is not optional in any comparison."""
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers, n_days=30)

    r = client.get(f"/api/runs/{run_id}/compare", headers=headers)
    assert r.status_code == 200
    body = r.json()
    names = {p["policy"] for p in body["policies"]}
    assert "ClockPacer (ablation)" in names
    assert "oracle" in body
    assert body["oracle"]["spent"] > 0


def test_compare_includes_cartpace_itself(client):
    """The comparison must show CartPace, not just its baselines -- a table
    with every baseline except the policy actually being evaluated answers
    the wrong question. CartPace's row is read from what the run actually
    did (DayStat), not re-simulated, so it must match the run's own history."""
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers, n_days=30)

    days = client.get(f"/api/runs/{run_id}/daystats", headers=headers).json()
    expected_caught = sum(d["caught"] for d in days)
    expected_spent = sum(d["spent"] for d in days)

    r = client.get(f"/api/runs/{run_id}/compare", headers=headers)
    body = r.json()
    cartpace = next((p for p in body["policies"] if p["policy"] == "CartPace"), None)
    assert cartpace is not None, "CartPace itself must appear in its own comparison"
    assert cartpace["caught"] == expected_caught
    assert cartpace["spent"] == expected_spent


def test_compare_is_reproducible_for_the_same_run(client):
    """The comparison re-simulates baselines fresh on the run's seed; calling
    it twice must give identical numbers, not fresh randomness."""
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers, n_days=20)

    r1 = client.get(f"/api/runs/{run_id}/compare", headers=headers).json()
    r2 = client.get(f"/api/runs/{run_id}/compare", headers=headers).json()
    assert r1 == r2


def test_stats_endpoints_require_auth(client):
    assert client.get("/api/runs/1/certificate").status_code == 401
    assert client.get("/api/runs/1/strata").status_code == 401
    assert client.get("/api/runs/1/daystats").status_code == 401
    assert client.get("/api/runs/1/compare").status_code == 401


def test_stats_endpoints_404_on_missing_run(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/runs/999999/certificate",
                      headers=headers).status_code == 404
    assert client.get("/api/runs/999999/strata",
                      headers=headers).status_code == 404
    assert client.get("/api/runs/999999/daystats",
                      headers=headers).status_code == 404
    assert client.get("/api/runs/999999/compare",
                      headers=headers).status_code == 404


def test_strata_history_covers_every_day_and_stratum(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = run_to_completion(client, headers, n_days=15)

    from sim.scenarios import N_STRATA
    r = client.get(f"/api/runs/{run_id}/strata/history", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 15 * N_STRATA
    assert {row["day"] for row in rows} == set(range(15))
    assert {row["stratum"] for row in rows} == set(range(N_STRATA))


def test_strata_history_404_on_missing_run(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/runs/999999/strata/history", headers=headers)
    assert r.status_code == 404
