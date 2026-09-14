# E2E tests

Real browser, real Vite dev server, real FastAPI backend, real WebSocket.
Nothing here is mocked — that is the point of an E2E suite living alongside
`Vitest` unit tests rather than replacing them.

## Prerequisites (start these first, in two terminals)

```bash
# Terminal 1 -- backend, from the repo root
cd ..
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
CORS_ORIGIN=http://localhost:5173 JWT_SECRET=$JWT_SECRET python -m backend.seed
CORS_ORIGIN=http://localhost:5173 JWT_SECRET=$JWT_SECRET python -m uvicorn backend.main:app --port 8000

# Terminal 2 -- frontend
npm run dev
```

Not automated into `playwright.config.ts`'s `webServer` option deliberately:
the backend needs a generated `JWT_SECRET` and a one-time seed step
(`python -m backend.seed`, creating the `nurse` / `supervisor` demo accounts
this suite logs in as) before it can serve a single request, and Playwright's
`webServer` is built for "start a static server," not "provision an app."
Two terminals, started once per session, is simpler than teaching Playwright
to orchestrate a Python process it was never meant to manage.

## Run

```bash
npx playwright test
npx playwright test --ui     # interactive
```

## What it covers

- Login: wrong password shows an announced (`role="alert"`) error; each role
  reaches the page its role entitles it to and no further (`nurse` never
  sees a Compare link; navigating there directly redirects away).
- A full run, start to finish, over the real WebSocket: create, watch the
  live feed populate, watch it reach `done`, confirm the certificate and
  offset panels render. This is the path where a real bug — an unhandled
  exception in the background asyncio task silently leaving every client
  hanging forever — was found earlier in this project. If that regresses,
  this test times out rather than passing quietly.
- Deep-linking: reloading `/live/:runId` restores the same run rather than
  dropping back to the picker.
- `/compare` includes CartPace itself, not just its baselines — the bug
  found and fixed when this dashboard was first driven manually in a browser.

Numeric correctness (does the offset actually track the injected drift, does
the certificate bracket the truth) is `tests/test_stats_api.py`'s job, run
against the same API this UI renders. This suite asserts that the UI
*shows* what the API returns and that the real-time pipeline doesn't hang or
silently fail — it is not trying to re-verify the statistics.

## A note on flakiness

This suite streams a real WebSocket against a real backend running a real
background asyncio simulation, all sharing one machine with the test
browser. Building it, every observed failure was checked against its own
captured DOM snapshot (`error-context.md` in `test-results/` on failure) and
in each case the snapshot showed the *correct* state already present — the
assertion had simply been outrun by test-execution timing on a heavily
loaded machine, not by a real bug. The same run passed in under a third of
the time once other heavy processes quieted down.

`playwright.config.ts` sets a generous global `expect` timeout and one retry
to absorb that class of noise. If a failure survives a retry, read its
`error-context.md` before assuming the app is wrong — that file is what
distinguishes "the app was slow" from "the app was wrong," and it is the
first thing to check.
