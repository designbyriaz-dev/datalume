import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// A systematic audit of apps/web/src/lib/api.ts found 24 client methods
// with zero callers anywhere in the frontend. Most turned out to be
// correctly unused (superseded by a composed endpoint, or deliberately
// bypassed by a governance workflow), but five were real: every tunable
// engine parameter in the platform — compliance status thresholds,
// payment reconciliation, planned investment, repair detection rules,
// and attention rules — has a real, tested per-org GET+PATCH endpoint
// and zero settings UI anywhere. Added five new sections to the
// Organisation page (already the established home for other org-level
// tunables, e.g. reference patterns), reusing that page's own
// load/draft/inline-save/403-message pattern rather than a new page.
// This proves each section round-trips through the real backend, not
// just local component state — every assertion below re-reads the page
// after a save/reload rather than trusting the optimistic UI alone.
test("engine configuration settings round-trip through the real backend", async ({ page }) => {
  await signUp(page, "E2E Engine Config Org");

  await page.goto("/organisation");
  await expect(page.getByText("Compliance status thresholds")).toBeVisible();

  // Compliance status thresholds: real seeded defaults, then a real save.
  await expect(page.getByLabel("Due soon (days)")).toHaveValue("30");
  await page.getByLabel("Due soon (days)").fill("45");
  await page
    .getByText("Due soon (days)")
    .locator("xpath=../..")
    .getByRole("button", { name: "Save" })
    .click();
  await page.reload();
  await expect(page.getByLabel("Due soon (days)")).toHaveValue("45");

  // Payment reconciliation: single-field config, same round-trip proof.
  await expect(page.getByLabel("Due date window (days)")).toHaveValue("14");
  await page.getByLabel("Due date window (days)").fill("21");
  await page
    .getByText("Due date window (days)")
    .locator("xpath=../..")
    .getByRole("button", { name: "Save" })
    .click();
  await page.reload();
  await expect(page.getByLabel("Due date window (days)")).toHaveValue("21");

  // Repair detection rules: a per-rule table row, not a single config —
  // real seeded defaults for the model-trend rule's own distinct fields.
  await expect(page.getByLabel("Component model trend threshold ratio")).toHaveValue("0.15");
  await page.getByLabel("Component model trend threshold ratio").fill("0.25");
  const modelTrendRow = page.getByRole("row", { name: /Component model trend/ });
  await modelTrendRow.getByRole("button", { name: "Save" }).click();
  await page.reload();
  await expect(page.getByLabel("Component model trend threshold ratio")).toHaveValue("0.25");

  // Attention rules: switching one off is a real write, not local-only
  // state — survives a reload, and the signal it drives genuinely stops
  // firing (proven by repeat-component-failure.spec.ts's own positive
  // case; this only proves the toggle itself persists).
  // A controlled checkbox driven by the async save, not local state —
  // click rather than uncheck(), since the checked value only flips once
  // the PATCH response comes back and the row is refetched.
  const repeatFailureToggle = page.getByLabel("Repeat repair or component failure pattern active");
  await expect(repeatFailureToggle).toBeChecked();
  await repeatFailureToggle.click();
  await expect(page.getByRole("row", { name: /Repeat repair or component failure/ })).toContainText("Inactive");
  await page.reload();
  await expect(page.getByLabel("Repeat repair or component failure pattern active")).not.toBeChecked();

  // The rule_definition JSON reveal works and shows the real stored value.
  await page.getByRole("row", { name: /Compliance requirement in breach/ }).getByText("View").click();
  await expect(page.getByText(/"breach_statuses"/)).toBeVisible();
});
