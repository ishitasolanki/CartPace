"""GET /api/scenarios -- available scenario configurations.

No PUT /api/config/budget in this cut: budget is set per-run at creation
(RunCreate does not carry a scenario-level override) rather than mutated on a
live run, since the controller's pacer already reads the day's budget from the
scenario and a supervisor changing it mid-run would race the running loop.
Recorded here rather than silently dropped -- see project.md out-of-scope.
"""

from fastapi import APIRouter, Depends

from backend.deps import current_user
from sim.scenarios import SCENARIOS

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/scenarios")
def list_scenarios(_=Depends(current_user)):
    return {
        name: {
            "budget": cfg.budget,
            "shortage_budget": cfg.shortage_budget,
            "shortage_prob": cfg.shortage_prob,
            "delay": cfg.delay,
            "rank_drift_stratum": cfg.rank_drift_stratum,
        }
        for name, cfg in SCENARIOS.items()
    }
