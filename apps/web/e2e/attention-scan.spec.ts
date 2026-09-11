import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Cross-Domain Attention Engine (Sprint 21): the scan itself only ever
// ran via the nightly worker job until Post-Sprint-24 added a manual
// "Run scan now" trigger to Home — this is that trigger's first E2E
// coverage. Three repairs of the same category against one property is
// the same repeat-failure pattern app/tests/test_attention.py's own
// worker test uses to get a real signals_created == 1.
test("running a manual scan surfaces a real repeat-failure signal", async ({ page }) => {
  await signUp(page, "E2E Attention Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Attention Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Attention Property")).toBeVisible();

  await page.goto("/repairs");
  for (let i = 0; i < 3; i++) {
    await page.locator("#repair-category").fill("Plumbing");
    await page.locator("#repair-description").fill("Leak under the sink");
    await page.getByRole("button", { name: "Report" }).click();
    await expect(page.getByText(/REP-\d+/).nth(i)).toBeVisible();
  }

  await page.goto("/home");
  await expect(page.getByText("Nothing needs attention right now.")).toBeVisible();

  await page.getByRole("button", { name: "Run scan now" }).click();
  await expect(page.getByText("1 new, 0 updated.")).toBeVisible();
  await expect(page.getByText(/repairs reported against this property/)).toBeVisible();
  await expect(page.getByText("Needs attention (1)")).toBeVisible();
});
