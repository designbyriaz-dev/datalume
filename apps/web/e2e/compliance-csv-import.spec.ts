import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77: "Upload compliance" — COMPLIANCE_INSPECTIONS
// (app/operations/importers.py's import_compliance_inspection_row) is
// a real, registered importer, and the /data-and-uploads dataset-type
// dropdown is populated straight from the backend's field dictionary
// (not a hardcoded frontend list), so this dataset type was already
// fully reachable end to end — it simply never had a Playwright spec,
// same shape as operations-csv-import.spec.ts (REPAIRS) and
// commercial-csv-import.spec.ts (RENT_OBLIGATIONS), which this mirrors
// exactly.
test("importing a compliance inspections CSV creates a real inspection against the matched building", async ({ page }) => {
  await signUp(page, "E2E Compliance Import Org");

  await page.goto("/compliance");
  await page.getByRole("button", { name: "Gas Safety" }).click();
  await page.locator("#requirement-code").fill("E2E-GAS-IMPORT-001");
  await page.locator("#requirement-title").fill("E2E annual gas safety check");
  await page.locator("#requirement-cadence").fill("annual");
  await page.getByRole("button", { name: "Add" }).nth(1).click();
  await expect(page.getByText("E2E-GAS-IMPORT-001")).toBeVisible();

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E Compliance Import Block");
  await page.getByRole("button", { name: "Add" }).click();
  const buildingRow = page.getByRole("row", { name: /E2E Compliance Import Block/ });
  await expect(buildingRow).toBeVisible();
  const buildingReferenceText = await buildingRow.getByRole("link").innerText();

  await page.goto("/data-and-uploads");
  await page.getByLabel("Dataset type").selectOption("COMPLIANCE_INSPECTIONS");
  await page.getByLabel("Name").fill("E2E compliance inspections upload");
  await page.setInputFiles("#upload-csv-file", {
    name: "compliance-inspections.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Requirement Code,Entity Type,Entity Reference,Inspector,Inspection Date,Result\n" +
        `E2E-GAS-IMPORT-001,building,${buildingReferenceText},E2E Gas Safe Engineer,2026-02-01,SATISFACTORY\n`,
    ),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();

  await expect(page.getByRole("button", { name: "Apply mapping" })).toBeVisible();
  await page.getByRole("button", { name: "Apply mapping" }).click();

  await expect(page.getByRole("button", { name: "Start import" })).toBeVisible();
  await page.getByRole("button", { name: "Start import" }).click();
  await expect(page.getByText(/1 rows processed, 1 entities created/)).toBeVisible({ timeout: 20_000 });

  await page.goto("/buildings");
  await page.getByRole("row", { name: /E2E Compliance Import Block/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/buildings\/.+/);
  await expect(page.getByText(/Building-level inspections:.*2026-02-01 \(SATISFACTORY\)/)).toBeVisible();
});
