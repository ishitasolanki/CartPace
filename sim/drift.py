"""How the world moves between days.

Two kinds of drift, and the distinction is the whole point of the project.

Prevalence drift changes how many cases there are. It moves every score in the
same direction, so the *ranking* is untouched. A quantile-based pacer adapts to
it for free, without learning anything.

Ranking drift changes how well the frozen model scores one subpopulation. The
model's output for that stratum is depressed while its true risk is unchanged,
so the ranking becomes wrong. No quantile method can fix this, because the
information needed is not in the score distribution -- it is in the labels.
"""

import numpy as np

from .scenarios import Scenario


def prevalence(cfg: Scenario, day: int, stratum: int) -> float:
    """True case rate for a stratum on a given day.

    Seasonal component is shared across strata (ranking-preserving); the
    stratum multiplier is fixed.
    """
    base = cfg.base_prevalence
    if cfg.prev_drift_amp:
        base += cfg.prev_drift_amp * np.sin(2.0 * np.pi * day / cfg.prev_drift_period)
    p = base * cfg.stratum_risk[stratum]
    return float(np.clip(p, 0.005, 0.6))


def rank_offset(cfg: Scenario, day: int, stratum: int) -> float:
    """Logit units by which the frozen model *under-scores* this stratum today.

    Zero everywhere unless ranking drift is enabled for this stratum. Grows
    linearly then saturates, which is what progressive population shift away
    from a model's training distribution looks like.

    The controller's per-stratum offset should converge to this value. That
    makes it directly checkable: the simulator knows the right answer.
    """
    if stratum != cfg.rank_drift_stratum or cfg.rank_drift_rate <= 0.0:
        return 0.0
    return float(min(cfg.rank_drift_rate * day, cfg.rank_drift_max))
