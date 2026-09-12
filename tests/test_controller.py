"""Controller tests.

Split into three kinds:

* **Invariants** that must hold for every policy on every stream. These are
  acceptance criteria, not nice-to-haves, and they are asserted on real runs.
* **Unit behaviour** of the pacer, explorer and calibrator in isolation, fed
  synthetic inputs so they are fast and deterministic.
* **Statistical** claims about the calibrator, which are the actual
  contribution and so are checked against a known ground truth rather than
  inferred from downstream case counts.
"""

import numpy as np
import pytest

from controller import baselines, metrics
from controller.budget import BudgetPacer
from controller.explore import Explorer
from controller.policy import BUDGET_EXHAUSTED, CartPaceController
from controller.recalibrate import StratumCalibrator, logit, sigmoid
from sim import arrivals, scenarios
from sim.labels import Feedback

ALL_SCENARIOS = ["calm", "prevalence_drift", "ranking_drift", "shortage", "volatile"]


def make_controller(seed=0, **kw):
    return CartPaceController(scenarios.N_STRATA, np.random.default_rng(seed), **kw)


# --- AC1: the budget invariant --------------------------------------------


@pytest.mark.parametrize("scn", ALL_SCENARIOS)
def test_budget_never_exceeded(scn):
    """FR3 is a hard physical constraint. metrics.run asserts it every day."""
    cfg = scenarios.get(scn)
    days = arrivals.make_days(cfg, 120, seed=2)
    metrics.run(make_controller(1), days, cfg.delay)


@pytest.mark.parametrize("policy_name", ["Fixed", "Greedy", "RandomUnderBudget",
                                         "ClockPacer"])
def test_baselines_respect_budget(policy_name):
    cfg = scenarios.get("volatile")
    days = arrivals.make_days(cfg, 100, seed=3)
    made = {
        "Fixed": lambda: baselines.Fixed(0.3),
        "Greedy": baselines.Greedy,
        "RandomUnderBudget": lambda: baselines.RandomUnderBudget(
            np.random.default_rng(0)),
        "ClockPacer": baselines.ClockPacer,
    }[policy_name]()
    metrics.run(made, days, cfg.delay)


def test_zero_budget_refers_nobody():
    c = make_controller()
    c.start_day(0)
    for i in range(50):
        d = c.decide(0.99, 0, 0.1 * i)
        assert not d.refer
        assert d.reason == BUDGET_EXHAUSTED


def test_budget_exhaustion_is_absorbing_within_a_day():
    """Once the budget is gone, no later arrival is referred however high its
    score.

    Scores are varied deliberately. With a constant score the pacer's
    threshold converges to that same value and nothing is *strictly* above it,
    so nobody is referred -- correct behaviour, but it exercises nothing.
    """
    rng = np.random.default_rng(0)
    c = make_controller()
    c.start_day(3)
    exhausted_at = None
    for i in range(400):
        score = float(rng.uniform(0.5, 1.0))
        d = c.decide(score, 0, 8.0 * i / 400)
        if exhausted_at is not None:
            assert not d.refer, "referred after the budget was exhausted"
            assert d.reason == BUDGET_EXHAUSTED
        if c.budget_left == 0 and exhausted_at is None:
            exhausted_at = i
    assert c.spent_today <= 3
    assert exhausted_at is not None, "budget should be spendable on good scores"


def test_negative_budget_rejected():
    with pytest.raises(ValueError):
        make_controller().start_day(-1)


# --- AC2: positivity -------------------------------------------------------


@pytest.mark.parametrize("scn", ALL_SCENARIOS)
def test_every_referral_carries_a_usable_propensity(scn):
    """Referrals must have propensity in (0, 1] or inverse-propensity
    weighting is undefined. Non-referrals after budget exhaustion legitimately
    have propensity 0 -- they were never in the draw -- and are excluded from
    the estimand, which policy.py documents."""
    cfg = scenarios.get(scn)
    c = make_controller(4)
    for day in arrivals.make_days(cfg, 40, seed=5):
        c.start_day(day.budget)
        for i in range(day.n):
            d = c.decide(float(day.scores[i]), int(day.strata[i]),
                         float(day.times[i]))
            if d.refer:
                assert 0.0 < d.propensity <= 1.0
                Feedback(d.stratum, d.propensity, d.score, int(day.labels[i]))
            elif d.reason == BUDGET_EXHAUSTED:
                assert d.propensity == 0.0
            else:
                assert 0.0 < d.propensity <= 1.0
        c.end_day(day.n)


