# Prior art clearance — W0

**Date:** 2026-09-12
**Scope:** first-pass clearance against the intended independent claim for CartPace, before any implementation code.
**Decision:** **PROCEED, NARROWED.** See section 6.

---

## 0. What this document is, and what it is not

This is a **first-pass clearance based on literature and open web patent search**. It is enough to fix the claim structure and to stop the project building around an idea that is already anticipated. It is explicitly **not** a professional freedom-to-operate search.

Not covered, and still required before filing:

- Structured search of **Espacenet**, **Lens.org**, and **InPASS** (Indian Patent Office) by CPC class rather than by keyword.
- CPC classes that should be swept manually: `G16H 40/20` (ICT for healthcare resource management), `G16H 50/20` (ICT for medical diagnosis support), `G06N 20/00`, `G06Q 10/087` (inventory management).
- Non-English filings.
- Pending applications not yet published.

The name change from the earlier project title also **shifts the search vocabulary**. The previous clearance attempt searched terms like "capacity-constrained conformal triage". Under the resource-allocation framing required by section 3(i), the correct vocabulary is consumable allocation, test-kit inventory, reagent budgeting, and assay scheduling. Those searches are begun here but are not exhausted.

---

## 1. The claim being cleared

Stated in elements, so each can be checked independently.

| # | Element |
|---|---|
| **E1** | An online controller allocating a **hard, irreversibly depleting physical consumable** (test cartridges) across a stream of arrivals, where the decision per arrival is immediate and irreversible. |
| **E2** | A **pacing threshold** derived from remaining budget and expected remaining arrivals, estimated against the clock from the current period's own arrival rate. |
| **E3** | **Per-stratum recalibration** of a **frozen** scoring model, as K scalar offsets in logit space, learned online. |
| **E4** | The recalibration is driven by **censored, delayed feedback** — labels return only for arrivals that were selected, and only after a delay — corrected by **propensity weighting** with clipping and an effective-sample-size guard. |
| **E5** | **Stochastic selection with a positivity floor**, so no arrival has selection probability zero, making the propensity-weighted estimate identifiable. |
| **E6** | The exploration in E5 is **funded from the same depleting budget** being allocated in E1, at a measured price. |
| **E7** | Total state is **O(1)** in arrivals seen; bounded per-decision latency; no retraining; **no connectivity** at decision time. |

---

## 2. References found, and what each anticipates

### 2.1 Bandits with Knapsacks / Resourceful Contextual Bandits — **anticipates E1+E2**

Badanidiyuru, Langford & Slivkins, *Resourceful Contextual Bandits*, COLT 2014. Related: *Bandits with Knapsacks* (JACM), Agrawal & Devanur, *Linear Contextual Bandits with Knapsacks*, NeurIPS 2016.

Online decisions under hard resource constraints other than time, via primal-dual thresholding, with near-optimal regret.

> **Verdict: E1 and E2 are anticipated as a standalone claim.** This was the predicted outcome and it holds. Budget-coupled thresholding as online constrained optimisation must not be claimed on its own.

**What it does not do,** and this is the basis for distinguishing:

- BwK/CBwK **learns a policy from scratch** to maximise reward subject to resource consumption. It does not take a **frozen, externally-supplied scoring model** and correct its ranking. There is no notion of an incumbent model being wrong about a subpopulation.
- Feedback in BwK is the **immediate reward of the chosen arm**. It is bandit feedback, not *delayed, confirmatory, censored* feedback returning days later.
- Exploration in BwK is a regret-minimisation device. It is not an explicitly budgeted, priced expenditure of the constrained physical resource, and the literature does not treat "the cost of exploration in units of the constrained resource" as a reported quantity.
- No constant-memory or offline-device requirement.

### 2.2 Counterfactual Risk Minimisation / logged bandit feedback — **anticipates E5**

Swaminathan & Joachims, *Batch Learning from Logged Bandit Feedback through Counterfactual Risk Minimisation*, ICML 2015 / JMLR 16.

Propensity-scored logging of stochastic decisions, IPW estimation with variance-aware bounds, POEM.

> **Verdict: E5 is anticipated generically.** Stochastic action selection with logged propensities to make IPW valid is standard and well-published. Claim it only in combination, never alone.

Does not do: online single-pass constant-memory operation, per-stratum correction of a frozen model, or coupling of exploration cost to a physical budget.

### 2.3 Adaptive Conformal Inference — **anticipates the conformal scalar**

Gibbs & Candès, *Adaptive Conformal Inference Under Distribution Shift*, NeurIPS 2021.

Scalar gradient update of the miscoverage level from realised errors; long-run coverage under arbitrary distribution shift without exchangeability.

> **Verdict: anticipated.** ACI is exactly the `tau_conf` update the earlier design used.

**Helpfully, the redesign already removed this from the claim path.** After the measured null result, the conformal scalar was demoted to *reporting the certificate* and no longer gates referral (`project.md` §3.4). It is a reported diagnostic, not a claimed mechanism. Keep it that way.

### 2.4 Learning to defer under capacity / workload constraints — **closer than previously assessed**

