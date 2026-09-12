"""Comparison policies.

All expose the same surface as the controller -- `start_day`, `decide`,
`end_day`, `observe_labels` -- so the harness cannot accidentally treat one
differently from another.

`ClockPacer` is the one that matters. It is the **ablation**: the novel
component deleted, everything else intact. It deliberately reuses the very same
`BudgetPacer` the full controller uses, so the comparison isolates
recalibration-plus-exploration and cannot be flattered by an incidental
difference in the pacing code.

The earlier iteration of this project survived only because this ablation
happened to be written: it beat the full controller and revealed that the
claimed contribution was doing nothing. It is mandatory in every comparison.
"""

import numpy as np

from .budget import DAY_HOURS, BudgetPacer
from .policy import (ABOVE_THRESHOLD, BELOW_FLOOR, BUDGET_EXHAUSTED, Decision)


class _Base:
    """Shared budget bookkeeping. Referral never exceeds the budget."""

    def __init__(self):
        self.budget_left = 0
        self.spent_today = 0

    def start_day(self, budget: int) -> None:
        self.budget_left = int(budget)
        self.spent_today = 0

    def end_day(self, n_actual: int) -> None:
        pass

    def observe_labels(self, batch) -> None:
        """Baselines do not learn. Accepting the call keeps the harness
        uniform, which is what stops the comparison drifting apart."""

    def _spend(self) -> None:
        self.budget_left -= 1
        self.spent_today += 1


class Fixed(_Base):
    """Current standard of care: one threshold, set by protocol, never moved."""

    def __init__(self, tau: float):
        super().__init__()
        self.tau = tau

    def decide(self, score: float, stratum: int, t: float) -> Decision:
        if self.budget_left <= 0:
            return Decision(False, 0.0, score, score, stratum, self.tau,
                            BUDGET_EXHAUSTED)
        refer = bool(score > self.tau)
        if refer:
            self._spend()
        return Decision(refer, 1.0 if refer else 0.0, score, score, stratum,
                        self.tau, ABOVE_THRESHOLD if refer else BELOW_FLOOR)


class Greedy(Fixed):
    """High-sensitivity protocol with no pacing.

    The morning-exhaustion failure mode: a low threshold refers almost everyone
    early, the budget is gone by mid-morning, and every afternoon arrival --
    including genuinely high-risk ones -- is turned away.
    """

    def __init__(self, tau: float = 0.10):
        super().__init__(tau=tau)


class RandomUnderBudget(_Base):
    """Floor. Refers at random at the rate the budget can sustain."""

    def __init__(self, rng: np.random.Generator, n_prior: float = 200.0):
        super().__init__()
        self.rng = rng
        self.n_prior = n_prior
        self.p = 0.2

    def start_day(self, budget: int) -> None:
        super().start_day(budget)
        self.p = min(1.0, budget / self.n_prior)

    def decide(self, score: float, stratum: int, t: float) -> Decision:
        if self.budget_left <= 0:
            return Decision(False, 0.0, score, score, stratum, 0.0,
                            BUDGET_EXHAUSTED)
        refer = bool(self.rng.random() < self.p)
        if refer:
            self._spend()
        return Decision(refer, self.p, score, score, stratum, 0.0,
                        ABOVE_THRESHOLD if refer else BELOW_FLOOR)


class ClockPacer(_Base):
    """THE ABLATION. Budget pacing alone.

    No recalibration, no exploration, deterministic thresholding. Identical
    pacing machinery to the full controller, so any difference in outcome is
    attributable to the learned correction and the exploration that funds it --
    which is the entire question the Phase 6 gate asks.
    """

    def __init__(self, sketch_size: int = 512, day_hours: float = DAY_HOURS,
                 n_prior: float = 200.0):
        super().__init__()
        self.pacer = BudgetPacer(sketch_size=sketch_size, day_hours=day_hours,
                                 n_prior=n_prior)

    def start_day(self, budget: int) -> None:
        super().start_day(budget)
        self.pacer.start_day()

    def end_day(self, n_actual: int) -> None:
        self.pacer.end_day(n_actual)

    def decide(self, score: float, stratum: int, t: float) -> Decision:
        self.pacer.observe(score)
        if self.budget_left <= 0:
            return Decision(False, 0.0, score, score, stratum, np.inf,
                            BUDGET_EXHAUSTED)
        tau = self.pacer.tau_for(self.budget_left, t)
        refer = bool(score > tau)
        if refer:
            self._spend()
        return Decision(refer, 1.0 if refer else 0.0, score, score, stratum,
                        tau, ABOVE_THRESHOLD if refer else BELOW_FLOOR)


def top_b_oracle(day, use_risk: bool = False) -> tuple[int, int]:
    """Upper bound: full-day lookahead, spend the whole budget on the best.

    Not a policy -- it sees the entire day at once, which no online method can.
    Returns (cases caught, cartridges spent).

    Two different ceilings, and the distinction matters under ranking drift:

    `use_risk=False` (default) ranks by the **frozen model's score as given**,
    drift included. This is the best any policy could do while trusting the
    model's ranking, so it is the right yardstick for pacing-style methods.
    A controller that *corrects* the ranking can legitimately beat it -- and
    doing so is precisely the claimed effect, not an anomaly.

    `use_risk=True` ranks by true latent risk, which no deployed system can
    observe. That is the absolute ceiling and bounds what recalibration could
    ever recover.

    Either way this is an upper bound on *cases*, not on cases per cartridge:
    it always spends the full budget, so a policy that under-spends can beat it
    on the ratio while catching fewer people. That is exactly why the ratio is
    not an acceptance criterion.
    """
    key = day.risks if use_risk else day.scores
    idx = np.argsort(-key)[:day.budget]
    return int(day.labels[idx].sum()), int(len(idx))
