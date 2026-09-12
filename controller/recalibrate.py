"""Per-stratum recalibration of a frozen model from censored, delayed feedback.

**This is the contribution.**

A hard count budget fixes *how many* referrals happen. The only freedom left is
*which* patients get them -- and with a single monotone score there is none,
because the optimal within-day policy is just top-B by score. Unless the
model's *ranking* is wrong for some subpopulation. Then there is, and censored
feedback can find it.

The correction is one scalar per stratum, applied in logit space:

    s_tilde = sigmoid( logit(s) + d_k )

Logit space keeps the result a valid probability without clipping and makes the
correction a proper monotone recalibration map rather than an arbitrary shift.

If the frozen model systematically under-scores a stratum -- a CNN undertrained
on HIV-positive or paediatric chest X-rays is the real case -- pacing on the raw
score puts that whole stratum below threshold, so it never gets referred, so it
never generates labels, so nothing ever corrects it. The exploration floor
breaks that loop: a trickle is referred anyway, the propensity-weighted
estimate shows the true case rate exceeds the model's claim, the offset rises,
and the stratum re-enters the referred set -- displacing a lower-value referral
elsewhere. Total referrals are unchanged; the *composition* changes.

With no drift the estimate agrees with the model, the offsets converge to zero,
and the controller degenerates exactly to pure pacing.

### Both sides of the comparison are propensity-weighted

The specification originally compared the propensity-weighted case rate against
"the mean predicted probability for the stratum". Read literally that is
biased: labels arrive only for referred patients, who are overwhelmingly high
scorers, so a plain batch mean of scores is a *sample* quantity while the
weighted case rate is a *population* estimate. Both sides are therefore
Horvitz-Thompson estimates over the same weighted sample.

### Why evidence is accumulated rather than consumed per batch

An earlier version stepped once per daily batch behind an effective-sample-size
floor of 3. That floor is far too permissive and produced a **one-sided
ratchet** that drove low-prevalence strata steadily negative:

* Floor-propensity referrals carry weight 1/p_floor each, so three of them
  already register ESS = 3 -- three actual patients.
* At 5% prevalence, 86% of three-patient batches contain **no cases at all**.
* Zero cases gives phat = 0, whose logit is clipped to -6.9 against a model
  claim near -2.9, a gap of -4 that pins the step at its negative limit.
* Nothing symmetric pushes back, because a batch cannot contain fewer than
  zero cases. Every case-free batch ratchets the offset down.

The fix is not a bigger floor alone -- that would discard the evidence instead
of using it. Sufficient statistics are accumulated per stratum across days and
the step fires only once enough evidence exists, then resets. Memory stays
O(1): four scalars per stratum regardless of how long the clinic runs.

Two further guards: the case rate is shrunk toward the model's own claim by a
small pseudo-count, so a thin batch moves the offset a little rather than a
lot; and the update is proportional control toward a target offset rather than
an unbounded gradient, so it cannot run away.
"""

import numpy as np

from .explore import P_FLOOR

_EPS = 1e-4


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