def test_explorer_never_returns_zero():
    e = Explorer(6)
    e.start_day(40)
    for score in (0.0, 1e-9, 0.001, 0.5, 0.99):
        p = e.propensity(score, tau=0.6, stratum=0, expected_remaining=30.0)
        assert 0.0 < p <= 1.0


def test_explorer_refers_above_threshold_outright():
    e = Explorer(6)
    e.start_day(40)
    assert e.propensity(0.9, tau=0.6, stratum=0, expected_remaining=30.0) == 1.0


def test_explorer_quota_is_exhaustible():
    """The exploration budget is finite: once a stratum's share is spent it
    falls back to the floor. This is what stops exploration eating the
    cartridge budget -- the failure that consumed 21% of it in an earlier
    design."""
    e = Explorer(6, explore_frac=0.05)
    e.start_day(40)
    for _ in range(10):
        e.charge(2)
    assert e.quota[2] <= 0
    assert e.propensity(0.5, tau=0.6, stratum=2,
                        expected_remaining=30.0) == e.p_floor


def test_quota_follows_the_information_deficit():
    """The point of stratified exploration: probe where the ignorance is.

    A uniform band gave the drifted stratum 36 referrals in 200 days while a
    perfectly calibrated stratum got 118, and the estimator never fired.
    """
    e = Explorer(4, explore_frac=0.1)
    e.start_day(40, deficits=[0.0, 1.0, 0.0, 0.0])
    assert e.quota[1] > 0
    assert e.quota[0] == 0.0 and e.quota[2] == 0.0 and e.quota[3] == 0.0
    # A stratum with no quota drops to the floor; the starved one is probed.
    assert e.propensity(0.1, 0.6, 0, 30.0) == e.p_floor
    assert e.propensity(0.1, 0.6, 1, 30.0) > e.p_floor


def test_quota_is_uniform_without_deficits():
    e = Explorer(4, explore_frac=0.1)
    e.start_day(40)
    assert np.allclose(e.quota, e.quota[0])
    e.start_day(40, deficits=[0.0, 0.0, 0.0, 0.0])
    assert np.allclose(e.quota, e.quota[0]), "all-zero deficit falls back to uniform"


def test_calibrator_deficit_falls_as_evidence_accumulates():
    c = StratumCalibrator(2, ess_min=40.0)
    assert c.deficit()[0] == pytest.approx(1.0)
    rng = np.random.default_rng(0)
    c.update(synth_feedback(rng, 20, 0, 0.2, 0.2, propensity=0.5))
    assert 0.0 < c.deficit()[0] < 1.0
    assert c.deficit()[1] == pytest.approx(1.0), "untouched stratum stays starved"


def test_explorer_rejects_bad_config():
    with pytest.raises(ValueError):
        Explorer(6, p_floor=0.0)
    with pytest.raises(ValueError):
        Explorer(6, explore_frac=1.5)
    with pytest.raises(ValueError):
        Explorer(0)


# --- the pacer -------------------------------------------------------------


def test_pacer_threshold_falls_as_budget_rises():
    p = BudgetPacer()
    rng = np.random.default_rng(0)
    for _ in range(512):
        p.observe(float(rng.random()))
    p.start_day()
    for _ in range(100):
        p.observe(float(rng.random()))
    lo = p.tau_for(5, 4.0)
    hi = p.tau_for(50, 4.0)
    assert hi < lo, "more budget must mean a lower bar"


def test_pacer_blocks_when_budget_gone():
    p = BudgetPacer()
    p.observe(0.5)
    assert p.tau_for(0, 4.0) == np.inf


def test_pacer_volume_estimate_self_corrects_within_the_day():
    """Clock-driven estimation must converge to today's actual volume even
    when the historical prior is badly wrong -- the fix for the hoarding bug."""
    p = BudgetPacer(n_prior=200.0)
    p.start_day()
    for i in range(300):                       # a 300-patient day
        p.observe(0.5)
    est = p.expected_total(8.0)
    assert abs(est - 300) < 1.0


def test_pacer_memory_is_flat():
    p = BudgetPacer(sketch_size=512)
    before = p.state_bytes
    rng = np.random.default_rng(0)
    for _ in range(100_000):
        p.observe(float(rng.random()))
    assert p.state_bytes == before


