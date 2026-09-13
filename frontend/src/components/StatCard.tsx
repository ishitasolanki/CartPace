/** A small labelled number, used across the dashboard for budget/cases/etc.
 * One shared component so every stat looks the same rather than each panel
 * inventing its own spacing. */
export function StatCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "warn" | "accent";
}) {
  const toneClass =
    tone === "warn"
      ? "text-warn"
      : tone === "accent"
        ? "text-accent"
        : "text-ink";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}
