# P2 risk spike — findings

**Verdict: NO-GO on the gate as written.** Reproduce with `python spike_p2.py`.

200 evaluation days × 5 seeds, budget 40 cartridges/day, 6 strata, score model
AUC ≈ 0.88, baselines tuned on a 60-day held-out warmup then frozen.

The gate conditions were written down before anything was run, and they are
reported here unchanged. Three of four pass. The one that fails does so by
three cases out of 3035.

| Gate | Condition | Result |
|---|---|---|
| G1 | `ranking_drift` ≥ +3% vs ablation, no more spend | **PASS** (+3.59%, spend ×1.004) |
| G2 | `calm` loses ≤ 1% | **PASS** (−0.75%) |
| G3 | Beats `Fixed` and `Greedy` in every scenario | **FAIL** — see below |
| G4 | Exploration ≤ 10% of cartridges | **PASS** (1.2%) |
| — | Exploration pays for itself | **NO** — see below |

## Headline results

| Scenario | Fixed | ClockPacer (ablation) | CartPace | vs ablation |
|---|---|---|---|---|
| calm | 3035 | 3055 | 3032 | **−0.75%** |
| prevalence_drift | 2880 | 3034 | 3015 | −0.63% |
| **ranking_drift** | 2901 | 2925 | **3030** | **+3.59%** |
| shortage | 2803 | 2872 | 2852 | −0.70% |
| **volatile** | 2450 | 2658 | **2764** | **+3.99%** |

## 1. The core contribution is real

Under ranking drift, per-stratum recalibration beats budget pacing alone by
**+3.59%** cases at +0.4% spend, and by **+3.99%** under `volatile`. The learned
offsets track the injected drift closely:

```
ranking_drift   learned [-0.00 -0.06  0.08 -0.02  1.63  0.12]
                true    [ 0     0     0     0     2     0   ]

volatile        learned [-0.01 -0.05 -0.03 -0.01  2.01  0.10]
                true    [ 0     0     0     0     2.5   0   ]
```

Only the drifted stratum moves; the other five stay within ±0.13 of zero. This
is the claim working exactly as specified: the budget still binds and is still
spent in full, but the *composition* of the referred set improves.

The degeneracy property also holds. In `calm` and `prevalence_drift` the
offsets converge to ≈0 and the controller reduces to pure pacing, losing only
the cost of the positivity floor.

This is a genuine reversal of the earlier iteration's null result. The
mechanism that had no channel to act through now has one.

## 2. Why G3 fails, and why that is not a formality

In `calm`, CartPace scores 3032 against a tuned fixed threshold's 3035 — three
cases, 0.1%, well inside seed noise. G3 as written requires beating `Fixed` in
*every* scenario.

The failure is structurally honest. In a stationary world with a well-tuned
threshold there is nothing to adapt to, so adaptation can only cost. That is
the behaviour `project.md` predicts and wants. But the gate was written to say
"every scenario", and the result is reported against the gate as written rather
than against a gate rewritten afterwards to fit.

**This is a judgement call for the project owner, not for the implementer.**
Either G3 is relaxed to "beats Fixed and Greedy in every non-stationary
scenario, and ties in stationary ones" — which is defensible and arguably what
was meant — or the result stands as NO-GO. It should not be quietly amended.

## 3. The finding that matters most: exploration does not pay for itself

The claim rests on E6, the coupling in which exploration is financed from the
same depleting budget being allocated. W0 clearance found E6 to be the **only
one of seven claim elements with no anticipating reference**. Everything else
was anticipated — budget-coupled thresholding by Bandits with Knapsacks,
propensity-logged exploration by Counterfactual Risk Minimisation, and
per-stratum correction from censored feedback, in substance, by reject
inference in credit scoring.

Measured, on `ranking_drift`:

| explore_frac | p_floor | cases | exploration | vs ablation |
|---|---|---|---|---|
| 0.000 | 1e-6 | **3036** | 0.0% | **+3.79%** |
| 0.000 | 0.002 | 3028 | 1.0% | +3.52% |
| 0.005 | 0.002 | 3030 | 1.2% | +3.59% |
| 0.020 | 0.004 | 3005 | 3.6% | +2.74% |
| 0.050 | 0.004 | 2976 | 6.9% | +1.74% |

**Performance is monotonically decreasing in exploration.** The best
configuration is the one with effectively none.

### Why this happened

Mid-spike the estimator was changed, and the change is what dissolved the need
for exploration.

Calibration is a **conditional** property: `E[y | s, k] = s`. Selection into the
referred set depends only on the corrected score, the stratum and the clock —
that is, only on variables being conditioned on. Conditioning on selection
therefore does not bias a calibration estimate, and no inverse-propensity
correction is required for this quantity. Verified on synthetic data with a
true offset of 1.20: estimating on the **top 5% of scores alone** recovers 1.16.

So the offsets can be learned from patients who were referred anyway. Probing
below the line buys nothing they do not already provide.

