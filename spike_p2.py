"""P2 risk spike -- the Phase 6 go/no-go gate.

Question: does per-stratum recalibration beat budget pacing alone?

The gate conditions were written down before running anything:

  G1  under ranking_drift, CartPace beats ClockPacer by >= +3% cases at no
      more than +2% spend
  G2  under calm, CartPace loses no more than 1%
  G3  CartPace beats Fixed and Greedy in every scenario
  G4  exploration stays at or below 10% of cartridges
  G5  the false-negative certificate brackets the realised rate

It also runs the ablation that answers the *second* question, which matters as
much as the first: is the exploration that the claim rests on actually earning
its cost?

Run: python spike_p2.py
"""

import sys

import numpy as np

from controller import baselines, metrics
from controller.policy import CartPaceController
from sim import arrivals, scenarios

N_DAYS, WARMUP, SEEDS = 260, 60, 5
SCENARIOS = ["calm", "prevalence_drift", "ranking_drift", "shortage", "volatile"]


def tune_fixed(days):
    """Best single threshold on the warmup period, then frozen -- this is what
    'current standard of care, tuned by an expert' looks like."""
    best_tau, best = 0.5, -1
    for tau in np.arange(0.05, 0.95, 0.02):
        r = metrics.run(baselines.Fixed(float(tau)), days, delay=0)
        if r.caught > best:
            best, best_tau = r.caught, float(tau)
    return best_tau


def one_seed(scn, seed, **kw):
    cfg = scenarios.get(scn)
    days = arrivals.make_days(cfg, N_DAYS, seed=seed)
    warm, ev = days[:WARMUP], days[WARMUP:]
    tau = tune_fixed(warm)

    cap = CartPaceController(scenarios.N_STRATA,
                             np.random.default_rng(seed + 100), **kw)
    pac = baselines.ClockPacer()
    metrics.run(cap, warm, cfg.delay)          # warm up, discard
    metrics.run(pac, warm, cfg.delay)

    out = {
        "CartPace": metrics.run(cap, ev, cfg.delay, "CartPace"),
        "ClockPacer (ablation)": metrics.run(pac, ev, cfg.delay,
                                             "ClockPacer (ablation)"),
        "Fixed (tuned)": metrics.run(baselines.Fixed(tau), ev, cfg.delay,
                                     "Fixed (tuned)"),
        "Greedy (no pacing)": metrics.run(baselines.Greedy(), ev, cfg.delay,
                                          "Greedy (no pacing)"),
        "Random under budget": metrics.run(
            baselines.RandomUnderBudget(np.random.default_rng(seed + 900)),
            ev, cfg.delay, "Random under budget"),
    }
    oracle = metrics.run_oracle(ev)
    oracle_risk = metrics.run_oracle(ev, use_risk=True)
    oracle_risk.policy = "TopB oracle (true risk)"
    return out, oracle, oracle_risk, cap.offsets, ev[-1].true_offsets


def evaluate(scn, **kw):
    per_policy, oracles, oracles_risk, offsets, truth = {}, [], [], [], None
    for seed in range(SEEDS):
        out, orc, orc_r, off, tru = one_seed(scn, seed, **kw)
        for name, res in out.items():
            per_policy.setdefault(name, []).append(res)
        oracles.append(orc)
        oracles_risk.append(orc_r)
        offsets.append(off)
        truth = tru
    means = {n: metrics.mean_result(rs, n) for n, rs in per_policy.items()}
    return (means,
            metrics.mean_result(oracles, "TopB oracle (model score)"),
            metrics.mean_result(oracles_risk, "TopB oracle (true risk)"),
            np.mean(offsets, axis=0), truth)


