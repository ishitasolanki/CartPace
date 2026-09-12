# CartPace — modular plan

Classification: **full-stack, algorithm-heavy, Complex → modular development.**

This describes the system **as built**, not as originally planned. Where the
two diverge the divergence is recorded with its reason, because a plan
presented as a description of something built differently is worse than no plan.

Build order: W0 → W4 from `docs/CartPace-Build-Specification.pdf`. Within each
module: reuse-check → implement → test → prove the test can fail → verify
integrated → commit.

---

## Module map

```
controller/   the contribution — pure Python, numpy only, no I/O, no framework
sim/          synthetic world: arrivals, drift, delayed censored labels
bench/        memory + latency measurement (patent evidence)
tests/        pytest
docs/         specification, prior art, findings
ml/           score model — deferred, synthetic scorer is the default
backend/      FastAPI — not yet built (W2)
frontend/     React — not yet built (W3)
```

**Dependency direction is strictly one-way:**

```
controller/  ←  numpy only
sim/         ←  numpy only
ml/          ←  torch
backend/     ←  controller, sim, ml
frontend/    ←  backend (HTTP + WebSocket only)
```

`controller/` must never import from `backend/`. Enforced by
`test_controller_does_not_import_backend`. Keeping it framework-free is what
made it testable in the P2 spike, portable to clinic hardware later, and clean
to recite in a patent claim.

---

## `controller/` — the core

### `recalibrate.py` — **the contribution**
```python
class StratumCalibrator:
    def __init__(self, n_strata, gamma=0.3, clip=3.0, ess_min=80.0,
                 p_floor=P_FLOOR, max_step=0.35, jeffreys=0.5,
                 weighting="none")
    def correct(self, score, stratum) -> float        # s_tilde
    def update(self, batch) -> None                   # delayed feedback
    def deficit(self) -> np.ndarray                   # steers exploration
    @property
    def offsets(self) -> np.ndarray                   # K scalars
    @property
    def state_bytes(self) -> int
```

K per-stratum logit offsets: `s_tilde = sigmoid(logit(s) + d_k)`.

**Divergence from plan — unweighted by default.** The spec called for
inverse-propensity weighting. Calibration is a *conditional* property and
selection depends only on the score and stratum, so IPW is unnecessary; it was
also actively harmful, collapsing an 80-patient batch's effective sample size
to 1.7. `weighting="ipw"` is retained as an option. See `docs/p2-findings.md` §3.

**Divergence — evidence is accumulated, not consumed per batch.** Four
offset-independent sufficient statistics per stratum, fired when ESS clears the
floor, then reset. Fixes a one-sided ratchet that drove low-prevalence strata to
−0.80. Still O(1).

### `certificate.py` — false-negative rate
```python
class FNRCertificate:
    def observe(self, batch) -> None
    def estimate(self) -> tuple[float, float]         # (fnr_hat, halfwidth)
    @property
    def identifiable(self) -> bool                    # False when blind
```
Horvitz-Thompson over never-referred patients — a **marginal** quantity, and the
one that genuinely requires exploration. `identifiable` is not cosmetic: without
exploration the estimator returns exactly 0.0, which is also the best possible
answer, so the flag is what separates a degraded certificate from a silently
false one.

### `budget.py` — pacing
```python
class BudgetPacer:
    def observe(self, score) -> None
    def afford(self, budget_left, t) -> float
    def tau_at(self, afford) -> float
    def tau_for(self, budget_left, t) -> float
    def end_day(self, n_actual) -> None
```
Clock-driven rate control over a bounded ring buffer. Sorted-sketch cache reused
for up to 16 arrivals — `np.quantile` twice per decision cost ~150 µs, two
orders above NFR2.

