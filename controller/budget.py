"""Budget pacing: spend the day's cartridges evenly across the day's arrivals.

The threshold is the score quantile that exactly exhausts the remaining budget
over the arrivals still expected. Two things make this work in a real clinic.

**Pace against the clock, not against history.** An earlier design estimated
today's volume from a historical average. That hoards: on a busy day you
exhaust the budget early and the loss is capped by the budget itself, but on a
quiet day you close with cartridges unused and that loss is unbounded. The
asymmetry produces systematic under-spending. A clinic can always see the
clock, so today's volume is re-estimated from today's own arrival rate and
self-corrects within the day.

**Bound the memory.** The score distribution is tracked by a fixed-size ring
buffer of recent scores, so state does not grow with patients seen (NFR1).
Being a *recent* window rather than a full history is a feature under drift:
it forgets the old distribution without being told to.
"""

import numpy as np

DAY_HOURS = 8.0
_MIN_ELAPSED = 0.05      # before this, the arrival-rate estimate is too noisy
_VOLUME_MEMORY = 30      # days of history folded into the volume prior
_RESORT_EVERY = 16       # re-sort the sketch at most this often (see tau_at)


class BudgetPacer:
    """Clock-driven rate control over a bounded quantile sketch."""

    def __init__(self, sketch_size: int = 512, day_hours: float = DAY_HOURS,
                 n_prior: float = 200.0):
        if sketch_size < 1:
            raise ValueError("sketch_size must be positive")
        if day_hours <= 0:
            raise ValueError("day_hours must be positive")
        # ponytail: ring buffer + np.quantile, not a t-digest. O(sketch_size)
        # per decision is microseconds at 512 and the memory is flat, which is
        # what the claim needs. Swap in a proper sketch only if profiling says
        # the quantile call is actually hot.
        self._sketch = np.zeros(sketch_size, dtype=float)
        self._write = 0
        self._filled = 0
        self._sorted = None      # cached ascending view of the filled sketch
        self._stale = 0
        self.day_hours = day_hours
        self.n_est = float(n_prior)      # running estimate of daily volume
        self._days_seen = 0
        self.seen = 0                    # arrivals so far today

    # --- lifecycle ---------------------------------------------------------

    def start_day(self) -> None:
        self.seen = 0

    def observe(self, score: float) -> None:
        """Record a score into the sketch. Call once per arrival, before
        asking for the threshold, so today's arrival is counted."""
        self._sketch[self._write] = score
        self._write = (self._write + 1) % len(self._sketch)
        self._filled = min(self._filled + 1, len(self._sketch))
        self._stale += 1
        self.seen += 1

    def end_day(self, n_actual: int) -> None:
        """Fold the day's realised volume into the prior for future days."""
        self._days_seen += 1
        step = min(self._days_seen, _VOLUME_MEMORY)
        self.n_est += (n_actual - self.n_est) / step

    # --- the threshold -----------------------------------------------------

    def expected_total(self, t: float) -> float:
        """Estimate of today's total arrivals, given the clock reads `t` hours.

        Convex combination of today's own extrapolation (`seen / elapsed`) and
        the historical prior, weighted by how much of the day has passed. Early
        on the prior dominates; by close, today's count does.
        """
        elapsed = float(np.clip(t / self.day_hours, _MIN_ELAPSED, 1.0))
        today = self.seen / elapsed
        return elapsed * today + (1.0 - elapsed) * self.n_est

    def remaining(self, t: float) -> float:
        """Arrivals still expected after the one just observed."""
        return max(1.0, self.expected_total(t) - self.seen)

    def afford(self, budget_left: int, t: float) -> float:
        """Fraction of the remaining arrivals the remaining budget can cover."""
        if budget_left <= 0:
            return 0.0
        return float(min(1.0, budget_left / self.remaining(t)))

    def tau_at(self, afford: float) -> float:
        """Threshold that refers the top `afford` fraction of recent scores.

        Exposed separately from `tau_for` so the explorer can ask for the
        threshold a little further down the distribution, which is what makes
        the exploration band a *quantile* width rather than an absolute score
        width. Scores here cluster near 0.12, so a fixed band in score units
        would swallow most of the distribution.
        """
        if afford <= 0.0:
            return np.inf                       # nothing left; refer no one
        if self._filled == 0:
            return 0.0                          # no history yet; do not block
        q = float(np.clip(1.0 - afford, 0.0, 1.0))
        return self._quantile(q)

    def _quantile(self, q: float) -> float:
        """Linear-interpolated quantile from a cached sort of the sketch.

        `np.quantile` costs ~50us of Python and NumPy overhead, and a decision
        needs two of them (the threshold, and the bottom of the exploration
        band). At 200 arrivals a day that dominated everything else and put the
        per-decision latency two orders of magnitude above the microsecond
        budget in NFR2.

        # ponytail: the sort is reused for up to _RESORT_EVERY arrivals. One
        # patient moves a 512-sample distribution by ~0.2%, far less than the
        # sampling noise already in the sketch, so the staleness is immaterial
        # next to what it buys. Drop the interval if a scenario ever pushes the
        # distribution faster than that.
        """
        if self._sorted is None or self._stale >= _RESORT_EVERY:
            self._sorted = np.sort(self._sketch[:self._filled])
            self._stale = 0
        a = self._sorted
        pos = q * (len(a) - 1)
        lo = int(pos)
        if lo >= len(a) - 1:
            return float(a[-1])
        frac = pos - lo
        return float(a[lo] + frac * (a[lo + 1] - a[lo]))

    def tau_for(self, budget_left: int, t: float) -> float:
        """Score threshold that spends `budget_left` evenly over the rest of
        the day."""
        return self.tau_at(self.afford(budget_left, t))

    # --- introspection -----------------------------------------------------

    @property
    def state_bytes(self) -> int:
        """Bytes of state, for the O(1) memory claim (NFR1)."""
        return self._sketch.nbytes + 5 * 8
