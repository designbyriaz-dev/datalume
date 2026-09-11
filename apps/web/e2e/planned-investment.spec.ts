import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 step 47 "View planned replacement intelligence" — a real,
// weighted, fully explainable scoring engine (planned_investment.py)
// that was fully built and wired into ComponentDetailClient.tsx but
// had no way for a user to actually drive it: the API always accepted
// installation_date/expected_life_years (the AGE_RATIO factor's whole
// input, the largest single weight at 0.35), but the "Add a component"
// form never exposed them, so AGE_RATIO was permanently
// applicable=false for every component anyone could create through the
// UI. Added those two fields to components/page.tsx alongside this
// spec, closing the "backend built, UI incomplete" gap rather than
// writing a test that could only ever exercise the "no data" path.
test("a component's real age drives a non-trivial planned investment score", async ({ page }) => {
  await signUp(page, "E2E Lifecycle Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Ageing Boiler Co");
  // Well past its expected life regardless of what today's date is —
  // the AGE_RATIO factor clamps ratio > 1 to 1.0, so this reliably
  // produces the maximum age signal without a brittle date/today math
  // dependency in the assertion below.
  await page.locator("#component-installation-date").fill("2005-01-01");
  await page.locator("#component-expected-life").fill("10");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(page.getByText("E2E Ageing Boiler Co")).toBeVisible();
  await page.getByRole("row", { name: /E2E Ageing Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await expect(page.getByText("Planned investment priority")).toBeVisible();
  await page.getByText("Planned investment priority").click();
  await expect(page.getByText(/years old of an expected 10-year life/)).toBeVisible();
  await expect(page.getByText(/0 repair\(s\) in the last/)).toBeVisible();
  await expect(page.getByText("No repeat-failure signal currently flagged")).toBeVisible();
  await expect(page.getByText("No open compliance actions")).toBeVisible();
});
