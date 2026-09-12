"""The controller: recalibrate, pace, explore, decide.

Order matters. The offsets correct the score, the pacer works on the corrected
score, and the explorer floors the propensity so nothing is ever unreachable.

    s_tilde = sigmoid(logit(s) + d_k)      # recalibrate
    tau     = quantile(sketch, 1 - afford) # pace, on the corrected score
    p       = 1 above tau, banded in the strip below it, floor elsewhere
    refer   = draw(p) and budget remains

**The budget is physically hard and always wins.** It is checked before the
draw, so no sequence of random outcomes can overspend it. The false-negative
certificate is reported, never enforced against reality: when the budget cannot
support the target, the honest output is a degrading certificate, not a system
pretending the target is met.

### Known limitation: positivity ends when the budget does

Patients arriving after the budget is exhausted have a referral probability of
genuinely zero, so positivity does not hold for them and they are excluded from
the estimand. The quantity being estimated is therefore "case rate among
patients arriving while budget remained", not "among all arrivals".

This is deliberate and bounded rather than hidden: pacing exists precisely to
make the budget last the whole day, so exhaustion should be rare, and when it
does happen the excluded group is a tail of late arrivals. It is recorded here
because an estimand that quietly changes definition under load is exactly the
kind of thing that invalidates a certificate without ever raising an error.
"""

from dataclasses import dataclass

import numpy as np

from .budget import DAY_HOURS, BudgetPacer
from .certificate import FNRCertificate
from .explore import EXPLORE_FRAC, P_FLOOR, Explorer
from .recalibrate import StratumCalibrator

ABOVE_THRESHOLD = "above_threshold"
EXPLORE = "explore"
BELOW_FLOOR = "below_floor"
BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class Decision:
    """One irreversible decision, with everything needed to audit it later."""

    refer: bool
    propensity: float    # probability the draw used. 0.0 iff budget exhausted.
    score: float         # raw frozen-model score
    s_tilde: float       # after per-stratum correction
    stratum: int
    tau: float
    reason: str


class CartPaceController:
    """Model-agnostic online allocator for a depleting test consumable."""

    def __init__(self, n_strata: int, rng: np.random.Generator,
                 explore_frac: float = EXPLORE_FRAC,
                 p_floor: float = P_FLOOR, gamma: float = 0.4,
                 ess_min: float = 30.0, sketch_size: int = 512,
                 w_cap: float = 0.0, explore_only: bool = False,
                 day_hours: float = DAY_HOURS, n_prior: float = 200.0,
                 recalibrate: bool = True):
        self.rng = rng
        self.n_strata = n_strata
        self.p_floor = p_floor
        # Running share of arrivals per stratum, so the quota can be spread
        # over the arrivals each stratum still expects today. Six scalars.
        self._share = np.full(n_strata, 1.0 / n_strata)
        self._day_counts = np.zeros(n_strata)
        self._days = 0
        # `recalibrate=False` is what makes the ablation an ablation: identical
        # machinery, learned correction removed.
        self.recalibrate = recalibrate
        self.calib = StratumCalibrator(n_strata, gamma=gamma, ess_min=ess_min,
                                       p_floor=p_floor, w_cap=w_cap,
                                       explore_only=explore_only)
        self.pacer = BudgetPacer(sketch_size=sketch_size, day_hours=day_hours,
                                 n_prior=n_prior)
        self.explorer = Explorer(n_strata, explore_frac=explore_frac,
                                 p_floor=p_floor)
        self.cert = FNRCertificate(p_floor=p_floor)
        self.budget_left = 0
        self.spent_today = 0

    # --- lifecycle ---------------------------------------------------------

    def start_day(self, budget: int) -> None:
        if budget < 0:
            raise ValueError("budget must be non-negative")
        self.budget_left = int(budget)
        self.spent_today = 0
        self.pacer.start_day()
        self._day_counts[:] = 0.0
        self.explorer.start_day(
            budget, self.calib.deficit() if self.recalibrate else None)

    def end_day(self, n_actual: int) -> None:
        self.pacer.end_day(n_actual)
        if n_actual > 0:
            self._days += 1
            step = min(self._days, 30)
            self._share += (self._day_counts / n_actual - self._share) / step

    def observe_labels(self, batch) -> None:
        """Delayed confirmatory results. Each carries the propensity that
        produced its referral -- never one recomputed now."""
        self.cert.observe(batch)
        if self.recalibrate:
            self.calib.update(batch)

    # --- the decision ------------------------------------------------------

    def decide(self, score: float, stratum: int, t: float) -> Decision:
        s_tilde = self.calib.correct(score, stratum) if self.recalibrate else score
        self.pacer.observe(s_tilde)

        # Hard invariant, checked before the draw: an exhausted budget cannot
        # be overspent by any sequence of random outcomes.
        if self.budget_left <= 0:
            return Decision(False, 0.0, score, s_tilde, stratum,
                            np.inf, BUDGET_EXHAUSTED)

        self._day_counts[stratum] += 1
        afford = self.pacer.afford(self.budget_left, t)
        tau = self.pacer.tau_at(afford)
        remaining_k = self.pacer.remaining(t) * self._share[stratum]

        p = self.explorer.propensity(s_tilde, tau, stratum, remaining_k)
        refer = bool(self.rng.random() < p)

        if s_tilde > tau:
            reason = ABOVE_THRESHOLD
        elif p > self.p_floor:
            reason = EXPLORE
        else:
            reason = BELOW_FLOOR

        if refer:
            self.budget_left -= 1
            self.spent_today += 1
            if p < 1.0:
                self.explorer.charge(stratum)

        return Decision(refer, p, score, s_tilde, stratum, tau, reason)

    # --- introspection -----------------------------------------------------

    @property
    def offsets(self) -> np.ndarray:
        return self.calib.offsets

    def certificate(self) -> tuple[float, float]:
        """Current false-negative estimate and halfwidth. Reported, never
        enforced -- see the module docstring."""
        return self.cert.estimate()

    @property
    def state_bytes(self) -> int:
        """Total controller state. Flat in patients seen -- the O(1) claim."""
        return (self.calib.state_bytes + self.pacer.state_bytes
                + self.explorer.state_bytes + self.cert.state_bytes + 4 * 8)
