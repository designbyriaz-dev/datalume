import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Closes the second of the two gaps the Playwright suite's own
// STATUS.md note named as "still genuinely unwritten" (handover
// authorisation was the first — see handover-authorisation.spec.ts).
// Defects and warranties share a building detail page (spec §34-35,
// architecture/03-development-domain.md §8) — this exercises a real
// status transition (OPEN -> ASSIGNED, server-validated against
// DEFECT_TRANSITIONS) and a real warranty voiding, not just the
// creation forms.
//
// The OPEN -> ASSIGNED step alone left spec §76 step 30 ("Complete
// defect") with no real coverage — DEFECT_TRANSITIONS has always
// supported the full OPEN -> ASSIGNED -> IN_PROGRESS ->
// READY_FOR_INSPECTION -> COMPLETED -> CLOSED chain (including a
// failed-inspection path back to IN_PROGRESS, and setting
// completion_date on the COMPLETED transition) but nothing exercised
// past the first step. Extended below to drive a second defect all
// the way to CLOSED.
test("reporting a defect and adding a warranty both drive real status changes", async ({ page }) => {
  await signUp(page, "E2E Defects Org");

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E Defects Block");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Defects Block")).toBeVisible();
  await page.getByRole("row", { name: /E2E Defects Block/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/buildings\/.+/);

  await page.locator("#defect-category").fill("Windows");
  await page.locator("#defect-description").fill("Cracked pane in communal stairwell");
  await page.locator("#defect-severity").selectOption("HIGH");
  await page.getByRole("button", { name: "Report" }).click();

  const defectItem = page.locator("li", { hasText: "Cracked pane in communal stairwell" });
  await expect(defectItem).toBeVisible();
  await expect(defectItem.getByText("OPEN")).toBeVisible();
  await expect(defectItem.getByText("HIGH")).toBeVisible();

  // A real server-validated transition (DEFECT_TRANSITIONS), not just a
  // free-text status field — only OPEN's actual next states are offered.
  await defectItem.getByRole("button", { name: "assigned" }).click();
  await expect(defectItem.getByText("ASSIGNED")).toBeVisible();
  await expect(defectItem.getByRole("button", { name: "in progress" })).toBeVisible();

  await page.locator("#warranty-provider").fill("Acme Windows Ltd");
  await page.locator("#warranty-type").fill("Structural warranty");
  await page.locator("#warranty-expiry-date").fill("2099-01-01");
  // Several "Add" buttons exist on this detail page (floors, spaces,
  // specifications) — scope to the warranty form's own grid container.
  await page.locator("#warranty-expiry-date").locator("xpath=../..").getByRole("button", { name: "Add" }).click();

  const warrantyItem = page.locator("li", { hasText: "Acme Windows Ltd" });
  await expect(warrantyItem).toBeVisible();
  await expect(warrantyItem.getByText(/d left\)/)).toBeVisible();
  await expect(warrantyItem.getByText("ACTIVE")).toBeVisible();

  await warrantyItem.getByRole("button", { name: "Void" }).click();
  await expect(warrantyItem.getByText("VOID")).toBeVisible();
});

test("a defect can be driven all the way through completion to closed", async ({ page }) => {
  await signUp(page, "E2E Defect Completion Org");

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E Defect Completion Block");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Defect Completion Block")).toBeVisible();
  await page.getByRole("row", { name: /E2E Defect Completion Block/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/buildings\/.+/);

  await page.locator("#defect-category").fill("Roof");
  await page.locator("#defect-description").fill("Slipped tile above flat 3");
  await page.locator("#defect-severity").selectOption("MEDIUM");
  await page.getByRole("button", { name: "Report" }).click();

  const defectItem = page.locator("li", { hasText: "Slipped tile above flat 3" });
  await expect(defectItem).toBeVisible();
  await expect(defectItem.getByText("OPEN")).toBeVisible();

  await defectItem.getByRole("button", { name: "assigned" }).click();
  await expect(defectItem.getByText("ASSIGNED")).toBeVisible();

  await defectItem.getByRole("button", { name: "in progress" }).click();
  await expect(defectItem.getByText("IN_PROGRESS")).toBeVisible();

  await defectItem.getByRole("button", { name: "ready for inspection" }).click();
  await expect(defectItem.getByText("READY_FOR_INSPECTION")).toBeVisible();

  // Real server-validated transitions, not a free-text field: READY_FOR_
  // INSPECTION's own next states are "completed" (inspection passed) or
  // "in progress" (sent back for rework) — never "closed" directly.
  await expect(defectItem.getByRole("button", { name: "closed" })).not.toBeVisible();

  await defectItem.getByRole("button", { name: "completed" }).click();
  await expect(defectItem.getByText("COMPLETED")).toBeVisible();

  await defectItem.getByRole("button", { name: "closed" }).click();
  await expect(defectItem.getByText("CLOSED")).toBeVisible();

  // CLOSED is terminal — DEFECT_TRANSITIONS maps it to an empty tuple,
  // so no transition button renders at all once reached.
  await expect(defectItem.locator("button")).toHaveCount(0);
});
