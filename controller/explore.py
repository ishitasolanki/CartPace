"""Self-funded exploration, directed at the strata that need it.

Deterministic thresholding gives every sub-threshold patient a referral
probability of exactly zero. Not small -- zero. Positivity fails, inverse
propensity weighting is undefined, and no amount of reweighting recovers the
missing mass. You cannot estimate what you missed when nothing below the line
is ever tested.

So referral is stochastic and every propensity is logged and bounded below.
The cost is real and is paid from the same cartridge budget being optimised:
the controller buys its own calibration data out of the resource it is
spending. That coupling is the claimed contribution.

**Exploration is a stability mechanism, not a reporting nicety.** With no
exploration the propensity-weighted estimator reports a false-negative rate of
exactly zero, because it structurally cannot observe a miss. The controller
concludes it is perfect, ratchets the threshold up, and converges on referring
almost nobody. Removing exploration does not degrade this system gracefully;
it makes it diverge.

### Why exploration is allocated per stratum

An earlier version spread the quota uniformly across a score band just below
the threshold. Measured on `ranking_drift`, that fails for a specific and
instructive reason:

* A stratum the model has learned to under-score is pushed *far* below the
  threshold, not just under it. It never enters a band defined in score
  terms, so the band never probes it.
* The quota therefore lands on whichever strata happen to sit near the
  threshold -- which are the ones the model already scores correctly, and
  which have nothing left to teach.
* Measured: the drifted stratum received 36 exploratory referrals in 200 days
  (0.18 a day) while a perfectly calibrated stratum received 118. The
  estimator fired essentially never.

Exploration is a scarce physical resource, so it is spent where the ignorance
is. Each stratum's share of the quota is proportional to its **information
deficit** -- how far its banked evidence falls short of what is needed to
update it -- and within a stratum the share is spread across that stratum's
own expected remaining arrivals, so it is consumed evenly over the day rather
than in the first hour.

A stratum whose calibration is already well evidenced drops to the global
positivity floor. A starved one is probed hard until it is not.
"""

import numpy as np

P_FLOOR = 0.002          # global positivity floor: never zero, anywhere
EXPLORE_FRAC = 0.005      # share of the daily budget funding exploration
P_MAX = 0.5              # no sub-threshold patient is referred more than half
                         # the time; keeps IPW weights away from 1/p blow-up


class Explorer:
    """Assigns a referral probability to every patient. Never zero."""

    def __init__(self, n_strata: int, explore_frac: float = EXPLORE_FRAC,
                 p_floor: float = P_FLOOR, p_max: float = P_MAX):
        if not (0.0 <= explore_frac <= 1.0):
            raise ValueError("explore_frac must be in [0, 1]")
        if not (0.0 < p_floor <= p_max <= 1.0):
            raise ValueError("require 0 < p_floor <= p_max <= 1")
        if n_strata < 1:
            raise ValueError("n_strata must be positive")
        self.n_strata = n_strata
        self.explore_frac = explore_frac
        self.p_floor = p_floor
        self.p_max = p_max
        self.quota = np.zeros(n_strata)
        self.spend = 0

    def start_day(self, budget: int, deficits=None) -> None:
        """Split the day's exploration budget across strata by information
        deficit. With no deficits supplied, split it evenly."""
        total = self.explore_frac * budget
        if deficits is None:
            self.quota = np.full(self.n_strata, total / self.n_strata)
            return
        d = np.clip(np.asarray(deficits, dtype=float), 0.0, 1.0)
        s = d.sum()
        self.quota = (np.full(self.n_strata, total / self.n_strata)
                      if s <= 0 else total * d / s)

    def propensity(self, score: float, tau: float, stratum: int,
                   expected_remaining: float) -> float:
        """Referral probability for one patient. Always in (0, 1].

        Above the threshold the patient is referred outright. Below it, this
        stratum's remaining quota is spread across the arrivals still expected
        from that stratum today -- so a starved stratum is probed hard and a
        well-evidenced one falls back to the floor.
        """
        if score > tau:
            return 1.0
        q = self.quota[stratum]
        if q <= 0.0:
            return self.p_floor
        p = q / max(1.0, expected_remaining)
        return float(np.clip(p, self.p_floor, self.p_max))

    def charge(self, stratum: int) -> None:
        """Record that an exploratory (sub-threshold) referral was made."""
        self.quota[stratum] -= 1.0
        self.spend += 1

    @property
    def state_bytes(self) -> int:
        return self.quota.nbytes + 5 * 8
