import type { WsMessage } from "../lib/types";

type FeedItem = Extract<WsMessage, { type: "decision" }>;

const REASON_STYLE: Record<string, { label: string; className: string }> = {
  above_threshold: { label: "referred", className: "bg-emerald-50 text-emerald-700" },
  explore: { label: "explored", className: "bg-warn/10 text-warn" },
  below_floor: { label: "not referred", className: "bg-slate-100 text-slate-500" },
  budget_exhausted: { label: "budget exhausted", className: "bg-red-50 text-red-700" },
};

/** The live per-patient decision feed. Newest first, capped so the DOM
 * doesn't grow without bound over a long run -- the controller is O(1) in
 * memory and the feed watching it should not be the thing that isn't. */
export function PatientFeed({ items }: { items: FeedItem[] }) {
  if (items.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-sm text-slate-400">
        No decisions yet — start a run to see the feed.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        Live feed
      </div>
      <ul className="max-h-72 divide-y divide-slate-50 overflow-y-auto">
        {items.map((d, i) => {
          const style = REASON_STYLE[d.reason] ?? REASON_STYLE.below_floor;
          return (
            <li
              key={`${d.day}-${d.seq}-${i}`}
              className="flex items-center justify-between px-4 py-2 text-sm"
            >
              <span className="text-slate-500">
                day {d.day} · patient {d.seq} · stratum {d.stratum}
              </span>
              <span className="flex items-center gap-2 tabular-nums text-slate-400">
                p={d.propensity.toFixed(3)}
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}
                >
                  {style.label}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
