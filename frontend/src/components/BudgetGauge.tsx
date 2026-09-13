/** Cartridge burn-down for the current day: budget hard-caps referrals, and
 * the whole point of pacing is to spend it evenly rather than exhausting it
 * by mid-morning (the greedy-baseline failure mode this project exists to
 * fix) or leaving it unspent at close. */
export function BudgetGauge({
  spent,
  budget,
}: {
  spent: number;
  budget: number;
}) {
  const pct = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
  const exhausted = spent >= budget && budget > 0;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Today's cartridges
        </span>
        <span className="text-sm font-semibold tabular-nums text-ink">
          {spent} / {budget}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            exhausted ? "bg-warn" : "bg-accent"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {exhausted && (
        <p className="mt-2 text-xs text-warn">
          Budget exhausted — remaining arrivals cannot be referred today.
        </p>
      )}
    </div>
  );
}
