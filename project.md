# CartPace — project specification

**Capacity-aware online controller for TB screening under a hard cartridge budget, with per-stratum recalibration learned from censored, delayed confirmatory feedback.**

Status: **Phase 0 — requirements.** Primary goal: India provisional patent application. Secondary goal: demo-quality full-stack web application (course deliverable).

Build plan and phase gates: `docs/CartPace-Build-Specification.pdf`.

---

## 1. Problem statement

A primary health centre (PHC) screens roughly 200 people per day for tuberculosis and holds roughly 40 GeneXpert cartridges to confirm diagnoses. Screening produces a risk score per patient; confirmation consumes one cartridge.

The referral threshold is fixed by protocol and never adapts to today's actual capacity. Both failure directions are real and costly:

- **Threshold too low** — cartridges are consumed by mid-morning. Afternoon arrivals, including genuinely high-risk ones, are turned away or queued. Queued patients are lost to follow-up; in TB care, loss to follow-up means untreated infectious disease and continued community transmission.
- **Threshold too high** — cartridges expire unused at the end of the day. Cases that could have been caught were not, and a scarce consumable was wasted.

Three constraints make this hard, and all three are ignored by existing work:

1. **The budget is hard and depletes irreversibly.** A cartridge spent at 09:00 is unavailable at 16:00.
2. **Decisions are online and irreversible.** The patient is physically present. You decide now. You cannot recall them after seeing the rest of the day's cohort.
3. **Feedback is censored and delayed.** Confirmatory results return days later, and *only for patients who were referred*. The system never directly observes what it missed.

Constraint 3 is the deep one: an allocation system that only ever sees labels for patients it referred cannot, by construction, measure its own false-negative rate.

## 2. Objective

Build a **model-agnostic online controller** that wraps any existing frozen screening model (chest X-ray CNN, cough classifier, symptom risk score) and, for each arriving patient, decides refer-or-not so as to:

- maximise TB cases confirmed for a given number of cartridges spent;
- never exceed the daily cartridge budget, as a hard invariant;
- maintain a continuously updated certificate on the false-negative rate, valid under covariate drift and censored, delayed feedback;
- detect and correct online degradation in the frozen model's *ranking* for identifiable subpopulations;
- run in constant memory with bounded per-decision latency, with no retraining and no connectivity at decision time.

Delivered as a working full-stack web application with a live operations dashboard.

> **Certificate status (measured 2026-09-12).** The false-negative certificate
> is implemented in `controller/certificate.py` and validated by gate G5: it
> bracketed the realised rate in 100% of seeds at every exploration level
> tested. Its halfwidth is a **delta-method approximation, not a
> distribution-free bound** - with heavy inverse-propensity weights the
> sampling distribution is skewed and the approximation understates the tail.
> The word "distribution-free" was removed from the objective above because the
> implementation does not deliver it. A patent specification asserting a
> guarantee the code does not provide is a liability, so either the bound is
> derived properly or the claim stays as it is: an estimate with a reported
> interval and an explicit identifiability flag. See `docs/p2-findings.md` section 7.

## 3. Proposed solution

Three coupled mechanisms, combined per patient.

### 3.1 Budget pacing (`controller/budget.py`)

Online rate control. A bounded quantile sketch over recent corrected scores estimates the score distribution; `tau_budget` is the quantile that spends the remaining budget evenly across the arrivals still expected today.

Today's volume is re-estimated continuously from today's own arrival rate against the clock, which is observable in any clinic. Pacing against a *historical* average hoards cartridges: high-volume days exhaust early and that loss is capped by the budget, while low-volume days end with unused cartridges and that loss is unbounded. Clock-driven estimation self-corrects within the day.

State: a fixed-size sketch.

### 3.2 Per-stratum recalibration (`controller/recalibrate.py`)

**This is the core contribution.**

The budget fixes *how many* referrals happen. The only freedom that remains is *which* patients receive them. With a single monotone score there is no such freedom — the optimal within-day policy is exactly top-B by score. Unless the score's **ranking** is wrong for some subpopulation. Then there is, and censored feedback can find it.

Patients are partitioned into `K` coarse strata (K between 6 and 8) on covariates available at the point of care without connectivity: age band, sex, HIV status, prior-TB history, symptom count. The partition is **fixed at configuration time and never learned**.

One scalar offset per stratum corrects the frozen model's score in logit space:

```
s_tilde = sigmoid( logit(s) + d_k )
```

