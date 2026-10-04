import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77: "Identify repeat repairs" — repeat_repair.py's
// repeat_repairs_for_property (threshold 3 within a 12-month window)
// and its repairs-page display have always been real, and
// repeat-component-failure.spec.ts already proves the sibling
// component-level signal (repeat_failures_for_component), but no spec
// ever created enough repairs against the same *property* (with no
// component at all) to trigger this one.
test("three repairs against one property trigger the repeat-repair signal", async ({ page }) => {
  await signUp(page, "E2E Property Repeat Repair Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Property Repeat Repair Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Property Repeat Repair Unit")).toBeVisible();

  await page.goto("/repairs");
  await expect(async () => {
    await page.getByLabel("Property").selectOption({ label: "E2E Property Repeat Repair Unit" });
    await expect(page.getByLabel("Property").locator("option:checked")).toHaveText("E2E Property Repeat Repair Unit");
  }).toPass({ timeout: 10_000 });

  for (let i = 1; i <= 3; i++) {
    await page.locator("#repair-category").fill("Damp");
    await page.locator("#repair-description").fill(`Damp issue ${i}`);
    await page.getByRole("button", { name: "Report" }).click();
    await expect(page.locator("li", { hasText: `Damp issue ${i}` })).toBeVisible({ timeout: 10_000 });
  }

  await expect(page.getByText(/3 repairs in the last 12 months \(threshold 3\)/)).toBeVisible();
});
