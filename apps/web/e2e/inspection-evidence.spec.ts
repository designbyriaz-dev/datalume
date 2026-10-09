import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Spec §42's "Missing evidence" Data Health check. Inspection.
// evidence_document_id and ComplianceAction.evidence_document_id have
// both been real columns since Sprint 16 (the compliance domain's own
// APPLICABILITY -> ... -> INSPECTION -> EVIDENCE -> ACTION chain names
// EVIDENCE explicitly, right between the two) — a real gap, not a
// missing-tracking one, which is why the fix here is two-sided: a new
// check_missing_inspection_evidence/check_missing_completed_action_
// evidence pair in app/data_health/rules.py, *and* the actual
// InspectionsPanel.tsx forms that never once let a user set
// evidence_document_id at all, for either an inspection or a completed
// action — a check flagging a gap no one could ever fix through the UI
// wouldn't be a real fix. This exercises both: recording an inspection
// with a file attached (no warning shown) and one without (a visible
// "no evidence document attached" note, closed once the next
// inspection supersedes it with evidence).
test("recording an inspection with evidence clears the missing-evidence warning", async ({ page }) => {
  await signUp(page, "E2E Inspection Evidence Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Evidence Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Evidence Boiler Co")).toBeVisible();

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();
  await page.locator("#requirement-code").fill("E2E-EVID-001");
  await page.locator("#requirement-title").fill("E2E annual boiler inspection");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();
  await expect(page.getByText("E2E-EVID-001")).toBeVisible();

  await page.goto("/components");
  await page.getByRole("row", { name: /E2E Evidence Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await page.getByLabel("Requirement").selectOption({ label: "E2E-EVID-001 — E2E annual boiler inspection" });
  await page.getByLabel("Basis").fill("Gas-fired boiler");
  await page.locator("#applicability-basis").locator("xpath=../..").getByRole("button", { name: "Add" }).click();
  const applicabilityItem = page.locator("li", { hasText: "Gas-fired boiler" });
  await expect(applicabilityItem).toBeVisible();

  // Recorded with no evidence file — the warning must show.
  await applicabilityItem.getByRole("button", { name: "+ Record inspection" }).click();
  await applicabilityItem.getByLabel("Inspector").fill("Gas Safe Engineer Ltd");
  await applicabilityItem.getByLabel("Inspection date").fill("2026-01-15");
  await applicabilityItem.getByRole("button", { name: "Save" }).click();
  await expect(applicabilityItem.getByText(/no evidence document attached/)).toBeVisible();

  // A second inspection, this time with a file — the warning clears,
  // since the "Last inspection" summary now points at this one.
  await applicabilityItem.getByRole("button", { name: "+ Record inspection" }).click();
  await applicabilityItem.getByLabel("Inspector").fill("Gas Safe Engineer Ltd");
  await applicabilityItem.getByLabel("Inspection date").fill("2027-01-15");
  await applicabilityItem.getByLabel("Inspection evidence file").setInputFiles({
    name: "gas-cert.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("gas certificate content"),
  });
  await applicabilityItem.getByRole("button", { name: "Save" }).click();
  await expect(applicabilityItem.getByText(/Last inspection: 2027-01-15/)).toBeVisible();
  await expect(applicabilityItem.getByText(/no evidence document attached/)).not.toBeVisible();

  // The real entity-linking proof, same shape as every other evidence
  // spec in this suite: the general documents list shows the same file.
  await page.goto("/data-and-uploads");
  await expect(page.getByText(/Inspection evidence/)).toBeVisible();
});

test("completing a compliance action with evidence attaches it to the action", async ({ page }) => {
  await signUp(page, "E2E Action Evidence Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Action Evidence Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Action Evidence Boiler Co")).toBeVisible();

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();
  await page.locator("#requirement-code").fill("E2E-EVID-002");
  await page.locator("#requirement-title").fill("E2E annual boiler inspection");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();
  await expect(page.getByText("E2E-EVID-002")).toBeVisible();

  await page.goto("/components");
  await page.getByRole("row", { name: /E2E Action Evidence Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await page.getByLabel("Requirement").selectOption({ label: "E2E-EVID-002 — E2E annual boiler inspection" });
  await page.getByLabel("Basis").fill("Gas-fired boiler needing remedial work");
  await page.locator("#applicability-basis").locator("xpath=../..").getByRole("button", { name: "Add" }).click();
  const applicabilityItem = page.locator("li", { hasText: "Gas-fired boiler needing remedial work" });
  await expect(applicabilityItem).toBeVisible();

  await applicabilityItem.getByRole("button", { name: "+ Raise action" }).click();
  await applicabilityItem.getByLabel("Compliance action description").fill("Replace faulty valve");
  await applicabilityItem.getByLabel("Compliance action deadline").fill("2026-06-01");
  await applicabilityItem.getByRole("button", { name: "Save" }).click();
  await expect(applicabilityItem.getByText(/Replace faulty valve — due 2026-06-01/)).toBeVisible();

  await applicabilityItem.getByRole("button", { name: "complete" }).click();
  await applicabilityItem.getByLabel("Completion evidence file").setInputFiles({
    name: "valve-replacement.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("completion evidence content"),
  });
  await applicabilityItem.getByRole("button", { name: "Confirm" }).click();
  await expect(applicabilityItem.getByText(/Replace faulty valve — due 2026-06-01/)).not.toBeVisible();

  await page.goto("/data-and-uploads");
  await expect(page.getByText(/Action completion evidence/)).toBeVisible();
});