Pacing and thresholding operate on `s_tilde`, never on the raw score. Logit space keeps the corrected value a valid probability without clipping and makes the correction a proper monotone recalibration map.

On each delayed label batch, per stratum:

```
w_i    = min( 1 / max(p_i, p_floor), 1 / p_floor )       # clipped, bounds variance
phat_k = sum_{i in k} w_i * y_i / sum_{i in k} w_i        # Horvitz-Thompson
ESS_k  = ( sum_{i in k} w_i )^2 / sum_{i in k} w_i^2
d_k   <- clip( d_k + gamma * (logit(phat_k) - logit(sbar_k)), -L, +L )   if ESS_k >= ESS_min
```

**Why this works.** If the frozen model systematically under-scores a stratum — a CNN undertrained on HIV-positive or paediatric chest X-rays is the canonical case — pacing on the raw score places that stratum below the threshold and never refers any of it, so it never generates labels, so nothing corrects it. The exploration floor breaks that loop: a trickle is referred anyway, the propensity-weighted estimate reveals the true positive rate exceeds the model's claim, the offset rises, and the stratum re-enters the referred set — displacing a genuinely lower-value referral elsewhere.

**Total referrals are unchanged.** The budget still binds and is still spent. What changes is the *composition* of the referred set.

**Graceful degeneration.** With no ranking drift the estimate agrees with the model, offsets converge to zero, and the controller reduces exactly to pure pacing. It cannot lose to its own ablation.

State: K scalars.

### 3.3 Self-funded exploration (`controller/explore.py`)

Deterministic thresholding gives every sub-threshold patient a referral probability of exactly zero. Not small — zero. Positivity fails, inverse-propensity weighting is undefined, and no reweighting recovers the missing mass.

The controller therefore refers **stochastically**: patients below threshold are referred with a small, deliberately chosen probability, concentrated in a band immediately below the threshold where the informative cases lie, and that propensity is logged. A global floor `p_floor` applies everywhere else so positivity holds by construction.

The cost is real: those exploratory referrals are paid out of the same fixed cartridge budget the controller is optimising. **The controller must buy its own calibration data out of the budget it is spending.**

Exploration is not merely how the system is certified. With zero exploration the estimator reports FNR = 0 because it structurally *cannot observe a miss*; the controller concludes it is performing perfectly and ratchets its threshold up until it refers almost nobody — an 83% collapse, measured. Exploration is what keeps a closed-loop controller from silently converging on referring no one.

State: 2 scalars.

### 3.4 Combination (`controller/policy.py`)

```
s_tilde = recalibrate(score, stratum)
tau     = tau_budget(s_tilde)                 # from the pacer
p       = 1.0            if s_tilde > tau
        = banded_explore if tau - BAND < s_tilde <= tau and quota remains
        = p_floor        otherwise
refer   = draw(p)  and  budget_left > 0
```

**Feasibility rule:** the budget is physically hard and always wins. The FNR bound is *certified and reported*, never enforced against reality. When the budget cannot support the target FNR, the dashboard shows the certificate degrading rather than the system pretending it is met.

**Design note.** An earlier iteration combined a conformal threshold with the budget threshold as `tau = max(tau_conf, tau_budget)`. That is sign-inverted: the conformal update raises its threshold when the controller is performing well, and `max` only lets it bind when it is the more conservative of the two, so it could take control only when it wanted to refer *fewer* people and only when it believed it was already succeeding. Measured result: a pacing-only ablation beat the full controller in every regime. The conformal scalar is retained for *reporting* the certificate; it no longer gates referral.

## 4. Target users

| Role | Sees | Can do |
|---|---|---|
| `health_worker` | Live decision feed, per-patient decision and reason, patient history | Run the clinic day, record outcomes |
| `supervisor` | Everything above, plus baseline comparison and scenario controls | Set cartridge budget, configure scenarios, run comparisons, export results |

