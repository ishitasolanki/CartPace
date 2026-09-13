/** Explore vs. exploit split for the current day.
 *
 * The exploratory referrals are the ones paid for out of the same cartridge
 * budget being allocated -- the coupling the patent claim rests on (see
 * project.md section 19 and docs/prior-art.md). Small by design: the P2
 * spike gated it at <=10% of the day's budget (G4). */
export function ExploreSplit({
  spent,
  exploreSpend,
  stale = false,
}: {
  spent: number;
  exploreSpend: number;
  /** True when this split is derived from an empty feed on a resumed view
   * rather than genuinely zero exploration -- see Live.tsx's call site. */
  stale?: boolean;
}) {
  const exploit = Math.max(0, spent - exploreSpend);
  const pct = spent > 0 ? (exploreSpend / spent) * 100 : 0;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Explore vs. exploit
        </span>
        <span className="text-xs text-slate-400">
          {stale ? "not tracked for a resumed view" : `${pct.toFixed(1)}% exploratory`}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        {!stale && (
          <div className="flex h-full">
            <div
              className="h-full bg-accent"
              style={{ width: `${spent > 0 ? (exploit / spent) * 100 : 0}%` }}
            />
            <div className="h-full bg-warn" style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
      <div className="mt-2 flex gap-4 text-xs text-slate-500">
        {stale ? (
          <span>Live only — reopen while the run is streaming to see this.</span>
        ) : (
          <>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent" /> exploit ({exploit})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-warn" /> explore ({exploreSpend})
            </span>
          </>
        )}
      </div>
    </div>
  );
}
