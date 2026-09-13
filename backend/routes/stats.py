"""Certificate, per-stratum offsets, baseline comparison, model card."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.deps import current_user
from backend.models import DayStat, Run, StrataState
from backend.schemas import CertificateOut, DayStatOut, StratumOffset

router = APIRouter(prefix="/api/runs", tags=["stats"])


def _get_run_or_404(db, run_id):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@router.get("/{run_id}/certificate", response_model=CertificateOut)
def certificate(run_id: int, db: Session = Depends(get_db),
                _=Depends(current_user)):
    _get_run_or_404(db, run_id)
    last = (db.query(DayStat).filter(DayStat.run_id == run_id)
           .order_by(DayStat.day.desc()).first())
    if last is None:
        return CertificateOut(fnr_hat=None, halfwidth=None, identifiable=False)
    return CertificateOut(fnr_hat=last.fnr_hat, halfwidth=last.fnr_halfwidth,
                          identifiable=last.fnr_identifiable)


@router.get("/{run_id}/strata", response_model=list[StratumOffset])
def strata(run_id: int, day: int | None = None, db: Session = Depends(get_db),
          _=Depends(current_user)):
    _get_run_or_404(db, run_id)
    q = db.query(StrataState).filter(StrataState.run_id == run_id)
    if day is not None:
        q = q.filter(StrataState.day == day)
    else:
        latest = (db.query(func.max(StrataState.day))
                 .filter(StrataState.run_id == run_id).scalar())
        q = q.filter(StrataState.day == latest)
    return [StratumOffset(stratum=r.stratum, offset=r.offset, ess=r.ess)
           for r in q.order_by(StrataState.stratum).all()]


@router.get("/{run_id}/daystats", response_model=list[DayStatOut])
def day_stats(run_id: int, db: Session = Depends(get_db),
             _=Depends(current_user)):
    _get_run_or_404(db, run_id)
    rows = (db.query(DayStat).filter(DayStat.run_id == run_id)
           .order_by(DayStat.day).all())
    return [DayStatOut(day=r.day, budget=r.budget, spent=r.spent,
                      caught=r.caught, cases=r.cases,
                      explore_spend=r.explore_spend) for r in rows]


@router.get("/{run_id}/compare")
def compare(run_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    """Baseline comparison table for this run's scenario and seed.

    Re-simulates the baselines fresh, on the identical seeded stream, rather
    than reading persisted decisions -- the run only ever persists CartPace's
    own decisions, and the ablation is mandatory in every comparison
    (project.md section 13).
    """
    from controller import baselines, metrics
    from sim import arrivals, scenarios

    run = _get_run_or_404(db, run_id)
    cfg = scenarios.get(run.scenario)
    days = arrivals.make_days(cfg, run.n_days, seed=run.seed)

    import numpy as np
    rows = {
        "Fixed": metrics.run(baselines.Fixed(0.3), days, cfg.delay, "Fixed"),
        "Greedy (no pacing)": metrics.run(baselines.Greedy(), days, cfg.delay,
                                          "Greedy (no pacing)"),
        "Random under budget": metrics.run(
            baselines.RandomUnderBudget(np.random.default_rng(run.seed + 900)),
            days, cfg.delay, "Random under budget"),
        "ClockPacer (ablation)": metrics.run(baselines.ClockPacer(), days,
                                             cfg.delay, "ClockPacer (ablation)"),
    }
    oracle = metrics.run_oracle(days)

    # CartPace's own result for this run, read from what it actually did --
    # not re-simulated. It is fully seeded and deterministic (the controller
    # is built from np.random.default_rng(run.seed + 100) in engine.py, and
    # nothing about a live WS broadcast affects the RNG draw sequence), so
    # re-running it here would reproduce the identical numbers at the cost of
    # a second full simulation. Omitting this row entirely was a real gap:
    # the comparison table is meant to show CartPace against its baselines,
    # and a table with every baseline except the one being evaluated answers
    # the wrong question.
    day_rows = db.query(DayStat).filter(DayStat.run_id == run_id).all()
    caught = sum(d.caught for d in day_rows)
    spent = sum(d.spent for d in day_rows)
    cases = sum(d.cases for d in day_rows)
    explore = sum(d.explore_spend for d in day_rows)
    cartpace_row = {
        "policy": "CartPace", "caught": caught, "spent": spent,
        "recall": caught / cases if cases else 0.0,
        "per_cartridge": caught / spent if spent else 0.0,
        "explore_share": explore / spent if spent else 0.0,
    }

    return {
        "policies": [cartpace_row] + [
            {"policy": r.policy, "caught": r.caught, "spent": r.spent,
            "recall": r.recall, "per_cartridge": r.per_cartridge,
            "explore_share": r.explore_share}
            for r in rows.values()
        ],
        "oracle": {"policy": oracle.policy, "caught": oracle.caught,
                  "spent": oracle.spent},
    }


@router.get("/{run_id}/strata/history")
def strata_history(run_id: int, db: Session = Depends(get_db),
                   _=Depends(current_user)):
    """Every day's offsets for every stratum, in one call.

    Backs the dashboard's offset-trajectory chart -- the mechanism made
    visible. A day-by-day /strata?day=N loop would need one request per day
    of the run (up to ~260), which is needless network overhead for data the
    StrataState table already holds in full.
    """
    _get_run_or_404(db, run_id)
    rows = (db.query(StrataState).filter(StrataState.run_id == run_id)
           .order_by(StrataState.day, StrataState.stratum).all())
    return [{"day": r.day, "stratum": r.stratum, "offset": r.offset,
             "ess": r.ess} for r in rows]
