import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// GET /api/v1/data-health's full findings list (every check, every
// severity) has always existed, but no page anywhere ever called it —
// /home only ever showed the headline score and a property's own detail
// page only ever showed findings scoped to that one property, so every
// other finding type (orphan/duplicate components, missing warranties,
// missing BSR references, missing evidence, ...) was invisible in the
// UI. This adds the general /data-health page (checks summary + a
// per-check filterable findings list) and proves it surfaces a
// component-scoped finding — ORPHAN_COMPONENT — that neither /home nor
// any property page would ever have shown.
test("the Data Health page lists a component-scoped finding no other page shows", async ({ page }) => {
  await signUp(page, "E2E Data Health Page Org");

  // Deliberately left unattached to any development/building/property/
  // space — the exact condition check_orphan_components flags.
  await page.goto("/components");
  // The form's own useEffect sets an initial default component type as
  // soon as the type list loads; on a slower runner "Add" can still fire
  // before that default lands, so retry the whole fill-and-submit step
  // rather than trusting one attempt (same race as component-warranty.spec.ts).
  const componentRow = page.getByRole("row", { name: /E2E Orphan Boiler Co/ });
  await expect(async () => {
    await page.locator("#component-manufacturer").fill("E2E Orphan Boiler Co");
    await page.getByRole("button", { name: "Add" }).click();
    await expect(componentRow).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 10_000 });

  await page.goto("/data-health");
  await expect(page.getByText(/overall data health score/)).toBeVisible();

  // The checks summary table renders first, before the findings table —
  // scope to it specifically, since both tables list every check code.
  const checkRow = page.getByRole("table").first().getByRole("row", { name: /Orphan component/ });
  await expect(checkRow).toBeVisible();
  await checkRow.getByRole("button", { name: "View findings" }).click();

  await expect(page.getByText("Showing findings for")).toBeVisible();
  // The findings table shows the component's own reference (e.g.
  // COMP-000001), not its manufacturer — anchor on the check's fixed
  // message text instead, which is unique to this finding type.
  const findingRow = page.getByRole("row").filter({ hasText: "isn't traceable to anywhere in the portfolio" });
  await expect(findingRow).toBeVisible();

  // The affected-record cell links straight to the real component.
  await findingRow.getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);
  await expect(page.getByText("E2E Orphan Boiler Co")).toBeVisible();
});
