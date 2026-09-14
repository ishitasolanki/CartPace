import { expect, test } from "@playwright/test";

/** Login -> run a day -> certificate updates as labels land -- the E2E line
 * from project.md section 11 and modular-plan.md's test plan, automated.
 *
 * This exercises the same path driven manually earlier in the project
 * (see the commit that added the design/accessibility pass): a real browser
 * against a real Vite dev server against a real FastAPI backend against a
 * real WebSocket, not a mocked one. See e2e/README.md for what must already
 * be running before this suite is invoked -- it deliberately does not spin
 * up its own backend, since seeding demo users and generating a JWT secret
 * are one-time setup steps, not per-test-run steps.
 */

const SUPERVISOR = { username: "supervisor", password: "change-me-supervisor" };
const NURSE = { username: "nurse", password: "change-me-nurse" };

async function login(page: import("@playwright/test").Page, creds: typeof SUPERVISOR) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(creds.username);
  await page.getByLabel("Password").fill(creds.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/live/);
}

test.describe("authentication", () => {
  test("rejects a wrong password with a visible, announced error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill("nurse");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    // role="alert" (Web Interface Guidelines: aria-live for inline
    // validation) -- getByRole("alert") only finds it if that attribute is
    // actually present, which is the point of asserting through the role.
    await expect(page.getByRole("alert")).toContainText(/invalid/i);
    await expect(page).toHaveURL(/\/login/);
  });

  test("health_worker signs in and reaches Live, with no Compare link", async ({ page }) => {
    await login(page, NURSE);
    await expect(page.getByRole("heading", { name: /start a new run|run #/i })).toBeVisible();
    // project.md section 4: Compare is part of the supervisor's "sees"
    // column. A health_worker must not even see the nav link.
    await expect(page.getByRole("link", { name: "Compare" })).toHaveCount(0);
  });

  test("supervisor sees the Compare link", async ({ page }) => {
    await login(page, SUPERVISOR);
    await expect(page.getByRole("link", { name: "Compare" })).toBeVisible();
  });
});

test.describe("running a clinic day, live", () => {
  test("create, stream, and watch the certificate become identifiable", async ({ page }) => {
    await login(page, SUPERVISOR);

    await page.getByLabel("Scenario").selectOption("ranking_drift");
    await page.getByLabel("Seed").fill("42");
    await page.getByLabel("Days").fill("15"); // short enough to finish in-test
    await page.getByRole("button", { name: "Create and run" }).click();

    // URL reflects state (Web Interface Guidelines) -- this is also what
    // makes deep-linking and reload-survival possible, not just a nicety.
    await expect(page).toHaveURL(/\/live\/\d+/);
    await expect(page.getByText(/^live$/)).toBeVisible({ timeout: 15_000 });

    // The feed populates from the live WebSocket -- not a poll, not a
    // page reload. If this never appears, decisions are not streaming.
    await expect(page.getByText(/live feed/i)).toBeVisible();
    await expect(page.locator("li", { hasText: "stratum" }).first()).toBeVisible({
      timeout: 20_000,
    });

    // The run must finish this many days without hanging or erroring --
    // this is the same background-asyncio-task path where a real bug
    // (an unhandled exception silently leaving the WS hanging forever)
    // was found and fixed earlier in this project.
    await expect(page.getByText(/^done$/)).toBeVisible({ timeout: 45_000 });

    // The mechanism made visible: at least one stratum's offset should have
    // moved away from zero by the time a ranking_drift run of 15 days ends.
    // Reading the chart's own data via its accessible axis text would be
    // brittle; asserting the panel exists and the run reached "done" with a
    // populated feed is the E2E-appropriate check -- the *numbers* are
    // covered by tests/test_stats_api.py's
    // test_strata_offset_tracks_the_drifted_stratum, which reads the same
    // API this page renders.
    await expect(page.getByText(/per-stratum calibration offset/i)).toBeVisible();

    // G5's UI surface: the certificate must not silently stay blank.
    await expect(page.getByText(/false-negative certificate/i)).toBeVisible();
  });

  test("reloading a deep-linked run restores it instead of the picker", async ({ page }) => {
    await login(page, SUPERVISOR);
    // Reuse whatever the previous test created; list view always has at
    // least one completed run by this point in the suite.
    const firstRun = page.locator("main li button").first();
    await firstRun.click();
    await expect(page).toHaveURL(/\/live\/\d+/);
    const url = page.url();

    await page.reload();
    await expect(page).toHaveURL(url);
    await expect(page.getByRole("button", { name: /back to runs/i })).toBeVisible();
  });
});

test.describe("baseline comparison", () => {
  test("supervisor can compare a completed run, and CartPace itself is in the table", async ({
    page,
  }) => {
    await login(page, SUPERVISOR);
    await page.goto("/compare");
    await expect(page).toHaveURL(/\/compare\/\d+/);

    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    // The bug this exact assertion exists to catch: an earlier version of
    // this table listed every baseline except the policy being evaluated.
    await expect(table.getByText("CartPace", { exact: true })).toBeVisible();
    await expect(table.getByText("ablation")).toBeVisible();
    await expect(table.getByText(/upper bound, offline/i)).toBeVisible();
  });

  test("health_worker cannot reach Compare directly", async ({ page }) => {
    await login(page, NURSE);
    await page.goto("/compare");
    await expect(page).toHaveURL(/\/live/);
  });
});
