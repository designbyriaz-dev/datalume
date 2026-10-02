import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77 step 14: "Identify component failures" — repeat_repair.py's
// repeat_failures_for_component (threshold 3 within an 18-month window)
// and its repairs-page display have always been real, but
// repair-linked-to-component.spec.ts only ever links one repair to a
// component — never enough to actually trigger the signal.
test("three repairs against one component trigger the repeat-failure signal", async ({ page }) => {
  await signUp(page, "E2E Component Failure Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Component Failure Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Component Failure Property")).toBeVisible();

  await page.goto("/components");
  await expect(async () => {
    await page.getByLabel("Type").selectOption({ label: "Boilers" });
    await expect(page.getByLabel("Type").locator("option:checked")).toHaveText("Boilers");
  }).toPass({ timeout: 10_000 });
  await page.getByLabel("Property (optional)").selectOption({ label: "E2E Component Failure Property" });
  await page.locator("#component-manufacturer").fill("E2E Failure Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("row", { name: /E2E Failure Boiler Co/ })).toBeVisible();

  await page.goto("/repairs");
  await expect(async () => {
    await page.getByLabel("Property").selectOption({ label: "E2E Component Failure Property" });
    await expect(page.getByLabel("Property").locator("option:checked")).toHaveText("E2E Component Failure Property");
  }).toPass({ timeout: 10_000 });
  await expect(page.getByLabel("Component (optional)")).toContainText("Boilers");

  for (let i = 1; i <= 3; i++) {
    await page.getByLabel("Component (optional)").selectOption({ index: 1 });
    await page.locator("#repair-category").fill("Heating");
    await page.locator("#repair-description").fill(`Boiler fault ${i}`);
    await page.getByRole("button", { name: "Report" }).click();
    await expect(page.locator("li", { hasText: `Boiler fault ${i}` })).toBeVisible({ timeout: 10_000 });
  }

  await expect(page.getByText(/3 repair interventions in the last 18 months \(threshold 3\)/)).toBeVisible();
});