- *Cost-Sensitive Learning to Defer to Multiple Experts with Workload Constraints* (arXiv 2403.06906)
- *Learning to Assign Prediction Tasks to Agents with Capacity Constraints*
- *Budgeted Multiple-Expert Deferral*, DeSalvo et al.
- Mozannar & Sontag, *Consistent Estimators for Learning to Defer to an Expert*, ICML 2020

> **Verdict: raise this from "adjacent" to "material".** The build specification listed deferral as a minor area. The capacity-constrained deferral line is structurally nearer to E1+E2 than the general deferral work is, because it explicitly allocates a limited number of expert/verification slots across a stream.

Still distinguishable: the deferred-to resource in that literature is **expert attention**, which replenishes per period and is not physically consumed; the feedback is generally not censored-and-delayed in the confirmatory sense; and the frozen-model-recalibration element is absent. But these papers must be read in full before drafting, not skimmed.

### 2.5 Reject inference in credit scoring — **the closest analogue to E3+E4, and it was not on the original list**

This is the most significant finding of W0 and it was **not** in the build specification's search plan.

Credit scoring has dealt with exactly this censoring structure for decades: repayment outcomes are observed **only for accepted applicants**; rejected applicants' true status is never known. "Reject inference" is the established family of corrections — reweighting, augmentation, extrapolation — that adjusts a scorecard for the selectively unobserved population.

> **Verdict: E3+E4 are anticipated in substance in a different domain.** Correcting a scoring model for a population whose labels are censored by the model's own past decisions is a known, named, mature technique.

This does **not** kill the claim, but it sharply narrows what can be said to be new, and any assertion that "correcting a model from censored feedback is novel" will not survive examination. What remains distinguishable:

- Reject inference is **batch and offline** — periodic scorecard refits on retained historical data. E3/E4 are **single-pass, streaming, constant-memory**, with no calibration set retained.
- Reject inference does not operate under a **hard per-period physical budget** that the correction's own data collection must be paid out of. In lending, granting an extra loan to learn is a financial decision, not consumption of a depleting physical stock that cannot be replenished within the period.
- The **coupling in E6 has no analogue**: nothing in reject inference funds its own identifiability from the same constrained resource it is optimising, nor reports the price.

### 2.6 The selective labels problem — **supports the framing, does not anticipate the mechanism**

Lakkaraju, Kleinberg, Leskovec, Ludwig & Mullainathan, *The Selective Labels Problem*, KDD 2017; and the bail/human-decisions work.

Formalises that observed outcomes are a consequence of past decisions, so a model estimates `P(Y | X, D=1)` rather than `P(Y | X)`. Proposes "contraction" for **evaluation**.

> **Verdict: not anticipating.** This is an evaluation methodology, not a controller. It is useful as a **citation for the problem statement** — it is the canonical reference establishing that the censoring problem is real and hard, which strengthens the case that solving it in a closed loop is non-obvious.

### 2.7 Resource-constrained screening threshold optimisation — **anticipates nothing new**

npj Digital Medicine 2023 LP-optimisation of screening thresholds under resource constraints; COVID triage threshold optimisation via discrete-event simulation.

Population-level, offline, full labels, static thresholds computed in advance.

> **Verdict: not anticipating.** Offline and fully labelled. Confirms the problem is recognised as important, which helps industrial applicability without threatening novelty.

---

## 3. Patent search — preliminary

Keyword search over Google Patents / USPTO surfaced:

| Reference | Content | Reads on? |
|---|---|---|
| US8697377B2, US9588109B2, US11143647B2 | Modular point-of-care devices, cartridges assembled just-in-time from pre-calibrated elements | **No.** Hardware and device architecture. No allocation control. |
| US6936476, EP1051687B1, US20060014302A1 | Point-of-care diagnostic systems | **No.** Device systems. |
| US10620198 | Device platform for point-of-care testing, cartridge and reader kits | **No.** Hardware. |
| US6890310, US6866640 | Adaptors for point-of-care testing cartridges | **No.** Mechanical. |
| US20210027647A1 | "Adaptive machine learning system" | **Unresolved — must be read in full.** Title is broad enough to matter. Flagged as an action item. |

**No granted patent found on capacity-constrained allocation of a diagnostic consumable by an adaptive controller.** That is a genuinely encouraging preliminary result, but the search was keyword-based and shallow. Treat it as "nothing obvious found", not as "clear".

---

## 4. Element-by-element summary

| Element | Status | Nearest art |
|---|---|---|
| E1 hard depleting consumable, online irreversible | **Anticipated** | BwK / CBwK |
| E2 clock-driven pacing threshold | **Anticipated** | CBwK primal-dual thresholding |
| E3 per-stratum recalibration of a frozen model | **Anticipated in substance** | Reject inference (credit scoring) |
| E4 censored delayed feedback, IPW, clipping, ESS guard | **Anticipated in substance** | Reject inference; CRM |
| E5 stochastic selection, positivity floor | **Anticipated** | CRM / logged bandit feedback |
| E6 **exploration funded from the allocated budget, at a measured price** | **No anticipating reference found** | — |
| E7 O(1) state, bounded latency, offline | **Weak — likely routine engineering** | Standard streaming/sketching |

