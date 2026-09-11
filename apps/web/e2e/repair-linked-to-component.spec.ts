import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 step 45: "Link repair to component" — the repairs page's
// own copy has always promised this ("optionally linked to the
// component that failed"), and api.createRepair/RepairOut have always
// carried component_id, and REPAIR_FREQUENCY (planned_investment.py)
// has always read Repair.component_id — but the "Report a repair" form
// never had a field for it, so no repair any real user created could
// ever be linked to a component. Discovered while wiring this: the
// "Add a component" form had the same gap one level up — no way to set
// property_id either, so a component could never be placed anywhere a
// repair's own property-scoped dropdown could find it. Fixed both.
test("linking a repair to a component drives its REPAIR_FREQUENCY factor", async ({ page }) => {
  await signUp(page, "E2E Repair Link Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Repair Link Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Repair Link Property")).toBeVisible();

  await page.goto("/components");
  // The form's own useEffect sets an initial default type as soon as
  // the list loads; on a slower runner that default selection can
  // still be in flight when selectOption fires, so retry the whole
  // select-and-verify step rather than trusting one attempt.
  await expect(async () => {
    await page.getByLabel("Type").selectOption({ label: "Boilers" });
    await expect(page.getByLabel("Type").locator("option:checked")).toHaveText("Boilers");
  }).toPass({ timeout: 10_000 });
  await page.getByLabel("Property (optional)").selectOption({ label: "E2E Repair Link Property" });
  await page.locator("#component-manufacturer").fill("E2E Repair Link Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  const componentRow = page.getByRole("row", { name: /E2E Repair Link Boiler Co/ });
  await expect(componentRow).toBeVisible();
  await expect(componentRow).toContainText("Boilers");

  await page.goto("/repairs");
  // Same defaulted-select race as the Type field above — the repairs
  // form auto-selects the first property as soon as its own list
  // loads.
  await expect(async () => {
    await page.getByLabel("Property").selectOption({ label: "E2E Repair Link Property" });
    await expect(page.getByLabel("Property").locator("option:checked")).toHaveText("E2E Repair Link Property");
  }).toPass({ timeout: 10_000 });
  await expect(page.getByLabel("Component (optional)")).toContainText("Boilers");
  // The only real component in the dropdown besides "— None —".
  await page.getByLabel("Component (optional)").selectOption({ index: 1 });
  await page.locator("#repair-category").fill("Heating");
  await page.locator("#repair-description").fill("Boiler not firing");
  await page.getByRole("button", { name: "Report" }).click();

  const repairItem = page.locator("li", { hasText: "Boiler not firing" });
  await expect(repairItem).toBeVisible();
  // Proves the link is real, not just accepted and discarded — the
  // register row itself shows the component it resolved to.
  await expect(repairItem.getByRole("link", { name: /Component/ })).toBeVisible();

  await repairItem.getByRole("link", { name: /Component/ }).click();
  await expect(page).toHaveURL(/\/components\/.+/);
  await page.getByText("Planned investment priority").click();
  const repairFactor = page.locator("li", { hasText: "Repair frequency" });
  await expect(repairFactor).toContainText("1 repair(s) in the last");
  await expect(repairFactor).not.toContainText("0 repair(s)");
});
