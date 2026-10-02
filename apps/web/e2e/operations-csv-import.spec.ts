import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §77: "Upload repairs" — the one Housing Operations Acceptance
// Test item that genuinely didn't exist on either side of the stack
// (only one-at-a-time manual entry existed) until
// app/operations/importers.py. Uses the real /data-and-uploads flow
// every other importer in this codebase goes through — same
// MAPPED -> IMPORTING -> COMPLETED worker-driven pipeline
// data-and-uploads.spec.ts already proves for PROPERTIES and
// commercial-csv-import.spec.ts proves for RENT_OBLIGATIONS. CSV
// headers match the field dictionary's own labels exactly, so the
// proposed mapping needs no manual editing.
test("importing a repairs CSV creates a real repair against the matched property", async ({ page }) => {
  await signUp(page, "E2E Operations Import Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Repairs Import Unit");
  await page.getByRole("button", { name: "Add" }).click();
  const propertyRow = page.getByRole("row", { name: /E2E Repairs Import Unit/ });
  await expect(propertyRow).toBeVisible();
  const propertyReferenceText = await propertyRow.getByRole("link").innerText();

  await page.goto("/data-and-uploads");
  await page.getByLabel("Dataset type").selectOption("REPAIRS");
  await page.getByLabel("Name").fill("E2E repairs upload");
  await page.setInputFiles("#upload-csv-file", {
    name: "repairs.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Property Reference,Category,Description,Reported Date,Priority\n" +
        `${propertyReferenceText},Plumbing,Leaking stopcock,2026-02-01,URGENT\n`,
    ),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();

  await expect(page.getByRole("button", { name: "Apply mapping" })).toBeVisible();
  await page.getByRole("button", { name: "Apply mapping" }).click();

  await expect(page.getByRole("button", { name: "Start import" })).toBeVisible();
  await page.getByRole("button", { name: "Start import" }).click();
  await expect(page.getByText(/1 rows processed, 1 entities created/)).toBeVisible({ timeout: 20_000 });

  await page.goto("/repairs");
  await expect(page.locator("li", { hasText: "Leaking stopcock" })).toBeVisible();
  await expect(page.locator("li", { hasText: "Leaking stopcock" })).toContainText("URGENT");
});
