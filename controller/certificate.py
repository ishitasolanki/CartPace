"""False-negative certificate: what fraction of cases did we miss?

This is the estimand that genuinely needs exploration, and it is a different
kind of quantity from the per-stratum offsets.

The offsets are a **conditional** property -- `E[y | s, k] = s` -- and selection
into the referred set depends only on the score and the stratum, so they can be
estimated from referred patients with no propensity correction at all
(`recalibrate.py` explains why). The false-negative rate is a **marginal**
quantity over patients who were *never referred*, whose labels are never
observed by anyone. Nothing about the referred set identifies it.

    FNR = E[y * (1 - referred)] / E[y]

Take the expectation over the referral draw. A patient referred with
probability `p` contributes `y * (1 - p)` to the numerator in expectation, so
the Horvitz-Thompson estimator over the referred sample is

    FNR_hat = sum_referred[ y * (1 - p) / p ]  /  sum_referred[ y / p ]

**Read what happens when exploration is switched off.** Then every referral has
`p = 1`, every numerator term is `y * 0 = 0`, and the estimate is exactly zero
-- not noisy, not wide, but confidently and precisely wrong. The estimator
cannot observe a miss because nothing that could have been a miss was ever
tested. A controller that believed it would conclude it is performing perfectly.

That is the sense in which exploration is load-bearing rather than decorative,
and it is why the honest home for the exploration-funding claim is the
certificate rather than case-finding throughput: P2 measured exploration as a
net cost to cases caught, but the certificate does not exist without it.

The certificate is **reported, never enforced**. When the budget cannot support
the target false-negative rate, the correct output is a certificate that visibly
degrades, not a system that pretends the target is met.
"""

import numpy as np


class FNRCertificate:
    """Streaming Horvitz-Thompson estimate of the false-negative rate.

    Constant memory: six accumulators regardless of how many patients are seen.
    """

    def __init__(self, p_floor: float = 0.002, ess_min: float = 20.0):
        if not (0.0 < p_floor <= 1.0):
            raise ValueError("p_floor must be in (0, 1]")
        self.p_floor = p_floor
        self.ess_min = ess_min
        self._num = 0.0       # sum y (1-p)/p   -- expected missed cases
        self._den = 0.0       # sum y / p       -- expected total cases
        self._num2 = 0.0      # sum of squared numerator terms, for variance
        self._den2 = 0.0
        self._w = 0.0         # sum of case weights, for effective sample size
        self._w2 = 0.0

    def observe(self, batch) -> None:
        """Fold in delayed confirmatory results.

        Only cases (`label == 1`) carry information about the case rate; a
        confirmed negative tells you nothing about how many cases were missed.
        """
        for f in batch:
            if not f.label:
                continue
            p = min(max(f.propensity, self.p_floor), 1.0)
            inv = 1.0 / p
            miss = (1.0 - p) * inv
            self._num += miss
            self._den += inv
            self._num2 += miss * miss
            self._den2 += inv * inv
            self._w += inv
            self._w2 += inv * inv

    @property
    def ess(self) -> float:
        """Effective number of observed cases behind the estimate."""
        return (self._w ** 2 / self._w2) if self._w2 > 0 else 0.0

    def estimate(self) -> tuple[float, float]:
        """Return `(fnr_hat, halfwidth)`.

        The halfwidth is a delta-method approximation for a ratio of two
        correlated sums, at roughly 95%. It is an approximation and is reported
        as such -- with heavy inverse-propensity weights the sampling
        distribution is skewed, so this understates the tail. It is adequate for
        showing the certificate degrade on a dashboard; it is not a
        distribution-free bound, and the specification should not claim one
        until it is.
        """
        if self._den <= 0.0 or self.ess < self.ess_min:
            return float("nan"), float("nan")
        r = self._num / self._den
        # Var(N/D) ~= (1/D^2) Var(N) + (N^2/D^4) Var(D) - 2 (N/D^3) Cov(N,D)
        # Cov is bounded by the product of standard deviations; using that bound
        # keeps the interval conservative rather than optimistic.
        var_n = max(self._num2 - self._num ** 2 / max(self.ess, 1.0), 0.0)
        var_d = max(self._den2 - self._den ** 2 / max(self.ess, 1.0), 0.0)
        v = (var_n / self._den ** 2
             + (self._num ** 2) * var_d / self._den ** 4
             + 2.0 * self._num * np.sqrt(var_n * var_d) / self._den ** 3)
        return float(np.clip(r, 0.0, 1.0)), float(1.96 * np.sqrt(max(v, 0.0)))

    @property
    def identifiable(self) -> bool:
        """False when no sub-threshold patient was ever referred.

        In that state the estimator returns exactly zero for any input, which
        is indistinguishable from genuinely perfect performance. Surfacing it
        as a flag is the difference between a degraded certificate and a
        silently false one.
        """
        return self._num > 0.0

    @property
    def state_bytes(self) -> int:
        return 8 * 8