### `explore.py` — positivity, directed
```python
class Explorer:
    def start_day(self, budget, deficits=None) -> None
    def propensity(self, score, tau, stratum, expected_remaining) -> float
    def charge(self, stratum) -> None
```
**Divergence — stratified, not banded.** The plan specified a score-defined band
below `tau`. A stratum the model under-scores is pushed *far* below threshold and
never enters such a band: measured, the drifted stratum got 36 probes in 200 days
while a perfectly calibrated one got 118. Quota is now allocated by per-stratum
information deficit, which inverts that to 133.

### `policy.py` — combination
```python
@dataclass(frozen=True)
class Decision:
    refer: bool; propensity: float; score: float
    s_tilde: float; stratum: int; tau: float; reason: str

class CartPaceController:
    def start_day(self, budget) -> None
    def decide(self, score, stratum, t) -> Decision
    def observe_labels(self, batch) -> None
    def certificate(self) -> tuple[float, float]
```
**Hard invariant:** budget checked before the draw, so no sequence of random
outcomes can overspend it. `recalibrate=False` produces the ablation.

**Divergence — no `max(tau_conf, tau_budget)`.** That rule was sign-inverted:
it let the conformal layer bind only when it wanted to refer *fewer* people and
only when it believed it was succeeding. Referral is gated on pacing over the
recalibrated score.

### `baselines.py`
`Fixed`, `Greedy`, `RandomUnderBudget`, **`ClockPacer`**, `top_b_oracle`.

`ClockPacer` is the mandatory ablation and reuses the *same* `BudgetPacer`, so a
comparison cannot be flattered by an incidental difference in pacing code.

### `metrics.py`
`run`, `run_oracle`, `beats`, `table`, `mean_result`. `beats()` requires more
cases at no more spend — extra cases bought with extra cartridges is not a win.

---

## `sim/`

- `scenarios.py` — `calm`, `prevalence_drift`, `ranking_drift`, `shortage`, `volatile`
- `drift.py` — prevalence drift (ranking-preserving) vs ranking degradation
- `arrivals.py` — morning-weighted day; model exactly calibrated absent drift, so "the correct offset is zero" is a sharp claim. `Day.true_offsets` publishes the answer.
- `labels.py` — delayed, referred-only; `Feedback` frozen at referral so the propensity cannot be recomputed later

---

## Integration points — where bugs actually live

1. **Label ↔ propensity pairing.** A label must carry the propensity that
   produced its referral. Getting this wrong corrupts every estimate silently.
   `Feedback` is frozen at referral; `test_propensity_travels_with_the_label`.
2. **Controller state across runs.** Stateful and per-run; must not leak.
3. **backend ↔ controller** (W2) — fresh instance per run.
4. **WebSocket reconnect** (W3) — no duplicate feed entries.
5. **ml ↔ backend** (W4) — absent weights degrade to synthetic, never crash.

---

## Test plan

| Level | What | Status |
|---|---|---|
| Invariant | Budget never exceeded; propensity in (0,1]; memory flat; no backend import | 91 tests passing |
| Unit | Each controller and sim class in isolation, seeded | done |
| Statistical | Offsets converge to zero under `calm`, track injected drift under `ranking_drift` | done |
| Certificate | Brackets the truth; reads 0.0 and flags itself when blind | done |
| Bench | `bench/footprint.py` — AC7 | PASS |
| API | 401 / 403 / expired token / body validation | W2 |
| E2E | Login → run day → offsets move as labels land | W3 |

Every invariant test has been shown **red** with its guard removed before being
trusted green — calibration, drift targeting, propensity pairing, positivity,
certificate numerator, identifiability flag.

---

## Known gaps

- **AC5 fails** in `calm` by 3 cases out of 3035. Relaxation is a project-owner
  decision, untaken.
- The certificate halfwidth is a delta-method approximation, **not** a
  distribution-free bound. `project.md` was corrected to stop claiming one.
- Drift beyond ~4 logits outruns what recalibration can track; the operating
  envelope is uncharacterised.
- Strata are fixed and correct by construction. A mis-specified partition — the
  realistic case — is untested.