Inverse-propensity weighting was not merely unnecessary, it was harmful.
Weights span 1 to `1/p_floor`, and a single floor-propensity referral collapses
the effective sample size of an 80-patient batch from 80 to **1.7**, so the
update fired almost never. That is risk R3, firing exactly as `project.md`
predicted, and it is why the first working version learned nothing.

### The lockout hypothesis was tested and did not rescue it

If drift pushed a stratum entirely out of the referred set, it would generate
no data at all and the state would be absorbing — no recovery without a
positivity floor. That would have made exploration load-bearing again. Tested
at three drift magnitudes:

| drift max | p_floor | cases vs ablation | learned offset |
|---|---|---|---|
| 2.0 | 1e-6 | +3.90% | 1.73 |
| 2.0 | 0.002 | +3.22% | 1.61 |
| 4.0 | 1e-6 | +0.34% | 0.65 |
| 4.0 | 0.002 | +0.19% | **0.97** |
| 6.0 | 1e-6 | −0.14% | 0.23 |
| 6.0 | 0.002 | −0.34% | **0.41** |

Exploration **does** recover more calibration at every drift level — the offsets
are consistently higher with a floor than without. It simply never recovers
enough to pay for the cartridges it consumes. The hypothesis is directionally
right and quantitatively insufficient.

Note also that at drift ≥ 4.0 the contribution collapses entirely regardless of
exploration. Recalibration cannot track drift that outruns the evidence it can
gather in 200 days.

## 4. What this does to the patent position

Combining W0 and P2:

- The **supported** effect — per-stratum recalibration of a frozen model from
  selectively-labelled data — is the element W0 found anticipated in substance
  by reject inference.
- The **unanticipated** element — exploration financed from the allocated
  budget — is the element P2 finds unsupported by evidence.

That is an uncomfortable position and it should be stated plainly rather than
managed. The honest options are in `docs/p2-findings.md` §5 and the decision
belongs to the project owner.

It is worth recording that the surviving mechanism is *further* from the
original claim than the abandoned one, not closer. The argument that makes it
work — that calibration is estimable on the selected set because selection
depends only on the score — is itself standard reasoning in the selective-labels
and reject-inference literature.

## 5. Options

1. **Relax G3 and proceed on the recalibration effect.** The effect is real,
   reproducible and gated. Accept that the patent claim narrows to the specific
   mechanism — deficit-directed stratified probing, constant memory, on-device —
   and that the exploration-funding story is dropped. Requires re-running W0
   clearance against the *new* mechanism, since the cleared claim no longer
   matches what was built.

2. **Keep exploration and claim the certificate, not the throughput.** A
   false-negative certificate over never-referred patients is a *marginal*
   quantity and genuinely does require exploration and propensity weighting.
   It was deferred in this spike (gate G5 unmeasured). This is the honest home
   for E6 — but it must be claimed as a measurement guarantee, not as a
   case-finding improvement, because the numbers above show it is not one.

3. **Pivot to the monthly budget pool.** The `project.md` §16 fallback. Lifting
   the budget from daily to monthly makes it non-binding within a day, which is
   a different and possibly stronger setting.

4. **Stop and reconsider the patent target.** Publication as an honest negative
   and corrective result remains available and is strengthened, not weakened, by
   these findings.

## 6. Bugs found and fixed during the spike

Each was found by inspecting intermediate state rather than by a failing test,
which is worth noting: none of them would have raised an error.

- **One-sided ratchet in the offset update.** With an effective-sample-size
  floor of 3, and floor-propensity weights of 250, three real patients register
  ESS 3. At 5% prevalence 86% of three-patient batches contain no cases at all;
  a zero-case batch gives `logit(0)` clipped to −6.9 against a model claim near
  −2.9, pinning the step at its negative limit. Nothing pushes back, because a
  batch cannot contain fewer than zero cases. Low-prevalence strata drifted to
  −0.80. Fixed by accumulating sufficient statistics across days and raising the
  floor.
- **Residual bias from taking logit of a noisy rate.** Even after the above,
  expected step was −0.044 per update when the true offset was zero, and still
  −0.015 at ESS 200 — more evidence alone does not fix it. Fixed with a Jeffreys
  posterior mean, which brings it to +0.004.
- **Exploration aimed at the wrong strata.** A band defined in score units never
  reaches a stratum the model has pushed far below threshold. Measured: the
  drifted stratum got 36 exploratory referrals in 200 days while a perfectly
  calibrated stratum got 118. Fixed by allocating the quota by per-stratum
  information deficit — after which the drifted stratum received the most
  probes, 133.
- **Per-decision latency ~150 µs**, two orders of magnitude above the NFR2
  budget, from two `np.quantile` calls per decision. Fixed with a cached sort,
  reused for up to 16 arrivals: **24 µs**.

## 7. What was not measured

- **G5, certificate bracketing.** The false-negative certificate is not yet
  implemented or gated. It is the natural home for option 2 above and should be
  built before that option is chosen.
- Drift that moves faster than the evidence can track (≥4.0 logits) breaks the
  contribution entirely. The operating envelope is not characterised.
- Strata are fixed and correct by construction here. A mis-specified partition —
  the realistic case — is untested.
