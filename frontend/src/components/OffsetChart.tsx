import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { StratumHistoryPoint } from "../lib/types";

/** The mechanism made visible.
 *
 * Each line is one stratum's learned logit-space offset over the run.
 * Under `calm` every line should sit near zero -- the offsets converge to no
 * correction when there is nothing to correct (project.md section 3.2's
 * degeneracy property). Under `ranking_drift` one line visibly climbs away
 * from zero: that is the controller discovering, from delayed and censored
 * feedback alone, that the frozen model under-scores that subpopulation, and
 * correcting for it in real time.
 *
 * This is deliberately not the raw score distribution or a threshold chart --
 * those show pacing, which the earlier P1 spike found does all the work on
 * its own. This chart shows the one thing pacing cannot do.
 */

const COLORS = [
  "#0f6466",
  "#c9a227",
  "#7c5cbf",
  "#2f7dd1",
  "#d1495b",
  "#3c9c6e",
  "#b5651d",
  "#5a6b8c",
];

export function OffsetChart({
  history,
  nStrata,
}: {
  history: StratumHistoryPoint[];
  nStrata: number;
}) {
  const byDay = new Map<number, Record<string, number>>();
  for (const p of history) {
    const row = byDay.get(p.day) ?? { day: p.day };
    row[`s${p.stratum}`] = p.offset;
    byDay.set(p.day, row);
  }
  const data = [...byDay.values()].sort((a, b) => a.day - b.day);

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-slate-200 bg-white text-sm text-slate-400">
        Waiting for the first day to complete…
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
        Per-stratum calibration offset
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Zero means the frozen model is trusted as-is for that group. A line
        moving away from zero is the controller correcting a subpopulation it
        has learned the model under- or over-scores.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="day"
            tick={{ fontSize: 11, fill: "#94a3b8" }}
            label={{ value: "day", position: "insideBottom", offset: -2, fontSize: 11 }}
          />
          <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} width={40} />
          <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="2 2" />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
            labelFormatter={(d) => `day ${d}`}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {Array.from({ length: nStrata }, (_, k) => (
            <Line
              key={k}
              type="monotone"
              dataKey={`s${k}`}
              name={`stratum ${k}`}
              stroke={COLORS[k % COLORS.length]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
