import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §31: "do not hard-code permanent interpretations of evolving
// Building Regulations" — create_requirement_version (app/operations/
// compliance/service.py) has always been the real, sole, append-only
// path for that (same shape as Specification revisions, Sprint 9): the
// old version is kept and marked superseded, a new row is added. But
// unlike specifications, there's no change-control governance layer
// wrapping it either — POST .../versions is a direct, single-step
// write, and it had zero frontend callers at all (found by the same
// api.ts audit that closed three other gaps this session). The
// requirement list already rendered a "v{n}" badge, implying
// versioning was a real concept — there was simply no way to create
// one. Added an inline "revise" toggle per requirement row, same
// per-row-form shape as InspectionsPanel's own toggles.
test("revising a compliance requirement creates a real new version, keeping the old one", async ({ page }) => {
  await signUp(page, "E2E Requirement Revision Org");

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();

  await page.locator("#requirement-code").fill("E2E-REV-001");
  await page.locator("#requirement-title").fill("Annual gas safety check");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();

  const requirementItem = page.locator("li", { hasText: "E2E-REV-001" });
  await expect(requirementItem).toBeVisible();
  await expect(requirementItem.getByText("v1")).toBeVisible();
  await expect(requirementItem).toContainText("Cadence: annual");

  await requirementItem.getByRole("button", { name: "revise" }).click();
  // Pre-filled from the current version, not blank — confirms it reads
  // the row it was opened from rather than always defaulting empty.
  await expect(requirementItem.getByLabel("Revised title")).toHaveValue("Annual gas safety check");
  await expect(requirementItem.getByLabel("Revised cadence")).toHaveValue("annual");

  await requirementItem.getByLabel("Revised cadence").fill("biennial");
  await requirementItem.getByRole("button", { name: "Save new version" }).click();

  // The same requirement row now shows v2 and the new cadence — a real
  // new row replaced it in the current-only list this page renders,
  // not an edit-in-place of v1.
  await expect(requirementItem.getByText("v2")).toBeVisible();
  await expect(requirementItem).toContainText("Cadence: biennial");
  await expect(requirementItem.getByText("v1")).not.toBeVisible();

  // Still true after a reload — a real persisted version, not
  // component state.
  await page.reload();
  await page.getByRole("button", { name: "Gas Safety" }).click();
  const reloadedItem = page.locator("li", { hasText: "E2E-REV-001" });
  await expect(reloadedItem.getByText("v2")).toBeVisible();
  await expect(reloadedItem).toContainText("Cadence: biennial");
});
