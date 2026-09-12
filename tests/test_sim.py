"""Tests for the synthetic world.

The simulator is the measuring instrument for the whole project. If it is
wrong, every downstream result is wrong in a way no amount of controller
testing would reveal, so it gets checked against its own definition rather
than against intuition.
"""

import numpy as np
import pytest

from sim import arrivals, drift, scenarios
from sim.labels import DelayedLabels, Feedback


def auc(scores, labels):
    """Rank-statistic AUC. No sklearn dependency."""
    r = np.argsort(np.argsort(scores)) + 1
    n1, n0 = labels.sum(), (1 - labels).sum()
    assert n1 and n0, "need both classes"
    return (r[labels == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


# --- reproducibility (NFR4) ------------------------------------------------


def test_same_seed_gives_identical_days():
    cfg = scenarios.get("volatile")
    a = arrivals.make_days(cfg, 10, seed=7)
    b = arrivals.make_days(cfg, 10, seed=7)
    for x, y in zip(a, b):
        assert np.array_equal(x.scores, y.scores)
        assert np.array_equal(x.labels, y.labels)
        assert np.array_equal(x.strata, y.strata)
        assert x.budget == y.budget


def test_different_seed_gives_different_days():
    cfg = scenarios.get("calm")
    a = arrivals.make_days(cfg, 10, seed=1)
    b = arrivals.make_days(cfg, 10, seed=2)
    assert not np.array_equal(a[0].scores, b[0].scores)


# --- the model is calibrated when it is not drifting -----------------------


def test_model_is_calibrated_without_drift():
    """Absent ranking drift, score == true risk, so mean score == case rate.

    This is what makes "the correct offset is zero" a sharp claim.
    """
    cfg = scenarios.get("calm")
    days = arrivals.make_days(cfg, 80, seed=3)
    s = np.concatenate([d.scores for d in days])
    y = np.concatenate([d.labels for d in days])
    assert abs(s.mean() - y.mean()) < 0.01, "model should be calibrated in calm"


def test_calm_scores_equal_risks():
    cfg = scenarios.get("calm")
    d = arrivals.make_days(cfg, 1, seed=4)[0]
    assert np.allclose(d.scores, d.risks)


def test_auc_is_realistic():
    """~0.87 matches published TB chest X-ray AI. Guards against a simulator
    so easy or so hard that controller differences cannot show up."""
    cfg = scenarios.get("calm")
    days = arrivals.make_days(cfg, 80, seed=5)
    s = np.concatenate([d.scores for d in days])
    y = np.concatenate([d.labels for d in days])
    assert 0.83 < auc(s, y) < 0.92


def test_prevalence_is_in_phc_range():
    cfg = scenarios.get("calm")
    days = arrivals.make_days(cfg, 80, seed=6)
    y = np.concatenate([d.labels for d in days])
    assert 0.08 < y.mean() < 0.17


# --- drift behaves as specified -------------------------------------------


def test_calm_has_no_offsets():
    cfg = scenarios.get("calm")
    for d in arrivals.make_days(cfg, 20, seed=8):
        assert np.all(d.true_offsets == 0.0)


def test_prevalence_drift_preserves_calibration():
    """Prevalence drift moves how many cases there are, not how they rank.

    The model stays calibrated, so the correct per-stratum offset is still
    zero -- which is exactly why a quantile pacer handles this for free and
    recalibration has nothing to contribute here.
    """
    cfg = scenarios.get("prevalence_drift")
    days = arrivals.make_days(cfg, 120, seed=9)
    for d in days:
        assert np.all(d.true_offsets == 0.0)
    s = np.concatenate([d.scores for d in days])
    y = np.concatenate([d.labels for d in days])
    assert abs(s.mean() - y.mean()) < 0.01


def test_prevalence_drift_actually_moves_prevalence():
    cfg = scenarios.get("prevalence_drift")
    days = arrivals.make_days(cfg, 120, seed=10)
    rate = [d.labels.mean() for d in days]
    early = np.mean(rate[:15])
    peak = max(np.mean(rate[i:i + 15]) for i in range(0, 105, 5))
    assert peak - early > 0.02, "seasonal drift should be visible"


def test_ranking_drift_depresses_only_the_target_stratum():
    cfg = scenarios.get("ranking_drift")
    k = cfg.rank_drift_stratum
    d = arrivals.make_days(cfg, 60, seed=11)[-1]   # late day, drift saturated

    target = d.strata == k
    # Scores for the drifted stratum are below their true risk.
    assert np.all(d.scores[target] < d.risks[target])
    # Everyone else is untouched.
    assert np.allclose(d.scores[~target], d.risks[~target])


def test_ranking_drift_grows_then_saturates():
    cfg = scenarios.get("ranking_drift")
    k = cfg.rank_drift_stratum
    off = [drift.rank_offset(cfg, t, k) for t in range(200)]
    assert off[0] == 0.0
    assert off[10] < off[30] < off[50]
    assert max(off) == pytest.approx(cfg.rank_drift_max)
    assert all(b >= a for a, b in zip(off, off[1:])), "must be monotone"


def test_true_offsets_match_drift_function():
    """The simulator publishes the answer the controller has to find."""
    cfg = scenarios.get("ranking_drift")
    for t in (0, 15, 40, 90):
        d = arrivals.make_day(cfg, t, np.random.default_rng(t))
        for k in range(scenarios.N_STRATA):
            assert d.true_offsets[k] == pytest.approx(drift.rank_offset(cfg, t, k))


def test_ranking_drift_breaks_calibration_for_target_stratum():
    """The drifted stratum is under-scored: the model claims less risk than
    is really there. That gap is what recalibration has to close."""
    cfg = scenarios.get("ranking_drift")
    k = cfg.rank_drift_stratum
    days = arrivals.make_days(cfg, 120, seed=12)[60:]   # after drift has bitten
    s = np.concatenate([d.scores[d.strata == k] for d in days])
    y = np.concatenate([d.labels[d.strata == k] for d in days])
    assert s.mean() < y.mean() - 0.02, "target stratum should be under-scored"


# --- budget and volume -----------------------------------------------------


def test_shortage_days_appear_at_roughly_the_configured_rate():
    cfg = scenarios.get("shortage")
    days = arrivals.make_days(cfg, 400, seed=13)
    short = np.mean([d.budget == cfg.shortage_budget for d in days])
    assert abs(short - cfg.shortage_prob) < 0.06


def test_no_shortage_when_disabled():
    cfg = scenarios.get("calm")
    assert all(d.budget == cfg.budget for d in arrivals.make_days(cfg, 50, seed=14))


def test_arrivals_are_sorted_and_within_the_day():
    cfg = scenarios.get("calm")
    for d in arrivals.make_days(cfg, 10, seed=15):
        assert np.all(np.diff(d.times) >= 0)
        assert d.times.min() >= 0.0
        assert d.times.max() <= cfg.day_hours
        assert len(d.times) == len(d.strata) == len(d.labels) == len(d.scores)


def test_arrivals_are_morning_weighted():
    """Morning loading is what makes unpaced greedy exhaust the budget early."""
    cfg = scenarios.get("calm")
    t = np.concatenate([d.times for d in arrivals.make_days(cfg, 30, seed=16)])
    assert (t < cfg.day_hours / 2).mean() > 0.55


def test_scenario_rejects_bad_config():
    with pytest.raises(AssertionError):
        scenarios.Scenario(name="bad", stratum_probs=(0.5, 0.5))


def test_unknown_scenario_raises():
    with pytest.raises(KeyError):
        scenarios.get("no_such_scenario")


# --- delayed censored feedback --------------------------------------------


def test_labels_arrive_only_after_the_delay():
    q = DelayedLabels(delay=3)
    q.record(stratum=0, propensity=1.0, score=0.9, label=1)
    assert q.end_day() == []      # day 0
    assert q.end_day() == []      # day 1
    assert q.end_day() == []      # day 2
    batch = q.end_day()           # day 3 -- day 0's referrals land
    assert len(batch) == 1
    assert batch[0].label == 1


def test_propensity_travels_with_the_label():
    """The bug this module exists to prevent.

    A label must carry the propensity in force when it was referred, not a
    later one. Two referrals at different propensities must come back with
    their own values.
    """
    q = DelayedLabels(delay=1)
    q.record(stratum=2, propensity=1.0, score=0.8, label=1)
    q.record(stratum=2, propensity=0.05, score=0.2, label=0)
    q.end_day()
    batch = q.end_day()
    assert sorted(f.propensity for f in batch) == [0.05, 1.0]


def test_feedback_is_immutable():
    f = Feedback(stratum=1, propensity=0.5, score=0.4, label=1)
    with pytest.raises(Exception):
        f.propensity = 0.9


def test_zero_propensity_is_rejected():
    """Positivity is not optional: a zero propensity makes IPW undefined."""
    with pytest.raises(ValueError):
        Feedback(stratum=0, propensity=0.0, score=0.1, label=0)


def test_propensity_above_one_is_rejected():
    with pytest.raises(ValueError):
        Feedback(stratum=0, propensity=1.5, score=0.1, label=0)


def test_bad_label_is_rejected():
    with pytest.raises(ValueError):
        Feedback(stratum=0, propensity=0.5, score=0.1, label=2)


def test_zero_delay_returns_same_day():
    q = DelayedLabels(delay=0)
    q.record(stratum=0, propensity=1.0, score=0.7, label=1)
    assert len(q.end_day()) == 1


def test_negative_delay_rejected():
    with pytest.raises(ValueError):
        DelayedLabels(delay=-1)


def test_pending_is_bounded_by_delay():
    """Memory in flight must not grow with the number of days run (NFR1)."""
    q = DelayedLabels(delay=3)
    seen = []
    for _ in range(200):
        for _ in range(40):
            q.record(stratum=0, propensity=1.0, score=0.5, label=0)
        q.end_day()
        seen.append(q.pending)
    assert max(seen) <= 4 * 40
