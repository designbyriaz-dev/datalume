import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77 steps 10-11: "Track hazards" / "Monitor damp & mould" — the
// /safety page (hazard register, repeat-hazard signal, status workflow,
// HazardActionsPanel) has always been fully built and wired to real
// endpoints, but had zero E2E coverage. hazard_type is deliberately free
// text (page's own copy), so "damp and mould" is typed exactly as a real
// user would and normalised client-side to DAMP_AND_MOULD.
test("reporting repeat damp & mould hazards, progressing one to a remedial action", async ({ page }) => {
  await signUp(page, "E2E Hazard Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Hazard Property");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Hazard Property")).toBeVisible();

  await page.goto("/safety");
  await expect(async () => {
    await page.getByLabel("Property").selectOption({ label: "E2E Hazard Property" });
    await expect(page.getByLabel("Property").locator("option:checked")).toHaveText("E2E Hazard Property");
  }).toPass({ timeout: 10_000 });

  // REPEAT_HAZARDS_PER_PROPERTY threshold is 2 within a 24-month window
  // (repeat_hazard.py) — two hazards of the same type on the same
  // property, reported moments apart, are both inside that window.
  for (let i = 1; i <= 2; i++) {
    await page.getByLabel("Hazard type").fill("Damp and mould");
    await page.getByLabel("Severity").selectOption("HIGH");
    await page.getByRole("button", { name: "Report" }).click();
    await expect(page.locator("li", { hasText: /DAMP AND MOULD/ })).toHaveCount(i, { timeout: 10_000 });
  }

  await expect(page.getByText(/2 damp and mould hazards in the last 24 months \(threshold 2\)/)).toBeVisible();

  const hazardItem = page.locator("li", { hasText: /DAMP AND MOULD/ }).first();
  await hazardItem.getByRole("button", { name: "triaged" }).click();
  await expect(hazardItem.getByText("TRIAGED")).toBeVisible();

  await hazardItem.getByRole("button", { name: "investigating" }).click();
  await expect(hazardItem.getByText("INVESTIGATING")).toBeVisible();

  await hazardItem.getByLabel("Investigation outcome").selectOption("CONFIRMED");
  await hazardItem.getByLabel("Findings").fill("Mould confirmed in bathroom extractor duct.");
  await hazardItem.getByRole("button", { name: "Record findings" }).click();
  await expect(hazardItem.getByText("INVESTIGATED")).toBeVisible();
  await expect(hazardItem.getByText(/Mould confirmed in bathroom extractor duct\./)).toBeVisible();

  await hazardItem.getByRole("button", { name: "action in progress" }).click();
  await expect(hazardItem.getByText("ACTION IN PROGRESS")).toBeVisible();

  await hazardItem.getByLabel("Hazard action description").fill("Install extractor fan");
  await hazardItem.getByLabel("Hazard action deadline").fill("2026-06-01");
  await hazardItem.getByRole("button", { name: "Raise" }).click();
  await expect(hazardItem.getByText(/Install extractor fan/)).toBeVisible();

  await hazardItem.getByRole("button", { name: "complete" }).click();
  await expect(hazardItem.getByRole("button", { name: "complete" })).not.toBeVisible();
});
