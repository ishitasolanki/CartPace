"""The run loop: sim -> controller -> persist -> broadcast.

One CartPaceController per run, never shared or reused across runs -- see
integration point 2 in modular-plan.md. The controller is stateful, so a run
that reused an instance across concurrent runs would leak one run's offsets
and budget into another's.
"""

import asyncio

from sqlalchemy.orm import Session

from controller.metrics import RunResult
from controller.policy import CartPaceController
from sim import arrivals, scenarios
from collections import deque

from sim.labels import DelayedLabels

from backend.models import Decision, DayStat, LabelEvent, Patient, StrataState
from backend.ws import ConnectionManager


async def run_simulation(
    db: Session, run_row, manager: ConnectionManager, seed_rng
) -> None:
    """Stream one run's days through a fresh controller, persisting and
    broadcasting each decision.

    Runs on the event loop with periodic `asyncio.sleep(0)` yields rather than
    in a thread, because SQLite (this project's DB, per project.md section 11)
    does not benefit from a second writer thread and the yields are what let
    the WebSocket actually flush frames as they are produced.
    """
    cfg = scenarios.get(run_row.scenario)
    days = arrivals.make_days(cfg, run_row.n_days, seed=run_row.seed)
    ctrl = CartPaceController(scenarios.N_STRATA, seed_rng)
    queue = DelayedLabels(delay=cfg.delay)
    # Mirrors queue's internal delay pipeline one-for-one, carrying the actual
    # decision row id instead of re-deriving it later. Matching a delayed label
    # back to its decision by (stratum, propensity) alone is unsound -- every
    # above-threshold referral shares propensity 1.0, every floor referral
    # shares p_floor, so a lookup by those fields alone can silently attach a
    # label to the wrong patient's decision.
    id_pipeline: deque[list[int]] = deque()
    id_today: list[int] = []
    result = RunResult(policy="CartPace")

    run_row.status = "running"
    db.commit()

    for day_idx, day in enumerate(days):
        ctrl.start_day(day.budget)
        result.cases += int(day.labels.sum())
        day_caught = 0
        day_explore = 0

        # Two passes rather than one, and it is worth explaining why. A naive
        # per-patient flush() -- needed to get an autoincrement id for the
        # foreign key before the next insert -- costs a full SQLite round trip
        # per row. Measured: 21s for an 8-day, ~1,600-patient run, which would
        # put a realistic 260-day run at well over ten minutes. That is a
        # genuine usability defect for a system whose point is a live
        # dashboard, not a subtlety.
        #
        # ctrl.decide() is stateful and its output depends on call order, so
        # the sequential decision loop cannot be batched or reordered. The
        # persistence can: compute every decision first (pass 1, no DB at
        # all), batch-insert every Patient row for the day and flush once
        # (pass 2), batch-insert every Decision row using those ids and flush
        # once (pass 3), then do the per-patient bookkeeping and broadcast
        # that only needs ids which now exist (pass 4). Two flushes a day
        # instead of two per patient.
        decided = []
        for seq in range(day.n):
            score = float(day.scores[seq])
            stratum = int(day.strata[seq])
            label = int(day.labels[seq])
            d = ctrl.decide(score, stratum, float(day.times[seq]))
            decided.append((seq, score, stratum, label, d))

        patients = [
            Patient(run_id=run_row.id, day=day_idx, seq=seq,
                   arrival_time=float(day.times[seq]), stratum=stratum,
                   true_label=label, raw_score=score)
            for seq, score, stratum, label, _d in decided
        ]
        db.add_all(patients)
        db.flush()

        decisions = [
            Decision(run_id=run_row.id, patient_id=patient.id, refer=d.refer,
                    propensity=d.propensity, s_tilde=d.s_tilde,
                    tau=(d.tau if d.tau != float("inf") else -1.0),
                    reason=d.reason)
            for (_seq, _score, _stratum, _label, d), patient
            in zip(decided, patients)
        ]
        db.add_all(decisions)
        db.flush()

        for (seq, score, stratum, label, d), decision in zip(decided, decisions):
            if d.refer:
                result.caught += label
                result.spent += 1
                day_caught += label
                if d.propensity < 1.0:
                    result.explore_spend += 1
                    day_explore += 1
                queue.record(stratum=stratum, propensity=d.propensity,
                            score=score, label=label)
                id_today.append(decision.id)
            else:
                result.missed += label

            await manager.broadcast(run_row.id, {
                "type": "decision", "day": day_idx, "seq": seq,
                "refer": d.refer, "propensity": d.propensity,
                "s_tilde": d.s_tilde, "reason": d.reason, "stratum": stratum,
            })
            if seq % 20 == 0:
                await asyncio.sleep(0)  # yield so the socket can flush

        assert ctrl.spent_today <= day.budget, (
            f"BUDGET VIOLATED on day {day_idx}: "
            f"{ctrl.spent_today} > {day.budget}")

        batch = queue.end_day()
        id_pipeline.append(id_today)
        id_today = []
        landed_ids = id_pipeline.popleft() if len(id_pipeline) > cfg.delay else []

        ctrl.observe_labels(batch)
        ctrl.end_day(day.n)

        # Persist delayed labels landing today, paired with their decision by
        # id -- carried alongside the feedback queue rather than re-derived
        # from it, since propensity alone does not identify a decision.
        assert len(batch) == len(landed_ids), (
            "feedback queue and id pipeline drifted out of lockstep")
        for f, decision_id in zip(batch, landed_ids):
            db.add(LabelEvent(decision_id=decision_id, label=f.label,
                             propensity_at_decision=f.propensity,
                             arrived_on_day=day_idx))

        fnr_hat, half = ctrl.certificate()
        db.add(DayStat(run_id=run_row.id, day=day_idx, budget=day.budget,
                       spent=ctrl.spent_today, caught=day_caught,
                       cases=int(day.labels.sum()), explore_spend=day_explore,
                       fnr_hat=None if fnr_hat != fnr_hat else fnr_hat,
                       fnr_halfwidth=None if half != half else half,
                       fnr_identifiable=ctrl.cert.identifiable))
        for k, (off, ess) in enumerate(zip(ctrl.offsets, ctrl.calib.ess)):
            db.add(StrataState(run_id=run_row.id, day=day_idx, stratum=k,
                              offset=float(off), ess=float(ess)))

        db.commit()
        await manager.broadcast(run_row.id, {
            "type": "day_end", "day": day_idx, "budget": day.budget,
            "spent": ctrl.spent_today, "offsets": [float(x) for x in ctrl.offsets],
            "fnr_hat": fnr_hat if fnr_hat == fnr_hat else None,
            "fnr_halfwidth": half if half == half else None,
            "identifiable": ctrl.cert.identifiable,
        })

    run_row.status = "done"
    db.commit()
    await manager.broadcast(run_row.id, {"type": "run_complete"})
