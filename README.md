# CartPace

Capacity-aware online controller for allocating a depleting point-of-care test consumable, with per-stratum recalibration learned from censored, delayed confirmatory feedback.

A primary health centre screens ~200 people a day and holds ~40 GeneXpert cartridges. A fixed referral threshold either exhausts the cartridges by mid-morning — leaving afternoon arrivals unserved — or leaves them unused at close. CartPace wraps any frozen screening model and sets the operating point online, under a hard budget, with no connectivity and no retraining.

**Status: Phase 6 complete — the go/no-go gate has been run.**

`controller/` and `sim/` are built and tested (91 tests). The gate returns
**NO-GO as written**: four of five conditions pass, and the fifth fails in the
stationary scenario by three cases out of 3035. The core effect is real —
recalibration beats budget pacing alone by +3.59% under ranking drift — but
exploration, the element prior-art clearance found unanticipated, is a net cost
to case-finding and earns its place only on the certificate. Read
`docs/p2-findings.md` before building on any of this.

## The problem in one line

Confirmatory labels come back days later and only for patients who were referred, so the controller never directly observes what it missed — and a controller that cannot observe a miss will converge on referring no one.

## What is actually new

The budget fixes *how many* referrals happen; the only remaining freedom is *which*. With a single monotone score there is none — unless the model's **ranking** is wrong for some subpopulation. CartPace keeps one calibration offset per stratum, learned from propensity-weighted delayed labels, and paces the budget against the corrected score. It changes the composition of the referred set without changing its size.

Making those offsets identifiable requires referring some patients below the threshold, and those referrals are paid for out of the same hard budget being optimised. That coupling is the contribution.

## Documents

| File | Contents |
|---|---|
| `project.md` | Requirements, objective, architecture, acceptance criteria, out-of-scope, riskiest assumptions |
| `docs/CartPace-Build-Specification.pdf` | Full build plan, Phase 0–13, each with an exit gate; patent strategy; risk register |
| `docs/prior-art.md` | W0 clearance: element-by-element prior art analysis and the proceed-narrowed decision |
| `docs/p2-findings.md` | **The gate result.** What works, what does not, and the four bugs found |
| `docs/clean-install.md` | Clean-clone verification, AC12 |
| `modular-plan.md` | Module map and interfaces, as built, with divergences from the plan |
| `docs/environment.md` | Verified toolchain versions |

## Setup

```bash
python -m venv .venv
. .venv/Scripts/activate      # Windows;  source .venv/bin/activate on Unix
pip install -r requirements.txt
cp .env.example .env          # then generate JWT_SECRET as the file describes
pytest                        # 116 tests
python spike_p2.py            # the gate
python bench/footprint.py     # memory and latency evidence -- run alone, not
                               # alongside another CPU-bound process
python -m backend.seed        # seeds nurse / supervisor demo accounts
uvicorn backend.main:app      # starts the API on :8000
```

Verified on a genuinely fresh clone of the remote with a new venv --
see `docs/clean-install.md`.

No GPU required. No model weights required — the synthetic scorer is the default, and absent weights fall back to it rather than failing.

## Roadmap

| Phase | Gate |
|---|---|
| W0 | Prior art clearance. No code. |
| W1 | `controller/` + `sim/`, then `spike_p2.py` — **done, NO-GO as written** |
| W2 | Benchmarks, backend, walking skeleton |
| W3 | Frontend, integration, end-to-end |
| W4 | Monthly budget pool, provisional draft, audits, clean-environment test |

## Notes

Datasets, if used, are public only, with licence and version recorded in `docs/dataset.md`. Splits are patient-level, never image-level.

This repository contains unfiled patent subject matter. Nothing here is to be published, preprinted, presented or made public before a filing date exists.
