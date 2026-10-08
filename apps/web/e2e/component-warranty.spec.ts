import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Handover Readiness's WARRANTIES_RECEIVED check (check_warranties_received,
// app/development/handover.py) has always queried Warranty.component_id —
// the Warranty model has supported a nullable component_id FK since it was
// added — but the only "Add a warranty" form in the UI
// (BuildingDetailClient.tsx) only ever created building-scoped warranties,
// so this check could never pass for any real development. Added a
// component-scoped "Add a warranty" form to ComponentDetailClient.tsx,
// reusing api.createWarranty exactly as the building form does, just
// passing component_id instead of building_id.
test("a component-scoped warranty clears the readiness check that flags its absence", async ({ page }) => {
  await signUp(page, "E2E Component Warranty Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E CW Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E CW Gardens")).toBeVisible();

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E CW Block");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E CW Gardens" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E CW Block")).toBeVisible();

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E CW Property");
  await page.getByLabel("Building (optional)").selectOption({ label: "E2E CW Block" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E CW Property")).toBeVisible();

  await page.goto("/components");
  // The form's own useEffect sets an initial default type as soon as the
  // list loads; on a slower runner that default selection can still be in
  // flight when selectOption fires, so retry the whole select-and-verify
  // step rather than trusting one attempt (same race as
  // repair-linked-to-component.spec.ts).
  await expect(async () => {
    await page.getByLabel("Type").selectOption({ label: "Boilers" });
    await expect(page.getByLabel("Type").locator("option:checked")).toHaveText("Boilers");
  }).toPass({ timeout: 10_000 });
  await page.getByLabel("Property (optional)").selectOption({ label: "E2E CW Property" });
  await page.locator("#component-manufacturer").fill("E2E CW Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("row", { name: /E2E CW Boiler Co/ })).toBeVisible();

  // The check must genuinely fail first — no warranty exists for the one
  // in-scope component yet.
  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E CW Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);
  await expect(page.getByText(/component warranties missing/)).toBeVisible();

  await page.goto("/components");
  await page.getByRole("row", { name: /E2E CW Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);
  await expect(page.getByText("No warranties linked to this component yet.")).toBeVisible();

  await page.locator("#component-warranty-provider").fill("E2E Warranty Provider Ltd");
  await page.locator("#component-warranty-type").fill("Manufacturer warranty");
  await page.locator("#component-warranty-expiry-date").fill("2030-01-01");
  // Several "Add" buttons exist on this detail page (specifications,
  // compliance requirements, child components) — scope to the warranty
  // form's own grid container, same pattern as defects-and-warranties.spec.ts.
  await page.locator("#component-warranty-expiry-date").locator("xpath=../..").getByRole("button", { name: "Add" }).click();

  await expect(page.getByText(/E2E Warranty Provider Ltd — Manufacturer warranty/)).toBeVisible();
  await expect(page.getByText("No warranties linked to this component yet.")).not.toBeVisible();

  // The check must now genuinely pass — the readiness score was recomputed
  // against a real warranty row, not just a UI state change.
  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E CW Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);
  await expect(page.getByText(/component warranties missing/)).not.toBeVisible();
});
