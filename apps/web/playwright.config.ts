import { existsSync } from "node:fs";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// Local dev installs the API into apps/api/.venv (this build's own
// convention throughout, since the system Python here is too old —
// see STATUS.md). CI's `pip install -e ".[dev]"` step has no venv at
// all and installs onto actions/setup-python's own Python, which is
// already first on PATH — a hardcoded ".venv/bin/python" path doesn't
// exist there and fails with exit code 127, exactly the failure this
// guard fixes. Prefer the venv when present, fall back to whatever
// `python3` resolves to otherwise.
const apiVenvPython = path.join(__dirname, "..", "api", ".venv", "bin", "python");
const apiPython = existsSync(apiVenvPython) ? apiVenvPython : "python3";

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
      command: `${apiPython} scripts/run_smoketest_server.py --port 8000 --db-path e2e-smoketest.db --fresh`,
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