## 5. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | Ingest a stream of patients with screening scores and stratum covariates, one at a time, in arrival order. |
| FR2 | Emit an immediate, irreversible refer/no-refer decision per patient, with the logged propensity and a human-readable reason. |
| FR3 | Never exceed the configured daily cartridge budget. Hard invariant. |
| FR4 | Accept confirmatory labels arriving on a configurable delay, for referred patients only, each carrying the propensity that produced its referral. |
| FR5 | Maintain and expose a live FNR certificate with a variance estimate, updated as delayed labels land. |
| FR6 | Maintain and expose the per-stratum offsets and their effective sample sizes. |
| FR7 | Run five baseline policies on the identical seeded stream for comparison. |
| FR8 | Persist every run, decision, and label event; support full deterministic replay. |
| FR9 | Stream decisions to the browser live over WebSocket. |
| FR10 | JWT authentication with two roles; supervisor-only routes for budget and scenario control. |
| FR11 | Configurable scenarios: prevalence, arrival profile, drift mode, budget, feedback delay, shortage probability. |
| FR12 | Report score-model quality: AUC, reliability curve, dataset provenance and licence. |
| FR13 | Benchmark and report controller memory footprint and per-decision latency. |

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR1 | Controller memory is O(1) in patients seen — flat from 1k to 100k decisions. |
| NFR2 | Per-decision latency bounded and measured in microseconds. |
| NFR3 | Runs fully offline. No network dependency at decision time. |
| NFR4 | Reproducible: seeded runs produce identical results. |
| NFR5 | Clean-environment install from README succeeds without a GPU and without model weights. |
| NFR6 | No secrets in the repository. |
| NFR7 | `controller/` imports nothing but numpy, and never imports from `backend/`. |

## 7. Inputs / outputs

**Inputs** — patient screening score (or chest X-ray image, scored locally); stratum covariates; daily cartridge budget; scenario configuration; delayed confirmatory results.

**Outputs** — per-patient refer/no-refer + propensity + reason; live FNR certificate with interval; per-stratum offsets; cases caught at matched spend; budget burn-down; baseline comparison table; memory/latency benchmark.

## 8. Primary metric

> **Cases confirmed, with cartridges spent always reported alongside.** Where two policies spend different amounts, compare cases at matched spend.

**`cases per cartridge` is banned as an acceptance criterion.** It is a gameable ratio: refer only the single highest-scoring patient each day and it approaches 1.0 while the clinic catches almost nobody. Measured concretely in the earlier spike — the full-lookahead oracle *lost* on it (0.416 vs 0.431) while catching 310 more cases. A metric on which the theoretical optimum loses is not a metric.

Secondary metrics: realised vs certified FNR; per-stratum calibration error; exploration spend as a fraction of budget; budget exhaustion time; memory; per-decision latency.

## 9. Dataset

**Required: NO for the core contribution. Optional for late validation. Public only.**

The controller is model-agnostic and operates on scores. Synthetic scores from a two-component generative model give AUC ~0.87, matching published TB CXR AI performance. The scorer is not the contribution.

If time remains after the Phase 6 gate:

| Dataset | Source | Use |
|---|---|---|
| TBX11K | Kaggle (`usmanshams/tbx-11`) | Primary CXR training set |
| Shenzhen + Montgomery | NIH / Open-i, open access | Additional CXR data, evaluation |

Licence, version and download date recorded in `docs/dataset.md` before use. **Rejected:** CODA TB cough (Synapse certification + data-use statement) and MIMIC-IV (CITI training, 1–2 week lead time). Neither strengthens the claim.

> **Splits are patient-level, never image-level.** Shenzhen and Montgomery contain multiple views per patient; splitting on images leaks patients across train and test and inflates AUC. Enforced by an automated test.

## 10. Training

**Offline training: NO for v1.** The screening model is frozen and may be synthetic. Not the contribution — do not architecture-search.

**Online learning: YES, and it is the entire contribution.** K per-stratum offsets and one conformal scalar, learned from censored delayed feedback, without gradients and without retraining. This distinction matters for the patent: the invention is not a trained model, it is a control mechanism that sits on top of any trained model.

If the CXR arm is built: fine-tune ResNet-18 at 224px on Colab GPU (no local CUDA), isotonic calibration on validation. `notebooks/train_colab.ipynb` emits exactly `score_model.pt`, `calibrator.pkl`, `metrics.json`. Weights are gitignored and distributed via GitHub Release; absent weights fall back to the synthetic scorer so clean-environment runs never hard-fail.

## 11. Technology

| Layer | Choice |
|---|---|
| Controller + sim | Pure Python, numpy only |
| Backend | FastAPI + Uvicorn |
| Database | SQLite + SQLAlchemy |
| Realtime | WebSocket |
| Auth | JWT — `python-jose` + `passlib[bcrypt]` |
| Frontend | React + Vite + TypeScript, Tailwind, Recharts |
| ML (optional) | PyTorch + torchvision, scikit-learn |
| Tests | pytest + Vitest + Playwright |

