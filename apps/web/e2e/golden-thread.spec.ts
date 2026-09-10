import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// A real (if small) slice of spec §76-78's "New Build" golden thread:
// Development -> Building -> Property, created through the actual UI,
// then confirmed to show up in the portfolio summary the Home
// dashboard reads (architecture 03 §1's own hierarchy, Sprint 6/13).
test("development -> building -> property golden thread shows up in the portfolio", async ({ page }) => {
  await signUp(page, "E2E Golden Thread Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Riverside Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Riverside Gardens")).toBeVisible();

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E Block A");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E Riverside Gardens" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Block A")).toBeVisible();

  await page.goto("/properties");
  await page.getByLabel("Address").fill("Flat 1, E2E Block A");
  await page.getByLabel("Building (optional)").selectOption({ label: "E2E Block A" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Flat 1, E2E Block A")).toBeVisible();

  await page.goto("/home");
  // get_portfolio_summary (Sprint 13) composes counts fresh from the
  // entities just created — "OPERATIONAL: 1" is StatusBadge's own
  // `${key}: ${count}` label format for properties_by_status.
  await expect(page.getByText("OPERATIONAL: 1")).toBeVisible();
  await expect(page.getByText("E2E Riverside Gardens")).toBeVisible();
});