def test_pacer_rejects_bad_config():
    with pytest.raises(ValueError):
        BudgetPacer(sketch_size=0)
    with pytest.raises(ValueError):
        BudgetPacer(day_hours=0)


# --- the calibrator: the contribution --------------------------------------


def synth_feedback(rng, n, stratum, true_rate, claimed, propensity):
    """Referrals whose true case rate may differ from what the model claims."""
    return [Feedback(stratum, propensity, claimed, int(rng.random() < true_rate))
            for _ in range(n)]


def test_correct_is_identity_at_zero_offset():
    c = StratumCalibrator(4)
    for s in (0.01, 0.2, 0.5, 0.9):
        assert c.correct(s, 0) == pytest.approx(s, abs=1e-6)


def test_correct_applies_a_logit_shift():
    c = StratumCalibrator(2)
    c._d[1] = 1.0
    assert c.correct(0.5, 1) == pytest.approx(sigmoid(logit(0.5) + 1.0))
    assert 0.0 < c.correct(1e-9, 1) < 1.0, "must stay a valid probability"


def test_offsets_stay_at_zero_when_the_model_is_right():
    """The degeneracy claim: no drift means no correction, so the controller
    reduces to pure pacing and cannot lose to its own ablation."""
    rng = np.random.default_rng(0)
    c = StratumCalibrator(1, ess_min=80.0)
    for _ in range(300):
        c.update(synth_feedback(rng, 40, 0, true_rate=0.12,
                                claimed=0.12, propensity=0.5))
    assert abs(c.offsets[0]) < 0.25, f"spurious drift: {c.offsets[0]}"


def test_offsets_rise_when_the_model_under_scores():
    """The core mechanism: true rate above the model's claim drives the
    offset up, in the direction that puts the stratum back in the referred
    set."""
    rng = np.random.default_rng(1)
    c = StratumCalibrator(1, ess_min=80.0)
    for _ in range(300):
        c.update(synth_feedback(rng, 40, 0, true_rate=0.30,
                                claimed=0.12, propensity=0.5))
    assert c.offsets[0] > 0.5


def test_offsets_fall_when_the_model_over_scores():
    rng = np.random.default_rng(2)
    c = StratumCalibrator(1, ess_min=80.0)
    for _ in range(300):
        c.update(synth_feedback(rng, 40, 0, true_rate=0.05,
                                claimed=0.25, propensity=0.5))
    assert c.offsets[0] < -0.5


def test_offset_magnitude_tracks_the_true_shift():
    """Not just the sign: the learned offset should approximate the actual
    logit gap, which is what makes it a calibration map rather than a nudge."""
    rng = np.random.default_rng(3)
    claimed, true_rate = 0.10, 0.25
    want = logit(true_rate) - logit(claimed)
    c = StratumCalibrator(1, ess_min=80.0)
    for _ in range(600):
        c.update(synth_feedback(rng, 40, 0, true_rate, claimed, propensity=0.5))
    assert abs(c.offsets[0] - want) < 0.35, f"got {c.offsets[0]}, want ~{want}"


def test_thin_evidence_does_not_move_the_offset():
    """The ESS guard. Steering on a starved estimate is how the loop
    destabilises; the evidence is banked, not spent."""
    rng = np.random.default_rng(4)
    c = StratumCalibrator(1, ess_min=80.0)
    c.update(synth_feedback(rng, 2, 0, 0.5, 0.05, propensity=0.004))
    assert c.offsets[0] == 0.0
    assert c.updates[0] == 0


def test_banked_evidence_is_not_discarded():
    """Batches too thin to act on must still accumulate, or a rare stratum
    never learns anything at all."""
    rng = np.random.default_rng(5)
    c = StratumCalibrator(1, ess_min=80.0)
    for _ in range(200):
        c.update(synth_feedback(rng, 1, 0, 0.4, 0.05, propensity=0.5))
    assert c.updates[0] > 0, "many thin batches should eventually add up"


def test_starved_stratum_holds_its_last_value():
    c = StratumCalibrator(3, ess_min=80.0)
    rng = np.random.default_rng(6)
    for _ in range(50):
        c.update(synth_feedback(rng, 40, 1, 0.3, 0.1, propensity=0.5))
    assert c.offsets[0] == 0.0 and c.offsets[2] == 0.0
    assert c.offsets[1] != 0.0


