# Clean-environment install verification (AC12)

**Date:** 2026-09-12
**Verified against:** `origin/main`, cloned fresh from the actual GitHub
remote (not the working directory) into a temp path, with a brand-new venv.

## Procedure

```bash
git clone https://github.com/ishitasolanki/CartPace.git
cd CartPace
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print('JWT_SECRET='+secrets.token_urlsafe(48))" >> .env
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe spike_p2.py
./.venv/Scripts/python.exe bench/footprint.py
./.venv/Scripts/python.exe -m backend.seed
./.venv/Scripts/python.exe -m uvicorn backend.main:app --port 8123
curl http://127.0.0.1:8123/api/health
curl -X POST http://127.0.0.1:8123/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"nurse","password":"change-me-nurse"}'
```

No GPU. No model weights present or required.

## Result: PASS, with one real gap found and fixed

| Step | Result |
|---|---|
| `pip install -r requirements.txt` | Succeeded, no GPU, no weights |
| `pytest` | **116 passed** |
| `spike_p2.py` | Ran to completion, exit 0 |
| `bench/footprint.py` | **AC7 PASS** (see caveat below) |
| `backend.seed` | `seeded: ['nurse', 'supervisor']` |
| `uvicorn backend.main:app` | Started, `/api/health` → `200 {"status":"ok"}` |
| Login with seeded credentials | `200`, valid JWT issued |

### Gap found: `httpx` and `pytest-timeout` were missing from `requirements.txt`

Both had been installed globally on the development machine at some point and
were never recorded. The clean clone's fresh venv did not have them, and
`pytest` failed at collection with `RuntimeError: The starlette.testclient
module requires the httpx package to be installed` — exactly the class of bug
this check exists to catch: a dependency the dev machine already has silently
satisfies, and a genuinely clean environment does not.

Fixed by adding both to `requirements.txt` with a note that they are test-only
(`TestClient`'s WebSocket support, and a timeout guard against a test hanging
on a background-task bug rather than failing loudly — see the commit that
built the walking skeleton for why that guard exists). Re-verified after the
fix: clean install, clean test run, 116 passed.

### Benchmark note: run it in isolation

`bench/footprint.py` was measured once while `spike_p2.py` was still running
in the background on the same machine, and failed its own latency-flatness
check: mean latency read 71.3 → 155.5us instead of the usual ~58 → ~60us, and
p99 spiked to 2146.7us. Re-run alone immediately after, same clone, same
machine: 58.4 → 76.2us, PASS. The controller was not the variable; CPU
contention was. Recorded in the benchmark's own docstring so this does not get
mistaken for a regression next time. AC7's actual, uncontended result:

```
 decisions   declared B   heap KB   mean us    p99 us
     1,000         4664      24.7      58.4     143.7
   100,000         4664      27.0      76.2     601.4

NFR1 declared state constant              : PASS  (4664 bytes throughout)
NFR1 heap flat over a 100x longer stream  : PASS  (+2.2 KB)
NFR2 per-decision latency bounded, in us  : PASS  (58.4 -> 76.2 us mean, 601.4 us p99)
AC7: PASS
```

## Frontend, verified separately (2026-09-16)

Same discipline: cloned fresh from `origin/main` into a temp path, not the
working directory.

```bash
cd CartPace/frontend
npm ci
cp .env.example .env
npx tsc --noEmit
npm run build
npm run test
```

| Step | Result |
|---|---|
| `npm ci` | 258 packages, 0 vulnerabilities |
| `npx tsc --noEmit` | Clean |
| `npm run build` | Succeeds, `dist/` produced |
| `npm run test` | **16 passed** |

No gap found this time — the design-pass commit's dependency additions
(`react-router-dom` v7, `recharts` 3, Vitest 5, Testing Library) were already
correctly recorded in `package.json`/`package-lock.json`, unlike the backend's
earlier `httpx` miss. `npm ci` (not `npm install`) is what a clean clone
should run — it installs exactly what the lockfile pins and fails loudly on
drift, rather than silently resolving around it.

## Re-verification

Re-run this whole procedure — backend and frontend both — before any patent
filing or graded submission, from a machine that has never held this project,
and update the dates above.
