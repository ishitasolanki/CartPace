"""Delayed, censored confirmatory feedback.

Confirmatory results come back days later, and **only for patients who were
referred**. The controller never learns what it missed, except through the
patients it deliberately explored.

This module exists mostly to make one specific bug impossible to write. The
propensity that produced a referral must travel with that referral's label; if
the controller instead looks up "the propensity I would assign now", every
downstream estimate is silently wrong and nothing raises an error. So the
propensity is captured into a frozen record at the moment of referral and is
never recomputed. See the build specification, Phase 7, integration point 1.
"""

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Feedback:
    """One confirmatory result, carrying the propensity that produced it.

    Frozen on purpose: once a referral happens, its propensity is history and
    must not be edited by anything downstream.
    """

    stratum: int
    propensity: float      # probability of referral AT DECISION TIME, in (0, 1]
    score: float           # raw frozen-model score at decision time
    label: int             # 1 = confirmed case

    def __post_init__(self):
        if not (0.0 < self.propensity <= 1.0):
            raise ValueError(f"propensity must be in (0, 1], got {self.propensity}")
        if self.label not in (0, 1):
            raise ValueError(f"label must be 0 or 1, got {self.label}")


class DelayedLabels:
    """A fixed-length pipeline of pending confirmatory results.

    Memory is bounded by the delay, not by the number of patients seen, so this
    does not compromise the O(1) claim: at most `delay` days are ever in flight.
    """

    def __init__(self, delay: int):
        if delay < 0:
            raise ValueError("delay must be non-negative")
        self.delay = delay
        self._pipeline: deque[list[Feedback]] = deque()
        self._today: list[Feedback] = []

    def record(self, stratum: int, propensity: float, score: float, label: int) -> None:
        """Log a referral. Call only for patients actually referred."""
        self._today.append(Feedback(stratum, propensity, score, label))

    def end_day(self) -> list[Feedback]:
        """Close the day and return the batch that has finished its delay.

        Returns an empty list until `delay` days have elapsed.
        """
        self._pipeline.append(self._today)
        self._today = []
        if len(self._pipeline) > self.delay:
            return self._pipeline.popleft()
        return []

    @property
    def pending(self) -> int:
        """Referrals awaiting a result. Bounded by delay x daily budget."""
        return sum(len(b) for b in self._pipeline) + len(self._today)
