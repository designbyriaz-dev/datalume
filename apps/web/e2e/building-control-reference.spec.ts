import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 steps 7-8: "Enter Building Control reference supplied
// externally", "Enter BSR reference where applicable/supplied". Both
// were fully backend-built — Building.building_control_reference/
// bsr_reference are ExternalReference rows create_building has always
// accepted, and compute_handover_readiness's own
// check_building_control_reference (weight 0.10) already reads them —
// but no page ever exposed a way to enter either, so this check could
// never pass for any building any user actually created: Handover
// Readiness was permanently capped below 100% by a UI gap, not a real
// data problem. Added the two fields to the "Add a building" form
// (both buildings/page.tsx and the same client method used everywhere
// else) plus display on BuildingDetailClient.tsx.
test("a Building Control reference clears the readiness check that flags its absence", async ({ page }) => {
  await signUp(page, "E2E BCO Org");

  // Development A: a building with no reference — the check must
  // genuinely fail, not just always pass now that the field exists.
  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E BCO Gardens Alpha");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E BCO Gardens Alpha")).toBeVisible();

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E BCO Block Alpha");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E BCO Gardens Alpha" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E BCO Block Alpha")).toBeVisible();

  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E BCO Gardens Alpha/ }).getByRole("link").click();
  await expect(page.getByText(/buildings missing a Building Control reference/)).toBeVisible();

  // Development B: a building with both references supplied at
  // creation — the same check must now genuinely pass.
  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E BCO Gardens Beta");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E BCO Gardens Beta")).toBeVisible();

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E BCO Block Beta");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E BCO Gardens Beta" });
  await page.locator("#building-control-reference").fill("BC/2026/0042");
  await page.locator("#building-bsr-reference").fill("BSR-2026-001");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E BCO Block Beta")).toBeVisible();

  await page.getByRole("row", { name: /E2E BCO Block Beta/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/buildings\/.+/);
  await expect(page.getByText(/Building Control: BC\/2026\/0042/)).toBeVisible();
  await expect(page.getByText(/BSR: BSR-2026-001/)).toBeVisible();

  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E BCO Gardens Beta/ }).getByRole("link").click();
  await expect(page.getByText(/buildings missing a Building Control reference/)).not.toBeVisible();
});
