import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77 step 5: "Calculate Data Health" — data_health/rules.py runs
// 14 deterministic checks on every read (run_data_health_checks),
// surfaced on /home as a KPI card and per-property on the property
// detail page, but neither had ever been exercised end-to-end. Adding a
// property with no type and no postcode deliberately fails
// MISSING_PROPERTY_TYPE and MISSING_POSTCODE, so the score is
// guaranteed to drop below 100% and both findings are guaranteed to
// appear — not a guess at whatever demo data happens to contain.
test("an incomplete property drags down the Data Health score and lists real findings", async ({ page }) => {
  await signUp(page, "E2E Data Health Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Data Health Property");
  await page.getByRole("button", { name: "Add" }).click();
  const propertyRow = page.getByRole("row", { name: /E2E Data Health Property/ });
  await expect(propertyRow).toBeVisible();

  await page.goto("/home");
  const dataHealthCard = page.getByText("Data Health Score", { exact: true }).locator("..");
  await expect(dataHealthCard).toContainText("%");
  await expect(dataHealthCard).not.toContainText("100%");

  await page.goto("/properties");
  // The address itself isn't a link — only the Reference cell
  // (PROP-000001) is.
  await page.getByRole("row", { name: /E2E Data Health Property/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/properties\/.+/);
  await expect(page.getByText(/has no property type recorded\./)).toBeVisible();
  await expect(page.getByText(/has no postcode recorded\./)).toBeVisible();
});
