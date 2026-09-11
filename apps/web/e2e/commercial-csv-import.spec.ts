import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §78: "Import rent obligations", "Import payments" — the one
// Commercial Acceptance Test item that genuinely didn't exist on
// either side of the stack until now (only one-at-a-time manual entry
// existed). Uses the real /data-and-uploads flow every other importer
// in this codebase goes through — same MAPPED -> IMPORTING -> COMPLETED
// worker-driven pipeline data-and-uploads.spec.ts already proves for
// PROPERTIES. CSV headers match the field dictionary's own labels
// exactly, so the proposed mapping needs no manual editing, same as
// that spec's own "Property Address"/"Post Code"/"Type" headers.
test("importing a rent obligations CSV creates a real obligation against the matched lease", async ({ page }) => {
  await signUp(page, "E2E Commercial Import Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Import Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Import Unit")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Import Tenant Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Import Tenant Ltd")).toBeVisible();

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Import Unit" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Import Tenant Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();
  const leaseReferenceText = await page.getByText(/LSE-\d+/).first().innerText();
  const leaseReference = leaseReferenceText.match(/LSE-\d+/)?.[0];
  expect(leaseReference).toBeTruthy();

  await page.goto("/data-and-uploads");
  await page.getByLabel("Dataset type").selectOption("RENT_OBLIGATIONS");
  await page.getByLabel("Name").fill("E2E rent obligations upload");
  await page.setInputFiles("#upload-csv-file", {
    name: "obligations.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Lease Reference,Due Date,Period Start,Period End,Amount Due\n" +
        `${leaseReference},2026-02-01,2026-02-01,2026-02-28,2500.00\n`,
    ),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();

  await expect(page.getByRole("button", { name: "Apply mapping" })).toBeVisible();
  await page.getByRole("button", { name: "Apply mapping" }).click();

  await expect(page.getByRole("button", { name: "Start import" })).toBeVisible();
  await page.getByRole("button", { name: "Start import" }).click();
  await expect(page.getByText(/1 rows processed, 1 entities created/)).toBeVisible({ timeout: 20_000 });

  await page.goto("/rent-and-payments");
  await page.getByLabel("Lease", { exact: true }).selectOption({ label: leaseReference! });
  await expect(page.getByText(/RENT · due 2026-02-01/)).toBeVisible();
  await expect(page.getByText(/£2500.00 outstanding/)).toBeVisible();
});