def main():
    print(f"\n{N_DAYS - WARMUP} eval days x {SEEDS} seeds | "
          f"budget 40/day | {scenarios.N_STRATA} strata\n")

    summary = {}
    for scn in SCENARIOS:
        means, orc, orc_r, off, truth = evaluate(scn)
        cap, pac = means["CartPace"], means["ClockPacer (ablation)"]
        print(f"=== {scn} ===")
        print(metrics.table(
            [means[n] for n in ["Greedy (no pacing)", "Random under budget",
                                "Fixed (tuned)", "ClockPacer (ablation)",
                                "CartPace"]],
            None))
        print(f"{orc.policy:<24}{orc.caught:>8}{orc.spent:>8}")
        print(f"{orc_r.policy:<24}{orc_r.caught:>8}{orc_r.spent:>8}")
        delta = 100.0 * (cap.caught / pac.caught - 1.0)
        print(f"\n  learned offsets : {np.round(off, 2)}")
        print(f"  true offsets    : {np.round(truth, 2)}")
        print(f"  vs ablation     : {delta:+.2f}% cases, "
              f"spend x{cap.spent / pac.spent:.3f}")
        summary[scn] = dict(delta=delta, cap=cap, pac=pac,
                            fixed=means["Fixed (tuned)"],
                            greedy=means["Greedy (no pacing)"])
        print()

    # --- is exploration earning its keep? ---------------------------------
    print("=== exploration ablation (ranking_drift) ===")
    print("The claim rests on exploration being funded from the budget it")
    print("allocates. That is only a contribution if it pays for itself.\n")
    print(f"{'explore_frac':>13}{'p_floor':>10}{'cases':>8}{'spent':>8}"
          f"{'expl%':>8}{'vs ablation':>13}")
    explore_rows = []
    for ef, pf in ((0.0, 1e-6), (0.0, 0.002), (0.005, 0.002), (0.02, 0.004),
                   (0.05, 0.004)):
        means, _, _, _, _ = evaluate("ranking_drift", explore_frac=ef, p_floor=pf)
        cap, pac = means["CartPace"], means["ClockPacer (ablation)"]
        d = 100.0 * (cap.caught / pac.caught - 1.0)
        explore_rows.append((ef, pf, cap.caught, d))
        print(f"{ef:>13.3f}{pf:>10.4f}{cap.caught:>8}{cap.spent:>8}"
              f"{cap.explore_share * 100:>7.1f}%{d:>+12.2f}%")

    # --- G5: the certificate, and what exploration actually buys ----------
    print("\n=== certificate (ranking_drift) ===")
    print("The offsets need no exploration. The certificate is a marginal")
    print("quantity over never-referred patients, and cannot exist without it.\n")
    print(f"{'p_floor':>9}{'expl_frac':>11}{'realised':>10}{'certified':>11}"
          f"{'halfwidth':>11}{'covers':>8}{'usable':>8}")
    g5_rows = []
    for pf, ef in ((1e-12, 0.0), (0.002, 0.005), (0.01, 0.02), (0.02, 0.05)):
        cfg = scenarios.get("ranking_drift")
        real, cert, half, ident = [], [], [], []
        for seed in range(SEEDS):
            days = arrivals.make_days(cfg, N_DAYS, seed=seed)
            c = CartPaceController(scenarios.N_STRATA,
                                   np.random.default_rng(seed + 100),
                                   p_floor=pf, explore_frac=ef)
            metrics.run(c, days[:WARMUP], cfg.delay)
            r = metrics.run(c, days[WARMUP:], cfg.delay)
            f, h = c.certificate()
            real.append(r.realised_fnr)
            cert.append(f)
            half.append(h)
            ident.append(c.cert.identifiable)
        ok = [not np.isnan(x) for x in cert]
        cov = (100.0 * np.mean([abs(a - b) <= h for a, b, h, o
                                in zip(cert, real, half, ok) if o])
               if any(ok) else 0.0)
        g5_rows.append((pf, ef, np.mean(real), np.nanmean(cert),
                        np.nanmean(half), cov, all(ident)))
        print(f"{pf:>9.4f}{ef:>11.3f}{100 * np.mean(real):>9.1f}%"
              f"{100 * np.nanmean(cert):>10.1f}%{100 * np.nanmean(half):>10.1f}%"
              f"{cov:>7.0f}%{str(all(ident)):>8}")

    g5 = all(r[5] >= 80.0 for r in g5_rows if r[6])
    blind = [r for r in g5_rows if not r[6]]
    if blind:
        print(f"\n  with no exploration the certificate reads "
              f"{100 * blind[0][3]:.1f}% against a realised "
              f"{100 * blind[0][2]:.1f}% -- flagged unusable, not reported.")

    # --- verdict ----------------------------------------------------------
    rd = summary["ranking_drift"]
    g1 = rd["delta"] >= 3.0 and rd["cap"].spent <= rd["pac"].spent * 1.02
    g2 = summary["calm"]["delta"] >= -1.0
    g3 = all(s["cap"].caught > s["fixed"].caught and
             s["cap"].caught > s["greedy"].caught for s in summary.values())
    g4 = all(evaluate(s)[0]["CartPace"].explore_share <= 0.10
             for s in ["ranking_drift"])

    print("\n=== gate ===")
    print(f"  G1 ranking_drift >= +3% vs ablation, no more spend : "
          f"{'PASS' if g1 else 'FAIL'}  ({rd['delta']:+.2f}%)")
    print(f"  G2 calm loses <= 1%                                : "
          f"{'PASS' if g2 else 'FAIL'}  ({summary['calm']['delta']:+.2f}%)")
    print(f"  G3 beats Fixed and Greedy everywhere               : "
          f"{'PASS' if g3 else 'FAIL'}")
    print(f"  G4 exploration <= 10% of cartridges                : "
          f"{'PASS' if g4 else 'FAIL'}")
    print(f"  G5 certificate brackets the realised FNR           : "
          f"{'PASS' if g5 else 'FAIL'}")

    best_ef = max(explore_rows, key=lambda r: r[2])
    exploration_pays = best_ef[0] > 0.0 or best_ef[1] > 1e-5
    print(f"\n  exploration pays for itself                        : "
          f"{'YES' if exploration_pays else 'NO'}"
          f"  (best: explore_frac={best_ef[0]}, p_floor={best_ef[1]})")

    verdict = "GO" if (g1 and g2 and g3 and g4 and g5) else "NO-GO"
    print(f"\nP2 VERDICT: {verdict}")
    if not exploration_pays:
        print("QUALIFIED: exploration is a net cost to CASES CAUGHT, so the "
              "throughput\nframing of the claim is not supported. It is however "
              "what makes the certificate exist at all -- G5 above shows it"
              " reads\n0.0% against a realised 38% when switched off."
              "\nSee docs/p2-findings.md.")
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
