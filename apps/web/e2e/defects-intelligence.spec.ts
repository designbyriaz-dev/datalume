import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// GET /api/v1/defects/intelligence (app/development/defects_intelligence.py,
// spec §35) has always been real and tested — open/overdue/warranty-related
// counts, cost totals, repeat-category detection — but the systematic
// api.ts audit that found this found zero frontend callers anywhere.
// BuildingDetailClient.tsx only ever rendered the raw listDefects
// register, no summary. Added the exact same KPI-card-row pattern
// /repairs/page.tsx already uses for its own intelligence endpoint, plus
// a repeat-category callout list. This proves it's wired to the real
// backend, not placeholder UI: two defects of the same category against
// the same building is exactly what get_defects_intelligence's own
// location/category grouping flags as a repeat pattern.
test("the building page surfaces real defects intelligence, including a repeat-category pattern", async ({ page }) => {
  await signUp(page, "E2E Defects Intelligence Org");

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E Defects Intelligence Block");
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByRole("row", { name: /E2E Defects Intelligence Block/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/buildings\/.+/);

  // No defects yet — the intelligence panel shouldn't render at all
  // rather than show an all-zero KPI row nobody asked to see.
  await expect(page.getByText("Total Defects")).not.toBeVisible();

  for (let i = 1; i <= 2; i++) {
    await page.locator("#defect-category").fill("Water ingress");
    await page.locator("#defect-description").fill(`Damp patch ${i}`);
    await page.locator("#defect-severity").selectOption("HIGH");
    await page.getByRole("button", { name: "Report" }).click();
    await expect(page.getByText(`Damp patch ${i}`)).toBeVisible();
  }

  await expect(page.getByText("Total Defects")).toBeVisible();
  // Each KpiStatCard is its own small card — one level up from the
  // label scopes to just that card, not the whole KPI row.
  await expect(page.getByText("Total Defects").locator("xpath=..")).toContainText("2");
  await expect(page.getByText("Open", { exact: true }).locator("xpath=..")).toContainText("2");

  // Both defects share one location (this building), so repeat-category
  // detection counts it as 1 location with a repeat pattern — not 2.
  // The category name is wrapped in curly quotes (&ldquo;/&rdquo;) by
  // the component, not straight ones.
  await expect(page.getByText(/1 location with repeat .Water ingress. defects/)).toBeVisible();
});
