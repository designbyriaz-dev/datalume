import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Post-Sprint-24: IMPORT moved off the request/response cycle onto the
// worker's poll loop (spec §72's "tens of thousands of properties"
// performance requirement), the same way report generation already
// works (see reports.spec.ts). This watches a real dataset go
// MAPPED -> IMPORTING -> COMPLETED with no page reload, then confirms
// the imported property actually landed.
test("an uploaded CSV goes from MAPPED to COMPLETED and creates real properties", async ({ page }) => {
  await signUp(page, "E2E Uploads Org");

  await page.goto("/data-and-uploads");
  await page.getByLabel("Name").fill("E2E upload");
  await page.setInputFiles("#upload-csv-file", {
    name: "properties.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Property Address,Post Code,Type\n12 E2E Street,SW1A 1AA,House\n"),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();

  await expect(page.getByRole("button", { name: "Apply mapping" })).toBeVisible();
  await page.getByRole("button", { name: "Apply mapping" }).click();

  await expect(page.getByRole("button", { name: "Start import" })).toBeVisible();
  await page.getByRole("button", { name: "Start import" }).click();

  await expect(page.getByText(/Importing/)).toBeVisible();

  // The page's own 2s poll picks up the worker's 5s tick — real room,
  // same reasoning as reports.spec.ts's wait for READY.
  await expect(page.getByText(/1 rows processed, 1 entities created/)).toBeVisible({ timeout: 20_000 });

  await page.goto("/properties");
  await expect(page.getByText("12 E2E Street")).toBeVisible();
});