Dependencies are added in the phase that first needs them, not up front.

## 12. Architecture

```
CXR image or synthetic draw
        |
        v
   frozen score model  ->  s (raw score)        stratum covariates
        |                                             |
        +---------------------+-----------------------+
                              v
                      CONTROLLER
                        d_k offsets     -> s_tilde = sigmoid(logit(s) + d_k)
                        quantile sketch -> tau_budget
                        conformal scalar-> certificate (reported, not gating)
                        explorer        -> propensity p
                              |
                              v
                decision + propensity + reason
                              |
               +--------------+--------------+
               v                             v
           SQLite                      WebSocket -> React dashboard
               ^
               |
      delayed labels (referred only, carrying their original propensity)
               |
               +--> per-stratum IPW update --> d_k, certificate
```

Dependency direction is strictly one-way: `controller/` and `sim/` depend on numpy alone; `backend/` depends on them; `frontend/` depends on `backend/` over HTTP and WebSocket only. `controller/` must never import from `backend/` — enforced by test. Keeping it framework-free is what makes it testable in the Phase 6 spike, portable to clinic hardware later, and clean to recite in a patent claim.

## 13. Scenarios and baselines

**Scenarios:** `calm`, `prevalence_drift`, `ranking_drift`, `shortage`, `volatile`.

`ranking_drift` is the one that matters. Prevalence drift preserves the score ranking, and pacing is a quantile method, so it is automatically invariant to prevalence drift — which is why an earlier simulator that drifted prevalence only made the learned layer look useless. `ranking_drift` depresses scores for a designated stratum while its true prevalence holds or rises.

**Baselines:**

1. `Fixed` — current standard of care, threshold tuned on a held-out warmup
2. `Greedy` — high-sensitivity, no pacing; the morning-exhaustion failure mode
3. `RandomUnderBudget` — floor
4. **`ClockPacer` — the ablation.** Pacing alone: no recalibration, no exploration.
5. `TopBOracle` — full-day lookahead, upper bound

> `ClockPacer` is not an optional extra. It is the ablation that deletes the novel component and keeps everything else intact, and it is the only baseline that can say whether the contribution carries any weight. Mandatory in every comparison and visible in the dashboard so it cannot quietly disappear from the story.

## 14. Constraints

- No local GPU; training is Colab-only. (Verified: `torch.cuda.is_available()` is `False`.)
- Budget is a hard physical constraint and always wins over the FNR target.
- Decisions are online and irreversible; no lookahead except the declared oracle.
- Labels are censored (referred patients only) and delayed.
- No clinical collaborator and no real clinic data; streams and capacity are simulated.
- The project lives in a OneDrive-synced folder. The GitHub remote is the only real copy — every session ends in a push.

## 15. Assumptions

- Simulated arrival streams and capacity are acceptable in place of live clinic data, for both the patent specification and the course deliverable.
- Stratum covariates are available at the point of care without connectivity — true of age, sex, HIV status and symptom count in Indian PHC practice.
- Feedback delay is configurable; fixed 3-day delay is the default, variable delay supported.
- Single clinic, single device. No multi-site concurrency.

## 16. Out of scope (v1)

| Excluded | Trigger to add in v2 |
|---|---|
| Multi-clinic / multi-tenant | A second real deployment site exists |
| Postgres | Concurrent writers appear |
| Cough audio and EHR modalities | The CXR arm is fully validated and time remains |
| Real deployment to clinic hardware | Patent filed and a partner site confirmed |
| Mobile app | A field user asks for it |
| Patient queueing / overflow to next day | The single-day model is proven first |
| Model explainability (saliency maps) | A clinical reviewer requests it |
| Monthly budget pooling across days | The daily controller passes its Phase 6 gate |

## 17. Riskiest assumptions

**R1 — Per-stratum recalibration may have no measurable effect either.** The earlier design's conformal layer had no channel through which to improve outcomes. If recalibration also fails to beat the pacing ablation, the contribution does not exist. *Mitigation: Phase 6 is a standalone spike testing exactly this, before any backend or UI work.*

**R2 — Exploration cost may exceed its benefit.** Cartridges spent below threshold are cartridges not spent on likely cases. *Mitigation: exploration rate swept in Phase 6; cost reported as an explicit metric; gate G4 bounds it at 10% of budget.*

