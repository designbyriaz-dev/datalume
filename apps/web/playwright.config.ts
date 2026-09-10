import { defineConfig, devices } from "@playwright/test";

// A real, first E2E suite — spec §76-78 names 50 New Build acceptance
// steps as the eventual target; this covers a handful of genuine
// end-to-end journeys (auth, the development->building->property
// golden thread, Ask DataLume) rather than claiming full coverage.
// STATUS.md's "Not yet done" list is updated to reflect exactly this,
// not more.
//
// Both servers run against the smoketest pattern used throughout this
// build's own manual verification (SQLite + in-process fake Redis, no
// Docker/Postgres/real Redis needed) — see
// apps/api/scripts/run_smoketest_server.py.

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // every spec signs up a fresh org against the same shared smoketest DB — parallel runs would race
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3100",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      // Invokes the venv's own python directly (not `python3` off
      // PATH) so this works whether or not the venv is "activated" in
      // the shell Playwright itself was launched from — the same
      // .venv/bin/python invocation used throughout this build's own
      // manual verification. The venv must already exist
      // (`pip install -e ".[dev]"` in apps/api) — this doesn't create
      // it, same as CI's own separate api install step.
      command:
        "../api/.venv/bin/python scripts/run_smoketest_server.py --port 8000 --db-path e2e-smoketest.db --fresh",
      cwd: "../api",
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      cwd: __dirname,
      url: "http://localhost:3100",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
