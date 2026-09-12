"""Generating a clinic day.

Design decision that matters: the frozen model is **exactly calibrated** in the
absence of ranking drift. Each patient gets a latent risk p, the label is drawn
from p, and the model's score *is* p. Drift then depresses the score for one
stratum by a pure logit offset.

Two reasons for building it this way:

1. The miscalibration introduced is exactly a logit shift, which is exactly
   what the controller's correction family can represent. The controller is
   therefore being tested on whether it can *find* the offset, not on whether
   its functional form happens to fit -- those are different questions and
   conflating them would flatter the result.
2. Absent drift the correct offset is zero, so "does it degenerate to pacing
   when there is nothing to learn" becomes a sharp, checkable claim.

The simulator knows the right answer (`Day.true_offsets`), which makes
convergence directly testable rather than inferred from downstream metrics.
"""

from dataclasses import dataclass

import numpy as np

from . import drift
from .scenarios import N_STRATA, Scenario


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p, eps=1e-6):
    p = np.clip(p, eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


@dataclass(frozen=True)
class Day:
    """One clinic day, fully determined by the scenario and the seed."""

    index: int
    times: np.ndarray        # arrival time in hours, sorted ascending
    strata: np.ndarray       # int in [0, N_STRATA)
    labels: np.ndarray       # 0/1 true status -- the simulator's secret
    scores: np.ndarray       # frozen model output in (0, 1), drifted
    risks: np.ndarray        # latent true risk -- what the score would be if honest
    budget: int
    true_offsets: np.ndarray  # per-stratum logit offset the controller should learn

    @property
    def n(self) -> int:
        return len(self.times)


def make_day(cfg: Scenario, day_index: int, rng: np.random.Generator) -> Day:
    n = max(30, int(rng.normal(cfg.n_mean, cfg.n_sd)))

    strata = rng.choice(N_STRATA, size=n, p=np.asarray(cfg.stratum_probs))

    # Latent risk: logit-normal around each stratum's prevalence. The spread is
    # what gives the model its discriminative power.
    loc = np.array([logit(drift.prevalence(cfg, day_index, k)) for k in range(N_STRATA)])
    risk_logit = rng.normal(loc[strata], cfg.spread)
    risks = sigmoid(risk_logit)

    labels = (rng.random(n) < risks).astype(int)

    # The frozen model under-scores drifted strata by a logit offset.
    offsets = np.array([drift.rank_offset(cfg, day_index, k) for k in range(N_STRATA)])
    scores = sigmoid(risk_logit - offsets[strata])

    # Morning-weighted arrivals: the clinic fills up early, which is what makes
    # naive greedy thresholding exhaust the budget before lunch.
    times = np.sort(rng.beta(2.0, 3.0, n) * cfg.day_hours)

    budget = cfg.shortage_budget if rng.random() < cfg.shortage_prob else cfg.budget

    return Day(index=day_index, times=times, strata=strata, labels=labels,
               scores=scores, risks=risks, budget=int(budget),
               true_offsets=offsets)


def make_days(cfg: Scenario, n_days: int, seed: int) -> list[Day]:
    """A seeded run. Same cfg and seed always produce identical days (NFR4)."""
    rng = np.random.default_rng(seed)
    return [make_day(cfg, t, rng) for t in range(n_days)]