def test_offsets_are_clipped():
    rng = np.random.default_rng(7)
    c = StratumCalibrator(1, clip=0.5, ess_min=80.0)
    for _ in range(400):
        c.update(synth_feedback(rng, 40, 0, 0.9, 0.01, propensity=0.5))
    assert abs(c.offsets[0]) <= 0.5 + 1e-9


def test_calibrator_memory_is_flat():
    c = StratumCalibrator(6)
    before = c.state_bytes
    rng = np.random.default_rng(8)
    for _ in range(2000):
        c.update(synth_feedback(rng, 20, 3, 0.2, 0.1, propensity=0.3))
    assert c.state_bytes == before


def test_calibrator_rejects_bad_config():
    with pytest.raises(ValueError):
        StratumCalibrator(0)
    with pytest.raises(ValueError):
        StratumCalibrator(2, p_floor=0.0)
    with pytest.raises(ValueError):
        StratumCalibrator(2, ess_min=0.0)


def test_empty_batch_is_harmless():
    c = StratumCalibrator(3)
    c.update([])
    assert np.all(c.offsets == 0.0)


# --- NFR1 / NFR7 -----------------------------------------------------------


def test_controller_memory_is_flat_over_a_long_run():
    """The O(1) claim, on the whole controller rather than a part."""
    cfg = scenarios.get("volatile")
    c = make_controller(9)
    days = arrivals.make_days(cfg, 5, seed=10)
    metrics.run(c, days, cfg.delay)
    before = c.state_bytes
    metrics.run(c, arrivals.make_days(cfg, 200, seed=11), cfg.delay)
    assert c.state_bytes == before


def test_controller_does_not_import_backend():
    """NFR7. Keeping the controller framework-free is what makes it testable
    here, portable to a device later, and clean to recite in a claim."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "controller"
    for f in root.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "import backend" not in src and "from backend" not in src, f


def test_ablation_shares_the_pacing_code():
    """If the ablation had its own pacer, the comparison would measure the
    difference between two pacers rather than the contribution."""
    from controller.budget import BudgetPacer as PacerUsedByController
    assert isinstance(baselines.ClockPacer().pacer, PacerUsedByController)


def test_ablation_learns_nothing():
    cfg = scenarios.get("ranking_drift")
    days = arrivals.make_days(cfg, 80, seed=12)
    pac = baselines.ClockPacer()
    metrics.run(pac, days, cfg.delay)
    assert not hasattr(pac, "offsets")


def test_recalibrate_false_disables_learning():
    cfg = scenarios.get("ranking_drift")
    c = make_controller(13, recalibrate=False)
    metrics.run(c, arrivals.make_days(cfg, 80, seed=14), cfg.delay)
    assert np.all(c.offsets == 0.0)


# --- reproducibility (NFR4) ------------------------------------------------


def test_seeded_runs_are_identical():
    cfg = scenarios.get("volatile")
    days = arrivals.make_days(cfg, 30, seed=15)
    a = metrics.run(make_controller(16), days, cfg.delay)
    b = metrics.run(make_controller(16), days, cfg.delay)
    assert (a.caught, a.spent, a.explore_spend) == (b.caught, b.spent,
                                                    b.explore_spend)


# --- metrics ---------------------------------------------------------------


def test_beats_requires_not_outspending():
    """Guards the primary metric: extra cases bought with extra cartridges is
    not a win, and this is what stops a ratio metric sneaking back in."""
    a = metrics.RunResult("a", caught=100, spent=200)
    b = metrics.RunResult("b", caught=90, spent=100)
    assert not metrics.beats(a, b)
    c = metrics.RunResult("c", caught=100, spent=101)
    assert metrics.beats(c, b)


def test_oracle_spends_the_whole_budget():
    cfg = scenarios.get("calm")
    days = arrivals.make_days(cfg, 30, seed=17)
    r = metrics.run_oracle(days)
    assert r.spent == sum(min(d.budget, d.n) for d in days)


def test_risk_oracle_beats_score_oracle_under_ranking_drift():
    """True-risk ranking must dominate the drifted model's ranking -- this is
    the headroom recalibration is trying to recover."""
    cfg = scenarios.get("ranking_drift")
    days = arrivals.make_days(cfg, 150, seed=18)[50:]
    assert metrics.run_oracle(days, use_risk=True).caught > \
        metrics.run_oracle(days, use_risk=False).caught
