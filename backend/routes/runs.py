"""Create/list/replay runs, and the run's WebSocket."""

import asyncio

import numpy as np
from fastapi import (APIRouter, Depends, HTTPException, Query, WebSocket,
                     WebSocketDisconnect, status)
from sqlalchemy.orm import Session

from backend.db import SessionLocal, get_db
from backend.deps import current_user, current_user_ws
from backend.engine import run_simulation
from backend.models import Decision, Patient, Run, User
from backend.schemas import DecisionOut, RunCreate, RunOut
from backend.ws import ConnectionManager

router = APIRouter(prefix="/api/runs", tags=["runs"])
manager = ConnectionManager()


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreate, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    # project.md section 4: "Run the clinic day" is a health_worker
    # capability, not a supervisor-only one. Supervisor-only in this cut is
    # nothing at the data level -- PUT /api/config/budget was deliberately
    # dropped (see routes/config.py) -- so there is currently no route that
    # should actually require require_role("supervisor").
    try:
        body.validate_scenario()
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    run = Run(user_id=user.id, scenario=body.scenario, seed=body.seed,
             n_days=body.n_days, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db), _=Depends(current_user)):
    return db.query(Run).order_by(Run.id.desc()).limit(100).all()


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@router.post("/{run_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_run(run_id: int, db: Session = Depends(get_db),
                    _=Depends(current_user)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    if run.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT,
                           f"run is already {run.status}")

    # A dedicated session for the background task: the request's session
    # closes when this handler returns, long before the simulation finishes.
    task_db = SessionLocal()
    task_run = task_db.get(Run, run_id)
    seed_rng = np.random.default_rng(run.seed + 100)
    asyncio.create_task(_run_and_close(task_db, task_run, seed_rng))
    return {"status": "started"}


async def _run_and_close(db, run_row, seed_rng):
    """The task created in start_run() is fire-and-forget from FastAPI's point
    of view -- nothing awaits it, so an unhandled exception here is silently
    swallowed by asyncio and never surfaces as an HTTP error. Without the
    except clause below, a failing run leaves run.status stuck at "running"
    forever and every WebSocket client blocks on a run_complete message that
    will never arrive. This was found by a hang in test_engine.py that traced
    back to exactly this: an unrelated bug raised inside run_simulation, and
    the client-side symptom was an indefinite wait with no error at all."""
    try:
        await run_simulation(db, run_row, manager, seed_rng)
    except Exception as e:
        run_row.status = "error"
        db.commit()
        await manager.broadcast(run_row.id, {"type": "error", "detail": str(e)})
        raise
    finally:
        db.close()


@router.get("/{run_id}/decisions", response_model=list[DecisionOut])
def get_decisions(run_id: int, offset: int = Query(0, ge=0),
                  limit: int = Query(200, ge=1, le=1000),
                  db: Session = Depends(get_db), _=Depends(current_user)):
    rows = (db.query(Decision, Patient)
           .join(Patient, Decision.patient_id == Patient.id)
           .filter(Decision.run_id == run_id)
           .order_by(Patient.day, Patient.seq)
           .offset(offset).limit(limit).all())
    return [
        DecisionOut(day=p.day, seq=p.seq, refer=d.refer, propensity=d.propensity,
                   s_tilde=d.s_tilde, tau=d.tau, reason=d.reason,
                   stratum=p.stratum, true_label=p.true_label)
        for d, p in rows
    ]


@router.websocket("/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: int,
                 token: str = Query(...)):
    db = SessionLocal()
    try:
        user = await current_user_ws(token, db)
        if user is None:
            await websocket.close(code=4401)  # 4401: app-defined "unauthorized"
            return
        run = db.get(Run, run_id)
        if run is None:
            await websocket.close(code=4404)
            return
    finally:
        db.close()

    await manager.connect(run_id, websocket)
    try:
        while True:
            # Client sends nothing meaningful; this just detects disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(run_id, websocket)
