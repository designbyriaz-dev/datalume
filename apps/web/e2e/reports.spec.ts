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
