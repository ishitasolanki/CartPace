import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useWebSocket } from "../lib/useWebSocket";
import type {
  CertificateOut,
  RunOut,
  StratumHistoryPoint,
  WsMessage,
} from "../lib/types";
import { StatCard } from "../components/StatCard";
import { BudgetGauge } from "../components/BudgetGauge";
import { ExploreSplit } from "../components/ExploreSplit";
import { FNRCertificate } from "../components/FNRCertificate";
import { OffsetChart } from "../components/OffsetChart";
import { PatientFeed } from "../components/PatientFeed";
import { N_STRATA } from "../lib/constants";
import { computeExploreSplit } from "../lib/derive";

type DecisionMsg = Extract<WsMessage, { type: "decision" }>;

function RunPicker({
  runs,
  onCreate,
  onSelect,
  busy,
}: {
  runs: RunOut[];
  onCreate: (scenario: string, seed: number, days: number) => void;
  onSelect: (id: number) => void;
  busy: boolean;
}) {
  const [scenario, setScenario] = useState("ranking_drift");
  const [seed, setSeed] = useState(1);
  const [days, setDays] = useState(260);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold text-ink">Start a new run</h2>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              Scenario
            </label>
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {["calm", "prevalence_drift", "ranking_drift", "shortage", "volatile"].map(
                (s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ),
              )}
            </select>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-slate-500">
                Seed
              </label>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-slate-500">
                Days
              </label>
              <input
                type="number"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
          </div>
          <button
            disabled={busy}
            onClick={() => onCreate(scenario, seed, days)}
            className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Starting…" : "Create and run"}
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold text-ink">Recent runs</h2>
        {runs.length === 0 ? (
          <p className="text-sm text-slate-400">No runs yet.</p>
        ) : (
          <ul className="max-h-64 divide-y divide-slate-50 overflow-y-auto">
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => onSelect(r.id)}
                  className="flex w-full items-center justify-between px-1 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span>
                    #{r.id} · {r.scenario} · seed {r.seed}
                  </span>
                  <StatusPill status={r.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: RunOut["status"] }) {
  const map: Record<RunOut["status"], string> = {
    pending: "bg-slate-100 text-slate-500",
    running: "bg-accent/10 text-accent",
    done: "bg-emerald-50 text-emerald-700",
    error: "bg-red-50 text-red-700",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${map[status]}`}>
      {status}
    </span>
  );
}

export function Live() {
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [run, setRun] = useState<RunOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [feed, setFeed] = useState<DecisionMsg[]>([]);
  // Deliberately not the full DayStatOut: a WS day_end frame carries only
  // day/budget/spent (see backend/engine.py's broadcast payload), and
  // fabricating caught/cases as 0 to satisfy that wider type would be a lie
  // sitting in state, even though nothing currently reads those fields.
  const [lastDay, setLastDay] = useState<{ day: number; budget: number; spent: number } | null>(null);
  const [cert, setCert] = useState<CertificateOut | null>(null);
  const [history, setHistory] = useState<StratumHistoryPoint[]>([]);

  const wsRunId = run && (run.status === "running" || run.status === "pending")
    ? run.id
    : null;

  async function refreshRunList() {
    try {
      setRuns(await api.listRuns());
    } catch {
      /* non-fatal for the picker */
    }
  }

  useEffect(() => {
    refreshRunList();
  }, []);

  async function hydrate(runId: number) {
    const [days, c, h] = await Promise.all([
      api.dayStats(runId).catch(() => []),
      api.certificate(runId).catch(() => null),
      api.strataHistory(runId).catch(() => []),
    ]);
    if (days.length) {
      const d = days[days.length - 1];
      setLastDay({ day: d.day, budget: d.budget, spent: d.spent });
    }
    setCert(c);
    setHistory(h);
  }

  async function handleCreate(scenario: string, seed: number, days: number) {
    setError(null);
    setBusy(true);
    try {
      const created = await api.createRun(scenario, seed, days);
      setRun(created);
      setFeed([]);
      setLastDay(null);
      setCert(null);
      setHistory([]);
      await api.startRun(created.id);
      setRun({ ...created, status: "running" });
      refreshRunList();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the run.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelect(id: number) {
    setError(null);
    const r = await api.getRun(id);
    setRun(r);
    setFeed([]);
    await hydrate(id);
    if (r.status === "pending") {
      await api.startRun(id);
      setRun({ ...r, status: "running" });
    }
  }

  function onMessage(msg: WsMessage) {
    if (msg.type === "decision") {
      setFeed((f) => [msg, ...f].slice(0, 300));
    } else if (msg.type === "day_end") {
      setLastDay({ day: msg.day, budget: msg.budget, spent: msg.spent });
      setCert({
        fnr_hat: msg.fnr_hat,
        halfwidth: msg.fnr_halfwidth,
        identifiable: msg.identifiable,
      });
      setHistory((h) => {
        const withoutDay = h.filter((p) => p.day !== msg.day);
        const additions = msg.offsets.map((offset, stratum) => ({
          day: msg.day,
          stratum,
          offset,
          ess: 0,
        }));
        return [...withoutDay, ...additions];
      });
    } else if (msg.type === "run_complete") {
      setRun((r) => (r ? { ...r, status: "done" } : r));
      refreshRunList();
    } else if (msg.type === "error") {
      setError(msg.detail);
      setRun((r) => (r ? { ...r, status: "error" } : r));
    }
  }

  const wsStatus = useWebSocket(wsRunId, onMessage, () => {
    if (run) hydrate(run.id);
  });

  const exploreSpendToday = useMemo(
    () => (lastDay ? computeExploreSplit(feed, lastDay.day).exploreSpend : 0),
    [feed, lastDay],
  );

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {!run ? (
        <RunPicker runs={runs} onCreate={handleCreate} onSelect={handleSelect} busy={busy} />
      ) : (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-semibold text-ink">
                Run #{run.id} · {run.scenario} · seed {run.seed}
              </h1>
              <StatusPill status={run.status} />
              {wsRunId !== null && (
                <span className="text-xs text-slate-400">
                  {wsStatus === "open"
                    ? "live"
                    : wsStatus === "connecting"
                      ? "connecting…"
                      : "reconnecting…"}
                </span>
              )}
            </div>
            <button
              onClick={() => setRun(null)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            >
              ← Back to runs
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Days completed"
              value={lastDay ? String(lastDay.day + 1) : "0"}
              sub={`of ${run.n_days}`}
            />
            <BudgetGauge spent={lastDay?.spent ?? 0} budget={lastDay?.budget ?? 0} />
            <ExploreSplit
              spent={lastDay?.spent ?? 0}
              exploreSpend={exploreSpendToday}
              // The split is derived from the live WS feed alone -- resuming
              // a finished run with an empty feed shows 0/0 honestly, but
              // that reads as a real measurement sitting next to a non-zero
              // cartridge count unless it's labelled. A full fix would fetch
              // the run's decisions on hydrate to recompute this for a
              // resumed view; not done here, since nothing else on this page
              // needs that fetch and it would be sizeable for a long run.
              stale={feed.length === 0 && run.status !== "running"}
            />
            <FNRCertificate cert={cert} />
          </div>

          <OffsetChart history={history} nStrata={N_STRATA} />

          <PatientFeed items={feed} />
        </>
      )}
    </div>
  );
}
