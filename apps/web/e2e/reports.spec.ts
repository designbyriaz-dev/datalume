import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Sprint 23's core guarantee: report generation is a real background
// job (the worker polls every 5s — see playwright.config.ts's second
// webServer), never synchronous in the request. This watches a job
// actually go PENDING -> READY with no page reload, the same behaviour
// verified manually during Sprint 23 itself, then confirms a real file
// downloads.
test("a requested report goes from PENDING to READY and downloads", async ({ page }) => {
  await signUp(page, "E2E Reports Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Reports Development");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Reports Development")).toBeVisible();

  await page.goto("/reports");
  await page.getByLabel("Report").selectOption({ label: "Development Summary" });
  await page.getByLabel("Format").selectOption({ label: "CSV" });
  await page.getByRole("button", { name: "Generate report" }).click();

  await expect(page.getByText("PENDING")).toBeVisible();

  // The page's own 3s poll picks up the worker's 5s tick — give this
  // real room rather than a tight timeout, since it's asserting on an
  // actual background job, not a mocked instant result.
  await expect(page.getByText("READY")).toBeVisible({ timeout: 20_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("development_summary.csv");
});

// HANDOVER_READINESS is a real, backend-tested report type (app/
// reports/content.py's build_handover_readiness_report, covered by
// app/tests/test_reports.py) that never had its own Playwright spec —
// STATUS.md's own words: "the 50-step acceptance suite as a whole
// still covers a real first slice, not every step." Same background-
// job shape as the Development Summary test above, just a different
// report type and format (PDF here, CSV there), and — unlike
// BOARD_ASSURANCE/COMPLIANCE_EXECUTIVE_SUMMARY — no building/property
// filter fields to fill in first.
test("a Handover Readiness report generates and downloads as PDF", async ({ page }) => {
  await signUp(page, "E2E Handover Report Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Handover Report Development");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Handover Report Development")).toBeVisible();

  await page.goto("/reports");
  await page.getByLabel("Report").selectOption({ label: "Handover Readiness" });
  await page.getByLabel("Format").selectOption({ label: "PDF" });
  await page.getByRole("button", { name: "Generate report" }).click();

  await expect(page.getByText("PENDING")).toBeVisible();
  await expect(page.getByText("READY")).toBeVisible({ timeout: 20_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("handover_readiness.pdf");
});

// COMPLIANCE_EXECUTIVE_SUMMARY is the other reports.board-gated report
// type (app/reports/content.py's build_compliance_executive_summary_
// report, covered by test_reports.py's permission test) that had no
// E2E coverage — board-report.spec.ts only ever exercised its sibling,
// Board Assurance. Leaving Building/Property at their "Whole portfolio"
// default (same as the already-tested backend request shape with no
// building_id/property_id) rather than picking one, since scoping
// itself isn't what this test is proving.
test("a Compliance Executive Summary report generates and downloads as PDF", async ({ page }) => {
  await signUp(page, "E2E Compliance Report Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Compliance Report Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Compliance Report Property")).toBeVisible();

  await page.goto("/reports");
  await page.getByLabel("Report").selectOption({ label: "Compliance Executive Summary" });
  await page.getByLabel("Format").selectOption({ label: "PDF" });
  await page.getByRole("button", { name: "Generate report" }).click();

  await expect(page.getByText("PENDING")).toBeVisible();
  await expect(page.getByText("READY")).toBeVisible({ timeout: 20_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("compliance_executive_summary.pdf");
});

// COMMERCIAL_PORTFOLIO is the fifth and last report type
// (build_commercial_portfolio_report) and had no E2E coverage either —
// its period is a fixed "current month to date" the page computes
// itself (ReportsPage's NEEDS_PERIOD branch is read-only, not a form
// field), so this only needs a real lease + rent obligation on the
// books, same UI flow as commercial-arrears.spec.ts, for the report to
// have real collection-rate content to show.
test("a Commercial Portfolio report generates and downloads as CSV", async ({ page }) => {
  await signUp(page, "E2E Commercial Report Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Commercial Report Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Commercial Report Unit")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Commercial Report Tenant Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Commercial Report Tenant Ltd")).toBeVisible();

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Commercial Report Unit" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Commercial Report Tenant Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText(/LSE-\d+/)).toBeVisible();

  const today = new Date();
  const periodStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
  await page.goto("/rent-and-payments");
  await page.getByLabel("Type").selectOption({ label: "RENT" });
  await page.getByLabel("Due date").fill(periodStart);
  await page.getByLabel("Period start").fill(periodStart);
  await page.getByLabel("Period end").fill(today.toISOString().slice(0, 10));
  await page.locator("#obligation-amount").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();

  await page.goto("/reports");
  await page.getByLabel("Report").selectOption({ label: "Commercial Portfolio" });
  await page.getByLabel("Format").selectOption({ label: "CSV" });
  await page.getByRole("button", { name: "Generate report" }).click();

  await expect(page.getByText("PENDING")).toBeVisible();
  await expect(page.getByText("READY")).toBeVisible({ timeout: 20_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("commercial_portfolio.csv");
});
