"""False-negative certificate tests.

The certificate is the estimand that actually requires exploration, so the most
important test here is the one asserting that it *fails loudly* without it --
`test_without_exploration_the_estimate_is_zero_and_flagged`.

An estimator that returns zero when it cannot see anything is not a small bug.
Zero is the best possible answer, so a controller reading it would conclude it
is performing perfectly and tighten further. That is the divergence failure the
project exists to prevent, and the `identifiable` flag is what separates a
degraded certificate from a silently false one.
"""

import numpy as np
import pytest

from controller import metrics
from controller.certificate import FNRCertificate
from controller.policy import CartPaceController
from sim import arrivals, scenarios
from sim.labels import Feedback


def cases(n, propensity):
    """n confirmed cases, all referred at the same propensity."""
    return [Feedback(0, propensity, 0.5, 1) for _ in range(n)]


def test_all_referred_outright_means_no_misses():
    """Everything above the line was referred, so nothing above it was missed.
    Zero is the correct answer here -- but it is also the answer returned when
    the estimator is blind, which is why `identifiable` exists."""
    c = FNRCertificate(ess_min=1.0)
    c.observe(cases(50, propensity=1.0))
    fnr, _ = c.estimate()
    assert fnr == pytest.approx(0.0)
    assert not c.identifiable


def test_without_exploration_the_estimate_is_zero_and_flagged():
    """The core failure mode. With p = 1 on every referral the numerator is
    identically zero for any input, so the certificate reads 0% no matter how
    many cases are really being missed."""
    c = FNRCertificate(ess_min=1.0)
    c.observe(cases(500, propensity=1.0))
    fnr, half = c.estimate()
    assert fnr == 0.0 and half == 0.0
    assert not c.identifiable, "must not present a blind estimate as a real one"


def test_exploration_makes_it_identifiable():
    c = FNRCertificate(ess_min=1.0)
    c.observe(cases(20, propensity=1.0))
    assert not c.identifiable
    c.observe(cases(3, propensity=0.05))
    assert c.identifiable


def test_recovers_a_known_false_negative_rate():
    """Half the cases are reachable only at propensity 0.2, so in expectation
    80% of that half is missed."""
    rng = np.random.default_rng(0)
    c = FNRCertificate(ess_min=1.0)
    n, p = 4000, 0.2
    c.observe(cases(n, propensity=1.0))                       # always referred
    drawn = int(rng.binomial(n, p))                           # the rest, sampled
    c.observe(cases(drawn, propensity=p))
    fnr, half = c.estimate()
    expected = (n * (1 - p)) / (2 * n)                        # = 0.4
    assert abs(fnr - expected) < 0.05, f"got {fnr}, want ~{expected}"
    assert half > 0


def test_lower_propensity_widens_the_interval():
    """Precision is what exploration actually buys. Rarer probes carry heavier
    weights and a wider interval for the same number of observed cases."""
    a = FNRCertificate(ess_min=1.0)
    a.observe(cases(100, 1.0))
    a.observe(cases(30, 0.30))
    b = FNRCertificate(ess_min=1.0)
    b.observe(cases(100, 1.0))
    b.observe(cases(30, 0.02))
    assert b.estimate()[1] > a.estimate()[1]


def test_starved_estimate_is_withheld():
    """Below the effective-sample-size floor the certificate reports nothing
    rather than something misleading."""
    c = FNRCertificate(ess_min=20.0)
    c.observe(cases(2, 0.5))
    fnr, half = c.estimate()
    assert np.isnan(fnr) and np.isnan(half)


def test_negatives_carry_no_information():
    """A confirmed non-case says nothing about how many cases were missed."""
    c = FNRCertificate(ess_min=1.0)
    c.observe(cases(30, 0.5))
    before = c.estimate()
    c.observe([Feedback(0, 0.5, 0.5, 0) for _ in range(500)])
    assert c.estimate() == before


def test_memory_is_flat():
    c = FNRCertificate()
    before = c.state_bytes
    for _ in range(1000):
        c.observe(cases(20, 0.3))
    assert c.state_bytes == before


def test_rejects_bad_config():
    with pytest.raises(ValueError):
        FNRCertificate(p_floor=0.0)


def test_empty_batch_is_harmless():
    c = FNRCertificate()
    c.observe([])
    assert not c.identifiable


# --- G5, end to end --------------------------------------------------------


def test_certificate_brackets_the_truth_on_a_real_run():
    """G5. The estimate must contain the realised false-negative rate that the
    simulator knows and the controller never sees."""
    cfg = scenarios.get("ranking_drift")
    covered = 0
    for seed in range(3):
        days = arrivals.make_days(cfg, 200, seed=seed)
        c = CartPaceController(scenarios.N_STRATA,
                               np.random.default_rng(seed + 100),
                               p_floor=0.02, explore_frac=0.05)
        metrics.run(c, days[:50], cfg.delay)
        r = metrics.run(c, days[50:], cfg.delay)
        fnr, half = c.certificate()
        assert c.cert.identifiable
        if abs(fnr - r.realised_fnr) <= half:
            covered += 1
    assert covered == 3, f"only {covered}/3 seeds bracketed the truth"


def test_real_run_without_exploration_certifies_zero_falsely():
    """The same run with exploration switched off certifies 0% while really
    missing around 38% of cases -- and says so via `identifiable`."""
    cfg = scenarios.get("ranking_drift")
    days = arrivals.make_days(cfg, 150, seed=0)
    c = CartPaceController(scenarios.N_STRATA, np.random.default_rng(1),
                           p_floor=1e-12, explore_frac=0.0)
    metrics.run(c, days[:50], cfg.delay)
    r = metrics.run(c, days[50:], cfg.delay)
    fnr, _ = c.certificate()
    assert r.realised_fnr > 0.2, "the run really is missing a lot of cases"
    assert fnr == 0.0, "and the blind estimator says none"
    assert not c.cert.identifiable
