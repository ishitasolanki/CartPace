"""Running a policy over a stream, and scoring it honestly.

The primary metric is **cases confirmed, with cartridges spent always reported
alongside**. Cases per cartridge is deliberately not an acceptance criterion:
it is a ratio that rewards referring almost nobody, and the full-lookahead
oracle loses on it while catching hundreds more people.

Where two policies spend different amounts, "better" means more cases without
more cartridges. `beats()` encodes exactly that and refuses to call a win when
the extra cases were simply bought with extra spend.
"""

from dataclasses import dataclass, field

import numpy as np

from sim.labels import DelayedLabels


@dataclass
class RunResult:
    policy: str
    caught: int = 0
    spent: int = 0
    cases: int = 0
    patients: int = 0
    explore_spend: int = 0
    exhausted_days: int = 0
    missed: int = 0                 # cases never referred -- the sim's truth
    offsets: list = field(default_factory=list)   # per-day snapshot, diagnostics

    @property
    def realised_fnr(self) -> float:
        """Ground truth the certificate is trying to estimate."""
        return self.missed / max(self.cases, 1)

    @property
    def recall(self) -> float:
        return self.caught / max(self.cases, 1)

    @property
    def per_cartridge(self) -> float:
        """Secondary only. Never a gate -- see the module docstring."""
        return self.caught / max(self.spent, 1)

    @property
    def explore_share(self) -> float:
        return self.explore_spend / max(self.spent, 1)


def run(policy, days, delay: int, name: str = "") -> RunResult:
    """Stream `days` through `policy`, delivering labels after `delay` days."""
    res = RunResult(policy=name or type(policy).__name__)
    queue = DelayedLabels(delay=delay)

    for day in days:
        policy.start_day(day.budget)
        res.cases += int(day.labels.sum())
        res.patients += day.n

        for i in range(day.n):
            d = policy.decide(float(day.scores[i]), int(day.strata[i]),
                              float(day.times[i]))
            if not d.refer:
                res.missed += int(day.labels[i])
            if d.refer:
                res.caught += int(day.labels[i])
                res.spent += 1
                if d.propensity < 1.0:
                    res.explore_spend += 1
                queue.record(stratum=int(day.strata[i]), propensity=d.propensity,
                             score=float(day.scores[i]), label=int(day.labels[i]))

        # FR3 is a hard invariant, not an aspiration. Assert it every day.
        assert policy.spent_today <= day.budget, (
            f"BUDGET VIOLATED: spent {policy.spent_today} of {day.budget}")
        if policy.budget_left == 0:
            res.exhausted_days += 1

        policy.observe_labels(queue.end_day())
        policy.end_day(day.n)

        if hasattr(policy, "offsets"):
            res.offsets.append(policy.offsets)

    return res


def run_oracle(days, use_risk: bool = False) -> RunResult:
    from .baselines import top_b_oracle
    name = "TopB oracle (true risk)" if use_risk else "TopB oracle (model score)"
    res = RunResult(policy=name)
    for day in days:
        c, s = top_b_oracle(day, use_risk=use_risk)
        res.caught += c
        res.spent += s
        res.cases += int(day.labels.sum())
        res.patients += day.n
    return res


def beats(a: RunResult, b: RunResult, margin: float = 0.0,
          spend_tol: float = 0.02) -> bool:
    """Did `a` beat `b` on cases *without* buying the win with cartridges?

    Requires more cases by at least `margin` (relative), and spend no more than
    `spend_tol` above `b`. Without the spend condition, any policy could "win"
    by simply spending more, which measures nothing.
    """
    if a.spent > b.spent * (1.0 + spend_tol):
        return False
    return a.caught >= b.caught * (1.0 + margin)


def table(results, oracle=None) -> str:
    rows = list(results)
    if oracle is not None:
        rows = rows + [oracle]
    w = max(len(r.policy) for r in rows) + 2
    out = [f"{'policy':<{w}}{'cases':>8}{'spent':>8}{'recall':>9}"
           f"{'per cart':>10}{'explore':>9}"]
    out.append("-" * len(out[0]))
    for r in rows:
        out.append(f"{r.policy:<{w}}{r.caught:>8}{r.spent:>8}"
                   f"{r.recall:>8.1%}{r.per_cartridge:>10.3f}"
                   f"{r.explore_share:>8.1%}")
    return "\n".join(out)


def mean_result(results, name: str) -> RunResult:
    """Average across seeds. Counts are means, so they are not integers --
    rounded only for display."""
    m = RunResult(policy=name)
    m.caught = int(round(np.mean([r.caught for r in results])))
    m.spent = int(round(np.mean([r.spent for r in results])))
    m.cases = int(round(np.mean([r.cases for r in results])))
    m.patients = int(round(np.mean([r.patients for r in results])))
    m.explore_spend = int(round(np.mean([r.explore_spend for r in results])))
    m.exhausted_days = int(round(np.mean([r.exhausted_days for r in results])))
    m.missed = int(round(np.mean([r.missed for r in results])))
    return m
