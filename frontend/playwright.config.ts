import { defineConfig, devices } from "@playwright/test";

/** E2E, per project.md section 11. Runs against the real dev server and the
 * real backend -- see e2e/README.md for why this suite is not started
 * automatically the way the frontend's own dev server is. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  // The dev backend (uvicorn --reload, watching files) and Vite share this
  // machine with the test browser, so a plain 5s default expect timeout
  // flaked on a request that was merely slow, not actually broken -- see
  // the commit that added this suite. Raised once, globally, rather than
  // patched per assertion.
  expect: { timeout: 15_000 },
  fullyParallel: false, // shares one backend + one SQLite file across tests
  forbidOnly: !!process.env.CI,
  // Not masking real bugs: every failure observed while building this suite
  // was verified by hand (checking the failure's own DOM snapshot, which
  // showed the correct state already present) to be test-execution timing
  // under a genuinely overloaded dev machine, not incorrect app behaviour --
  // the same suite reran clean and in a fraction of the time once other
  // heavy processes on the machine quieted down. One retry absorbs that
  // class of noise; it will not turn a real, reproducible failure green.
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
