"""Named simulation scenarios.

A Scenario is the complete description of a synthetic world: how many people
arrive, how sick they are, how the frozen model behaves, and how both drift.

The scenario that matters is `ranking_drift`. Prevalence drift preserves the
score ranking, and budget pacing is a quantile method, so pacing is already
invariant to it -- which is why an earlier simulator that drifted prevalence
only made the learned layer look useless. Ranking drift is the regime where
recalibration has something to do.
"""

from dataclasses import dataclass

N_STRATA = 6
DAY_HOURS = 8.0


@dataclass(frozen=True)
class Scenario:
    """One synthetic world. Frozen so a scenario cannot be mutated mid-run."""

    name: str

    # Volume
    n_mean: int = 200
    n_sd: int = 40

    # Budget
    budget: int = 40
    shortage_budget: int = 25
    shortage_prob: float = 0.0

    # Risk. stratum_risk multiplies base prevalence, so strata differ in how
    # sick they are as well as how common they are.
    # Location parameter, not the realised rate. Risk is logit-normal, so
    # Jensen's inequality lifts the realised prevalence well above this:
    # 0.05 here yields ~12% realised, which is the PHC screening range.
    base_prevalence: float = 0.05
    stratum_probs: tuple = (0.30, 0.22, 0.18, 0.14, 0.10, 0.06)
    stratum_risk: tuple = (0.6, 0.8, 1.0, 1.2, 1.6, 2.2)

    # Spread of individual risk in logit space. Controls model AUC:
    # wider spread separates cases from non-cases more.
    spread: float = 1.9

    # Prevalence drift: seasonal, ranking-preserving.
    prev_drift_amp: float = 0.0
    prev_drift_period: float = 60.0

    # Ranking drift: the frozen model progressively under-scores one stratum
    # while that stratum's true risk is unchanged. This is the failure mode a
    # CNN undertrained on a subpopulation actually exhibits.
    rank_drift_stratum: int = -1          # -1 disables
    rank_drift_rate: float = 0.0          # logit units per day
    rank_drift_max: float = 0.0           # saturation

    # Feedback
    delay: int = 3                        # days until confirmatory result

    day_hours: float = DAY_HOURS

    def __post_init__(self):
        assert len(self.stratum_probs) == N_STRATA
        assert len(self.stratum_risk) == N_STRATA
        assert abs(sum(self.stratum_probs) - 1.0) < 1e-9, "stratum_probs must sum to 1"
        assert 0.0 <= self.shortage_prob <= 1.0
        assert self.delay >= 0


_BASE = dict(n_mean=200, n_sd=40, budget=40, shortage_budget=25, delay=3)

SCENARIOS = {
    # No drift, steady volume and budget. Recalibration should find nothing to
    # do and degenerate to pure pacing.
    "calm": Scenario(name="calm", **_BASE),

    # Seasonal prevalence, ranking intact. Pacing handles this on its own.
    "prevalence_drift": Scenario(
        name="prevalence_drift", prev_drift_amp=0.025, prev_drift_period=60.0, **_BASE),

    # The gate scenario. The model's ranking degrades on stratum 4 -- a
    # high-risk, low-prevalence group, which is the painful case: pacing on the
    # raw score pushes it below threshold and it then generates no labels.
    "ranking_drift": Scenario(
        name="ranking_drift", rank_drift_stratum=4,
        rank_drift_rate=0.035, rank_drift_max=2.0, **_BASE),

    # Supply shocks. Pacing matters most; recalibration should not regress.
    "shortage": Scenario(name="shortage", shortage_prob=0.25, **_BASE),

    # Everything at once.
    "volatile": Scenario(
        name="volatile", shortage_prob=0.20,
        prev_drift_amp=0.025, prev_drift_period=45.0,
        rank_drift_stratum=4, rank_drift_rate=0.05, rank_drift_max=2.5, **_BASE),
}


def get(name: str) -> Scenario:
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; have {sorted(SCENARIOS)}")
    return SCENARIOS[name]
