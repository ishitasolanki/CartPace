# CartPace — frontend

React + Vite + TypeScript + Tailwind, per `project.md` section 11.

## Setup

```bash
npm install
cp .env.example .env   # VITE_API_BASE, default http://localhost:8000
npm run dev             # http://localhost:5173
```

The backend must be running separately (`uvicorn backend.main:app`) — see the
repository root README.

## Structure

| Path | Contents |
|---|---|
| `src/pages/` | `Login`, `Live`, `Compare` — the three pages per `modular-plan.md` |
| `src/components/` | `BudgetGauge`, `OffsetChart`, `FNRCertificate`, `ExploreSplit`, `PatientFeed`, `BaselineTable`, `StatCard` |
| `src/lib/api.ts` | Fetch wrapper — attaches the JWT, throws `ApiError` with a real message |
| `src/lib/useWebSocket.ts` | Reconnect with backoff; the backend does not replay history, so `onReconnect` exists to refetch state over REST and close the gap |
| `src/lib/derive.ts` | Pure logic pulled out of `Live.tsx` so it can be unit-tested — the explore/exploit split lives here after a real bug was found in it live |
| `src/lib/AuthContext.tsx` | Token + current-user state |

## Testing

```bash
npm run test        # Vitest, once
npm run test:watch  # Vitest, watch mode
npx tsc --noEmit     # typecheck
npm run build        # production build
```

`src/lib/derive.test.ts` carries a named regression test for a bug caught by
manual end-to-end testing rather than by any unit test written in advance:
computing the explore/exploit split by propensity range alone (without also
requiring `refer === true`) produced "434.3% exploratory" against a day that
had spent 35 of 40 cartridges — mathematically impossible, and only visible by
actually running the pipeline live.

## Design notes

- `OffsetChart` is the centrepiece: the per-stratum calibration offsets
  climbing away from zero as delayed labels land is the mechanism the whole
  project is about, made visible.
- `Compare` is gated to `supervisor` at the **route** level only — per
  `project.md` section 4's "sees" column, not as a hard security boundary; the
  API itself does not restrict `/compare` (see `backend/routes/stats.py`).
- Nothing here is a diagnostic or triage interface. Per the section 3(i)
  drafting discipline in `docs/CartPace-Build-Specification.pdf`, this reads
  throughout as a consumable-inventory and resource-allocation dashboard.
