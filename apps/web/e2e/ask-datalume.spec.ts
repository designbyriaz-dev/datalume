import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Sprint 22's core guarantee, exercised through the real UI: a
// question no tool can answer must render the fixed "no data" message
// and an explicit "No data" badge — never a guess, never an
// explainability panel for a tool call that didn't happen.
test("an ungrounded question gets the fixed no-data answer, never a guess", async ({ page }) => {
  await signUp(page, "E2E Ask Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Ask Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Ask Property")).toBeVisible();

  await page.goto("/ask");
  await page.getByLabel("Ask about").selectOption({ label: "Property" });
  await page.getByLabel("Record").selectOption({ label: "E2E Ask Property" });
  await page.getByPlaceholder(/Is this compliant/).fill("What's the weather like today?");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText("No data")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/I don't have data/)).toBeVisible();
  // No tool ran, so there's nothing to show the data behind.
  await expect(page.getByText(/Show the data behind this answer/)).not.toBeVisible();
});
