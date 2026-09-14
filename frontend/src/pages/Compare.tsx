import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { usePageTitle } from "../lib/usePageTitle";
import type { CompareOut, RunOut } from "../lib/types";
import { BaselineTable } from "../components/BaselineTable";

/** Supervisor-only per project.md section 4's "sees" column: baseline
 * comparison is part of what distinguishes a supervisor's view from a
 * health worker's, not a hard security boundary -- the API itself does not
 * restrict this endpoint (routes/stats.py), only the frontend route does. */
export function Compare() {
  const { runId: runIdParam } = useParams();
  const navigate = useNavigate();

  const [runs, setRuns] = useState<RunOut[]>([]);
  const [data, setData] = useState<CompareOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = runIdParam ? Number(runIdParam) : null;

  usePageTitle(selected ? `Compare — Run #${selected}` : "Compare");

  useEffect(() => {
    api
      .listRuns()
      .then((all) => {
        const done = all.filter((r) => r.status === "done");
        setRuns(done);
        // URL is the source of truth: only default to the newest completed
        // run when nothing is already selected via the URL, so a shared or
        // reloaded link is never silently overridden.
        if (!runIdParam && done.length > 0) {
          navigate(`/compare/${done[0].id}`, { replace: true });
        }
      })
      .catch(() => setError("Could not load runs."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selected === null) return;
    setLoading(true);
    setError(null);
    api
      .compare(selected)
      .then(setData)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load the comparison."),
      )
      .finally(() => setLoading(false));
  }, [selected]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-ink">Baseline comparison</h1>
        {runs.length > 0 && (
          <div className="flex items-center gap-2">
            <label htmlFor="compare-run" className="text-xs font-medium text-slate-500">
              Run
            </label>
            <select
              id="compare-run"
              value={selected ?? ""}
              onChange={(e) => navigate(`/compare/${e.target.value}`)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-base sm:text-sm"
            >
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} · {r.scenario} · seed {r.seed}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {runs.length === 0 && !error && (
        <div className="flex h-48 items-center justify-center rounded-lg border border-slate-200 bg-white text-sm text-slate-400">
          No completed runs yet. Finish a run on the Live page first.
        </div>
      )}

      {loading && (
        <div className="flex h-48 items-center justify-center rounded-lg border border-slate-200 bg-white text-sm text-slate-400">
          Loading…
        </div>
      )}

      {!loading && data && <BaselineTable data={data} />}
    </div>
  );
}