class StratumCalibrator:
    """K scalar offsets, learned online from propensity-weighted labels."""

    def __init__(self, n_strata: int, gamma: float = 0.3, clip: float = 3.0,
                 ess_min: float = 80.0, p_floor: float = P_FLOOR,
                 max_step: float = 0.35, jeffreys: float = 0.5,
                 w_cap: float = 0.0, explore_only: bool = False,
                 weighting: str = "none"):
        if n_strata < 1:
            raise ValueError("n_strata must be positive")
        if not (0.0 < p_floor <= 1.0):
            raise ValueError("p_floor must be in (0, 1]")
        if ess_min <= 0:
            raise ValueError("ess_min must be positive")
        self.n_strata = n_strata
        self.gamma = gamma
        self.clip = clip
        self.ess_min = ess_min
        self.p_floor = p_floor
        self.max_step = max_step
        self.jeffreys = jeffreys
        # Weight cap. Inverse-propensity weights span 1 (referred outright) to
        # 1/p_floor (=250), and a single 250 crushes the effective sample size
        # of an otherwise healthy batch from 80 to 1.7 -- risk R3, exactly as
        # specified. Capping trades a little bias for a lot of variance, which
        # is the right trade here because the quantity used is a *contrast*
        # between two estimates over the same weighted sample: a cap biases
        # both sides in the same direction and largely cancels.
        # 0 means "no cap beyond the 1/p_floor clip".
        self.w_cap = w_cap if w_cap > 0 else 1.0 / p_floor
        # Restrict learning to sub-threshold referrals. Above-threshold
        # patients are referred regardless, so they carry no information about
        # where the line should be; the marginal patients just below it do.
        self.explore_only = explore_only
        if weighting not in ("none", "ipw"):
            raise ValueError("weighting must be 'none' or 'ipw'")
        # Default is *unweighted*, and the reason is worth stating precisely.
        #
        # Calibration is a CONDITIONAL property: E[y | s, k] = s. Selection
        # into the referred set depends only on the corrected score, the
        # stratum and the clock -- that is, only on the variables being
        # conditioned on. Conditioning on selection therefore does not bias a
        # calibration estimate, and no inverse-propensity correction is needed
        # for this quantity. Measured on synthetic data with a true offset of
        # 1.20: estimating on the top 5% of scores alone recovers 1.16.
        #
        # This matters because IPW was actively harmful here. Weights span 1 to
        # 1/p_floor = 250, and a single floor-propensity referral drops the
        # effective sample size of an 80-patient batch to 1.7, so the update
        # essentially never fired. Unweighted, the effective sample size is
        # just the number of referrals, which is plentiful.
        #
        # Inverse-propensity weighting is still required for the false-negative
        # certificate, which is a *marginal* quantity over patients who were
        # never referred. That is a different estimand and keeps exploration
        # load-bearing; see policy.py.
        self.weighting = weighting

        self._d = np.zeros(n_strata, dtype=float)
        self._updates = np.zeros(n_strata, dtype=int)
        # Accumulated sufficient statistics. Offset-independent by
        # construction, so they stay valid while d_k moves underneath them.
        self._sw = np.zeros(n_strata)     # sum of weights
        self._sw2 = np.zeros(n_strata)    # sum of squared weights -> ESS
        self._swy = np.zeros(n_strata)    # weighted cases
        self._sws = np.zeros(n_strata)    # weighted raw score

    # --- applying the correction ------------------------------------------

    def correct(self, score: float, stratum: int) -> float:
        """The corrected score the rest of the controller acts on."""
        return float(sigmoid(logit(score) + self._d[stratum]))

    # --- learning it -------------------------------------------------------

    def update(self, batch) -> None:
        """Fold delayed confirmatory results into the accumulators, and step
        any stratum that has now gathered enough evidence.

        `batch` items carry `stratum`, `propensity` (as at referral), `score`
        (raw) and `label`.
        """
        for f in batch:
            if self.explore_only and f.propensity >= 1.0:
                continue
            k = f.stratum
            # Clipped inverse-propensity weight. Clipping bounds the variance a
            # single rare exploratory referral can inject (risk R3).
            if self.weighting == "ipw":
                w = min(1.0 / max(f.propensity, self.p_floor), self.w_cap)
            else:
                w = 1.0
            self._sw[k] += w
            self._sw2[k] += w * w
            self._swy[k] += w * f.label
            self._sws[k] += w * f.score

        for k in range(self.n_strata):
            if self._sw2[k] <= 0.0:
                continue
            ess = self._sw[k] ** 2 / self._sw2[k]
            if ess < self.ess_min:
                continue                      # keep accumulating, discard nothing

            sbar_raw = self._sws[k] / self._sw[k]        # population mean claim

            # Posterior mean of the case rate under a Jeffreys prior, on the
            # *effective* sample size rather than the raw weight total.
            #
            # Taking logit() of the raw weighted rate is what produced the
            # residual downward drift: logit is steeply convex near zero, so a
            # batch that happens to contain no cases yields an enormous
            # negative target while a batch with one extra case yields only a
            # small positive one. The asymmetry does not cancel. At ESS 40 and
            # 5% prevalence the expected step is -0.044 per update even when
            # the true offset is exactly zero; it is still -0.015 at ESS 200,
            # so more evidence alone does not fix it. Smoothing does: the same
            # calculation gives +0.004 here, and +0.0001 at 12% prevalence.
            n_eff = ess
            cases_eff = (self._swy[k] / self._sw[k]) * n_eff
            phat = ((cases_eff + self.jeffreys)
                    / (n_eff + 2.0 * self.jeffreys))

            # Offset that would make the corrected claim match the observed
            # rate. Proportional control toward it, rather than an unbounded
            # gradient, so a freak batch cannot send d_k flying.
            target = logit(phat) - logit(sbar_raw)
            step = float(np.clip(self.gamma * (target - self._d[k]),
                                 -self.max_step, self.max_step))
            self._d[k] = float(np.clip(self._d[k] + step, -self.clip, self.clip))
            self._updates[k] += 1
            self._reset(k)

    def _reset(self, k: int) -> None:
        self._sw[k] = self._sw2[k] = self._swy[k] = self._sws[k] = 0.0

    # --- introspection -----------------------------------------------------

    @property
    def offsets(self) -> np.ndarray:
        return self._d.copy()

    @property
    def ess(self) -> np.ndarray:
        """Evidence currently banked per stratum, not yet spent on a step."""
        with np.errstate(divide="ignore", invalid="ignore"):
            e = np.where(self._sw2 > 0, self._sw ** 2 / np.maximum(self._sw2, 1e-12), 0.0)
        return e

    def deficit(self) -> np.ndarray:
        """How far each stratum falls short of the evidence needed to update.

        1.0 means nothing banked, 0.0 means ready to step. This is what steers
        the exploration budget: probe where the ignorance is, not where the
        patients happen to be.
        """
        return np.clip(1.0 - self.ess / self.ess_min, 0.0, 1.0)

    @property
    def updates(self) -> np.ndarray:
        """Times each stratum has actually stepped. A stratum that never
        gathers enough evidence sits at its last value -- intended behaviour
        under starvation, not a failure."""
        return self._updates.copy()

    @property
    def state_bytes(self) -> int:
        arrays = (self._d, self._updates, self._sw, self._sw2, self._swy, self._sws)
        return sum(a.nbytes for a in arrays) + 7 * 8