**Every element except E6 is anticipated individually.** This is the expected and normal position for a combination invention, and it is why inventive step — not novelty — was identified as the weak link from the outset.

---

## 5. Consequences for drafting

**Do not claim, standalone:** budget-coupled thresholding (E1/E2, killed by CBwK); propensity-logged exploration for IPW validity (E5, killed by CRM); an ACI scalar threshold; recalibration from censored feedback in the abstract (E3/E4, too close to reject inference).

**Claim the coupling.** The independent claim should recite the closed loop in which:

1. a hard, irreversibly depleting physical consumable is allocated across a stream, **and**
2. the identifiability of the correction applied to a frozen scoring model is obtained **only** by consuming units of that same depleting stock, **and**
3. absent that expenditure the loop is **not merely less accurate but divergent** — the estimator cannot observe a miss, reports zero error, and the controller ratchets to selecting almost nobody.

Point 3 is the strongest available inventive-step argument and it is **empirically supported**: the measured 83% collapse at zero exploration. An examiner asserting obvious combination must explain why a skilled person would foresee that removing exploration causes divergence rather than graceful degradation. That is a genuinely non-obvious failure mode.

**Lead the technical effect with divergence prevention, not memory footprint.** E7 is the weakest element and inviting an examiner to focus on constant memory invites a routine-engineering objection. Keep the `bench/` figures as supporting evidence only.

**Section 3(i) framing is unchanged and now consistently applied.** The rename to CartPace removed "triage" from the project title, and the two remaining violations in `project.md` were corrected. Maintain: consumable-inventory and resource-allocation controller for a point-of-care testing device.

---

## 6. Decision

> **PROCEED, NARROWED.**
>
> No single reference anticipates the combination, and E6 — exploration financed from the depleting resource under allocation, with a measured price and a demonstrated divergence failure without it — has no anticipating reference found. The project is not built on an idea that is already taken.
>
> The narrowing is real and binding: four of the seven elements are individually anticipated and must never be claimed alone. The claim rests on the coupling and on the divergence result.
>
> **The go/no-go gate in Phase 6 becomes more important, not less.** E6 is the only clear element, and E6 is worthless if the recalibration it funds cannot be shown to beat the pacing-only ablation. If `spike_p2.py` fails gate G1, the patent has no supported effect and the fallback in build specification §6.5 applies.

---

## 7. Action items before filing

- [ ] Read **US20210027647A1** in full. Unresolved and potentially broad.
- [ ] Read the capacity-constrained deferral papers in full (arXiv 2403.06906 and the budgeted multiple-expert deferral line), not from abstracts.
- [ ] Read at least two reject-inference survey papers to state the distinction precisely in the specification rather than hand-waving it.
- [ ] Structured CPC search on Espacenet, Lens.org and **InPASS** under `G16H 40/20`, `G16H 50/20`, `G06Q 10/087`. Keyword search is not sufficient for filing.
- [ ] Re-run searches under the **allocation vocabulary** — consumable allocation, test-kit inventory, reagent budgeting, assay scheduling — the rename changed the relevant terms.
- [ ] Record the measured exploration price and the zero-exploration collapse in `docs/patent-evidence.md` with reproducing commands, since both are load-bearing for inventive step.

---

## Sources

- [Resourceful Contextual Bandits (PMLR)](https://proceedings.mlr.press/v35/badanidiyuru14.html)
- [Bandits with Knapsacks (JACM)](https://dl.acm.org/doi/10.1145/3164539)
- [Linear Contextual Bandits with Knapsacks (NeurIPS)](https://dl.acm.org/doi/10.5555/3157382.3157484)
- [Counterfactual Risk Minimisation (arXiv 1502.02362)](https://arxiv.org/abs/1502.02362)
- [Batch Learning from Logged Bandit Feedback (JMLR 16)](https://jmlr.org/papers/v16/swaminathan15a.html)
- [Adaptive Conformal Inference Under Distribution Shift (arXiv 2106.00170)](https://arxiv.org/abs/2106.00170)
- [Cost-Sensitive Learning to Defer with Workload Constraints (arXiv 2403.06906)](https://arxiv.org/html/2403.06906v3)
- [Budgeted Multiple-Expert Deferral (arXiv 2510.26706)](https://www.arxiv.org/pdf/2510.26706)
- [Consistent Estimators for Learning to Defer to an Expert (PMLR)](https://proceedings.mlr.press/v119/mozannar20b/mozannar20b.pdf)
- [Fighting Sampling Bias: Training and Evaluating Credit Scoring Models (arXiv 2407.13009)](https://arxiv.org/pdf/2407.13009)
- [The Selective Labels Problem (KDD 2017)](https://cs.stanford.edu/~jure/pubs/contraction-kdd17.pdf)
- [Optimal Triage for COVID-19 Under Limited Resources (JMIR)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8565604/)
- [US20210027647A1 — Adaptive machine learning system](https://patents.google.com/patent/US20210027647A1/en)
- [US11143647B2 — Modular point-of-care devices](https://patents.google.com/patent/US11143647B2/en)