**R3 — IPW estimates may be too high-variance to steer on**, and the problem worsens split across K strata rather than pooled. *Mitigation: weight clipping, per-stratum ESS guard, coarse strata, variance reported with every certificate; gate G5 tests it.*

**R4 — Prior art may anticipate the claim.** **Status: cleared, narrowed (2026-09-12).** Contextual Bandits with Knapsacks anticipates budget-coupled thresholding, Counterfactual Risk Minimisation anticipates propensity-logged exploration, and Adaptive Conformal Inference anticipates the conformal scalar. None may be claimed standalone. No reference was found anticipating the coupling — exploration financed from the depleting resource under allocation. *See `docs/prior-art.md` for the element-by-element analysis and the residual action items.*

**R5 — Reject inference may anticipate the recalibration element.** Surfaced during W0 clearance and not previously identified. Credit scoring has corrected models for selectively unobserved (rejected) populations for decades, using reweighting, augmentation and extrapolation. Correcting a scoring model from feedback censored by the model's own past decisions is therefore a known, named, mature technique, and cannot be claimed as novel in the abstract. *Mitigation: the specification must distinguish on three specific grounds — single-pass streaming in constant memory with no retained calibration set; operation under a hard per-period physical budget that cannot be replenished; and the exploration-funding coupling, which has no analogue in lending. Read two reject-inference surveys before drafting so the distinction is stated precisely rather than asserted.*

## 18. Acceptance criteria / Definition of Done

**Status as of 2026-09-12.** Measured by `python spike_p2.py`,
`python bench/footprint.py` and `pytest` (91 tests).

- [x] AC1 — Budget invariant never violated across ≥100 seeded days, all scenarios
- [x] AC2 — Every **referral** carries a propensity in `(0, 1]`
      *(reworded: a patient arriving after the budget is exhausted was never in
      the draw and correctly logs propensity 0. The statistically meaningful
      claim is about referrals, which is what inverse-propensity weighting
      needs. The original wording would have been violated by correct
      behaviour.)*
- [x] AC3 — Under `ranking_drift`, CartPace beats `ClockPacer` on cases at matched spend — **+3.59%**, spend ×1.004
- [x] AC4 — Under `calm`, CartPace does not lose to `ClockPacer` by more than 1% — **−0.75%**
- [ ] **AC5 — CartPace beats the tuned fixed threshold and greedy in every scenario — FAILS in `calm` by 3 cases out of 3035 (0.1%, inside seed noise).** Structurally expected: with nothing to adapt to, adaptation can only cost. Relaxing this to "every non-stationary scenario, ties in stationary ones" is a project-owner decision and has not been taken.
- [x] AC6 — Certified FNR brackets realised FNR in simulation — **100% of seeds** at every exploration level tested (G5)
- [x] AC7 — Memory and latency flat from 1k → 100k decisions — **4664 bytes throughout, heap +1.8 KB, 57.6 µs mean / 170.8 µs p99**
- [x] AC8 — Zero-exploration collapse reproduces; the identifiability flag catches it — certificate reads **0.0% against a realised 38.2%** and is flagged unusable
- [x] AC9 — A delayed label is always paired with the propensity that produced it
- [ ] AC10 — 401 unauthenticated, 403 wrong-role, expired token rejected *(backend not built — W2)*
- [ ] AC11 — Full E2E through the browser *(frontend not built — W3)*
- [ ] AC12 — Clean-environment install from README succeeds with no GPU and no weights *(not yet verified on a fresh clone)*
- [x] AC13 — No secrets committed, in working tree or history

## 19. Patent track

Primary goal. India provisional, self-drafted. Full strategy in `docs/CartPace-Build-Specification.pdf` chapter 16. Two rules that bind this repository:

> **Section 3(i) drafting discipline.** The Indian Patents Act excludes processes for diagnostic treatment of human beings. Describe this system throughout — including in this repository's own documentation, which an examiner may read — as a **consumable-inventory and resource-allocation controller for a point-of-care testing device**. Never as a diagnostic, screening or triage method.

> **Nothing goes public before the filing date exists.** No preprint, no arXiv, no public repository, no demo video, no conference or workshop submission. India has no general grace period for prior publication by the applicant. Publication before filing is irreversible.

## 20. Authorship

No AI assistant is credited anywhere in this repository — no co-author trailer on any commit, no generated-with line in any pull request, no attribution in tags or release notes. The Git history is a record of authorship and inventorship for a patent filing and a graded deliverable, not a changelog.
