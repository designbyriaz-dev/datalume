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
