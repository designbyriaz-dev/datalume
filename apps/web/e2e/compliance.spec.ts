import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Compliance Foundation (Sprint 15): the 21 global compliance domains
// are pre-seeded for every org, not created per-tenant — this picks a
// real one (Gas Safety) rather than creating a throwaway domain, the
// same way a real user would.
test("adding a requirement under a seeded compliance domain shows up in its list", async ({ page }) => {
  await signUp(page, "E2E Compliance Org");

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();

  // "Code"/"Title"/"Add" are all ambiguous getByLabel/getByRole matches
  // here — the "Add a domain" form above uses the same label text and
  // button label for a different field/action — so these go by id
  // directly, and the button by position (requirements form is second
  // on the page).
  await page.locator("#requirement-code").fill("E2E-GAS-001");
  await page.locator("#requirement-title").fill("E2E annual gas safety check");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();

  await expect(page.getByText("E2E-GAS-001")).toBeVisible();
  await expect(page.getByText("E2E annual gas safety check")).toBeVisible();
});
