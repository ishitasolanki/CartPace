"""ORM schema, as specified in modular-plan.md.

Kept close to the shape controller.metrics.RunResult and sim.labels.Feedback
already use, so the persistence layer is a straightforward serialization of
state the controller already produces -- not a parallel model of it.
"""

import datetime as dt

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))  # "health_worker" | "supervisor"
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scenario: Mapped[str] = mapped_column(String(32))
    seed: Mapped[int] = mapped_column(Integer)
    n_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # "pending" | "running" | "done"
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    patients: Mapped[list["Patient"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    day_stats: Mapped[list["DayStat"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")


class Patient(Base):
    """The seeded stream, persisted so a run can be replayed exactly."""

    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("run_id", "day", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    day: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)  # arrival order within the day
    arrival_time: Mapped[float] = mapped_column(Float)
    stratum: Mapped[int] = mapped_column(Integer)
    true_label: Mapped[int] = mapped_column(Integer)
    raw_score: Mapped[float] = mapped_column(Float)

    run: Mapped["Run"] = relationship(back_populates="patients")


class Decision(Base):
    """Immutable decision log. Never updated after creation -- see
    controller/policy.py: a decision is irreversible by design, and the log
    that records it should be too."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    refer: Mapped[bool] = mapped_column(Boolean)
    propensity: Mapped[float] = mapped_column(Float)
    s_tilde: Mapped[float] = mapped_column(Float)
    tau: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    run: Mapped["Run"] = relationship(back_populates="decisions")
    label_event: Mapped["LabelEvent | None"] = relationship(
        back_populates="decision", uselist=False, cascade="all, delete-orphan")


class LabelEvent(Base):
    """A delayed confirmatory result.

    propensity_at_decision is deliberately duplicated from Decision rather than
    joined and read live: see sim/labels.py and the build specification's
    Phase 7 integration point 1. A delayed label must be paired with the
    propensity that produced it, not one recomputed later, and storing it here
    makes that pairing impossible to get wrong by construction rather than by
    discipline.
    """

    __tablename__ = "label_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"),
                                             unique=True)
    label: Mapped[int] = mapped_column(Integer)
    propensity_at_decision: Mapped[float] = mapped_column(Float)
    arrived_on_day: Mapped[int] = mapped_column(Integer)

    decision: Mapped["Decision"] = relationship(back_populates="label_event")


class StrataState(Base):
    """Per-day snapshot of the recalibrator's offsets, for the dashboard's
    offset-trajectory chart -- the mechanism made visible."""

    __tablename__ = "strata_state"
    __table_args__ = (UniqueConstraint("run_id", "day", "stratum"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    day: Mapped[int] = mapped_column(Integer)
    stratum: Mapped[int] = mapped_column(Integer)
    offset: Mapped[float] = mapped_column(Float)
    ess: Mapped[float] = mapped_column(Float)


class DayStat(Base):
    """Per-day rollup: burn-down, certificate, exploration cost."""

    __tablename__ = "day_stats"
    __table_args__ = (UniqueConstraint("run_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    day: Mapped[int] = mapped_column(Integer)
    budget: Mapped[int] = mapped_column(Integer)
    spent: Mapped[int] = mapped_column(Integer)
    caught: Mapped[int] = mapped_column(Integer)
    cases: Mapped[int] = mapped_column(Integer)
    explore_spend: Mapped[int] = mapped_column(Integer)
    fnr_hat: Mapped[float | None] = mapped_column(Float, nullable=True)
    fnr_halfwidth: Mapped[float | None] = mapped_column(Float, nullable=True)
    fnr_identifiable: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped["Run"] = relationship(back_populates="day_stats")
