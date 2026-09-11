import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Closes the last remaining gap in Planned Investment Intelligence
// (spec §76 step 47): CONDITION_SIGNAL is real UI-testable now too —
// no tool/UI gap on the ask side this time, but ComponentDetailClient.tsx
// had no compliance/inspection section at all, even though
// list_compliance_statuses_for_entity and the Inspection table already
// support entity_type="component" (get_compliance_status's own
// applicable_entity_types names it). Extracted the Building page's
// InspectionsPanel into a shared component and added the same
// "Add a compliance requirement" + applicability list it already used,
// scoped to this component instead.
test("recording an inspection against a component drives its CONDITION_SIGNAL factor", async ({ page }) => {
  await signUp(page, "E2E Condition Signal Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Condition Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Condition Boiler Co")).toBeVisible();

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();
  await page.locator("#requirement-code").fill("E2E-COND-001");
  await page.locator("#requirement-title").fill("E2E annual boiler inspection");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();
  await expect(page.getByText("E2E-COND-001")).toBeVisible();

  await page.goto("/components");
  await page.getByRole("row", { name: /E2E Condition Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  // Baseline: no inspection recorded yet, so CONDITION_SIGNAL is
  // inapplicable — the widget shows "not applicable", not a detail
  // string, since ComponentDetailClient.tsx only renders f.detail when
  // f.applicable is true.
  await page.getByText("Planned investment priority").click();
  const conditionFactor = page.locator("li", { hasText: "Latest inspection condition" });
  await expect(conditionFactor).toContainText("not applicable — excluded");

  await page.getByLabel("Requirement").selectOption({ label: "E2E-COND-001 — E2E annual boiler inspection" });
  await page.getByLabel("Basis").fill("Gas-fired boiler");
  // Several "Add" buttons exist on this detail page (specifications,
  // child components) — scope to the compliance form's own container.
  await page.locator("#applicability-basis").locator("xpath=../..").getByRole("button", { name: "Add" }).click();
  const applicabilityItem = page.locator("li", { hasText: "Gas-fired boiler" });
  await expect(applicabilityItem).toBeVisible();

  await applicabilityItem.getByRole("button", { name: "+ Record inspection" }).click();
  await applicabilityItem.getByLabel("Inspector").fill("E2E Inspector");
  await applicabilityItem.getByLabel("Inspection date").fill("2026-01-15");
  await applicabilityItem.getByLabel("Result").selectOption("UNSATISFACTORY");
  await applicabilityItem.getByRole("button", { name: "Save" }).click();

  await expect(applicabilityItem.getByText(/Last inspection: 2026-01-15 by E2E Inspector — UNSATISFACTORY/)).toBeVisible();

  // The priority widget picks up the real inspection it just refreshed
  // against — the same Inspection row, not a second computation.
  await expect(conditionFactor).toContainText("Last inspection (2026-01-15) result: UNSATISFACTORY");
  await expect(conditionFactor).not.toContainText("not applicable");
});
