"""Pydantic request/response models. Validation on every body, per
modular-plan.md -- no route accepts an unvalidated dict.
"""

from pydantic import BaseModel, Field

from sim.scenarios import SCENARIOS


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class MeResponse(BaseModel):
    id: int
    username: str
    role: str


class RunCreate(BaseModel):
    scenario: str
    seed: int = Field(ge=0, le=2_000_000_000)
    n_days: int = Field(default=260, ge=1, le=2000)

    def validate_scenario(self) -> None:
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {self.scenario!r}; "
                             f"have {sorted(SCENARIOS)}")


class RunOut(BaseModel):
    id: int
    scenario: str
    seed: int
    n_days: int
    status: str

    model_config = {"from_attributes": True}


class DecisionOut(BaseModel):
    day: int
    seq: int
    refer: bool
    propensity: float
    s_tilde: float
    tau: float
    reason: str
    stratum: int
    true_label: int


class CertificateOut(BaseModel):
    fnr_hat: float | None
    halfwidth: float | None
    identifiable: bool


class StratumOffset(BaseModel):
    stratum: int
    offset: float
    ess: float


class DayStatOut(BaseModel):
    day: int
    budget: int
    spent: int
    caught: int
    cases: int
    explore_spend: int


class PolicySummary(BaseModel):
    """One row of the baseline comparison table."""

    policy: str
    caught: int
    spent: int
    recall: float
    per_cartridge: float
    explore_share: float


class BudgetUpdate(BaseModel):
    budget: int = Field(ge=1, le=1000)
