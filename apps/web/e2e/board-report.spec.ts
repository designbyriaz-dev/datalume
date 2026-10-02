import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77 step 17: "Generate management/board reports" — reports.spec.ts
// only ever exercises DEVELOPMENT_SUMMARY; the board-level report types
// (reports/content.py, gated by the reports.board permission every
// signup owner has per auth/rbac.py) had never actually been requested
// or downloaded end-to-end.
test("a board-level report goes from PENDING to READY and downloads", async ({ page }) => {
  await signUp(page, "E2E Board Report Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Board Report Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Board Report Property")).toBeVisible();

  await page.goto("/reports");
  await page.getByLabel("Report").selectOption({ label: "Board Assurance" });
  await page.getByLabel("Format").selectOption({ label: "PDF" });
  await page.getByRole("button", { name: "Generate report" }).click();

  await expect(page.getByText("PENDING")).toBeVisible();
  await expect(page.getByText("READY")).toBeVisible({ timeout: 20_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("board_assurance.pdf");
});
