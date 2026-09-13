import type { CompareOut } from "../lib/types";

/** project.md section 13: the ablation is mandatory in every comparison, not
 * an optional extra baseline -- it is the only row that answers whether the
 * learned component is carrying any weight at all. Never hide it behind a
 * toggle. */
export function BaselineTable({ data }: { data: CompareOut }) {
  const rows = [...data.policies].sort((a, b) => b.caught - a.caught);
  const isAblation = (name: string) => name.includes("ablation");
  const isCartPace = (name: string) => name === "CartPace";

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
            <th className="px-4 py-2 font-medium">Policy</th>
            <th className="px-4 py-2 text-right font-medium">Cases caught</th>
            <th className="px-4 py-2 text-right font-medium">Spent</th>
            <th className="px-4 py-2 text-right font-medium">Recall</th>
            <th className="px-4 py-2 text-right font-medium">Explore share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.policy}
              className={`border-b border-slate-50 last:border-0 ${
                isCartPace(r.policy) ? "bg-accent/5 font-medium" : ""
              }`}
            >
              <td className="px-4 py-2">
                {r.policy}
                {isAblation(r.policy) && (
                  <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                    ablation
                  </span>
                )}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{r.caught}</td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                {r.spent}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                {(r.recall * 100).toFixed(1)}%
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                {(r.explore_share * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
          <tr className="bg-slate-50/60">
            <td className="px-4 py-2 text-slate-500">
              {data.oracle.policy}
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                upper bound, offline
              </span>
            </td>
            <td className="px-4 py-2 text-right tabular-nums text-slate-500">
              {data.oracle.caught}
            </td>
            <td className="px-4 py-2 text-right tabular-nums text-slate-500">
              {data.oracle.spent}
            </td>
            <td className="px-4 py-2 text-right text-slate-300">—</td>
            <td className="px-4 py-2 text-right text-slate-300">—</td>
          </tr>
        </tbody>
      </table>
      <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
        Ranked by cases caught, not cases per cartridge — a ratio the
        full-lookahead oracle can lose on while catching more people. See
        project.md section 8.
      </p>
    </div>
  );
}
