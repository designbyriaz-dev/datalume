import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77 step 9: "Track remedial actions" — api.createComplianceAction
// and the status workflow have always existed (operations/compliance/
// service.py:create_compliance_action), but InspectionsPanel.tsx only
// ever let you complete an existing action, never raise one — no form
// anywhere called the client's own createComplianceAction. Added a
// "+ Raise action" control mirroring HazardActionsPanel's pattern.
test("raising and completing a compliance action against a requirement's applicability", async ({ page }) => {
  await signUp(page, "E2E Compliance Action Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Action Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Action Boiler Co")).toBeVisible();

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();
  await page.locator("#requirement-code").fill("E2E-ACT-001");
  await page.locator("#requirement-title").fill("E2E annual boiler inspection");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();
  await expect(page.getByText("E2E-ACT-001")).toBeVisible();

  await page.goto("/components");
  await page.getByRole("row", { name: /E2E Action Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await page.getByLabel("Requirement").selectOption({ label: "E2E-ACT-001 — E2E annual boiler inspection" });
  await page.getByLabel("Basis").fill("Gas-fired boiler needing an action");
  await page.locator("#applicability-basis").locator("xpath=../..").getByRole("button", { name: "Add" }).click();
  const applicabilityItem = page.locator("li", { hasText: "Gas-fired boiler needing an action" });
  await expect(applicabilityItem).toBeVisible();

  await applicabilityItem.getByRole("button", { name: "+ Raise action" }).click();
  await applicabilityItem.getByLabel("Compliance action description").fill("Replace smoke detector");
  await applicabilityItem.getByLabel("Compliance action deadline").fill("2026-06-01");
  await applicabilityItem.getByRole("button", { name: "Save" }).click();

  await expect(applicabilityItem.getByText(/Replace smoke detector — due 2026-06-01/)).toBeVisible();

  await applicabilityItem.getByRole("button", { name: "complete" }).click();
  await expect(applicabilityItem.getByText(/Replace smoke detector — due 2026-06-01/)).not.toBeVisible();
});
