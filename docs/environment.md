# Verified environment

Recorded 2026-09-10 on the development machine (Windows 11). Verified by running each command, not assumed.

| Item | Command | Result |
|---|---|---|
| Python | `python --version` | 3.11.9 |
| Node | `node --version` | v24.14.1 |
| npm | `npm --version` | 10.1.0 |
| Git | `git --version` | 2.53.0.windows.2 |
| numpy | `python -c "import numpy; print(numpy.__version__)"` | 2.3.3 |
| GPU | `python -c "import torch; print(torch.cuda.is_available())"` | **False** |
| GitHub CLI | `gh --version` | not installed |

## Consequences

**No local CUDA.** Confirms the Colab-only training constraint in `project.md` section 10. Any CXR arm trains on Colab GPU and exports exactly three artefacts; nothing else crosses back.

**No `gh`.** The GitHub remote is created manually through the web interface, then added with `git remote add`. Not a blocker — it is a one-time step.

**Repository location.** `C:\Users\ishit\OneDrive\Desktop\web tech project`, inside a OneDrive-synced folder. This is a settled decision. The previous iteration of this project was destroyed by a sync event with no remote, so the GitHub remote is the only real copy: every working session ends in a push, and nothing is left uncommitted overnight.

## Re-verification

Re-run this table before the Phase 12 clean-environment test, and record any version that has moved.
