import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Spec §76 step 35: "Resolve missing data" — Handover Readiness'
// COMMISSIONING_EVIDENCE check (app/development/handover.py's
// check_commissioning_evidence) requires a component to have a
// Document whose document_type contains "COMMISSIONING", and has
// since Post-Sprint-24 — but the component evidence upload form's own
// DOCUMENT_TYPES list never included it, so this check could never
// genuinely pass for any component any user actually created, same
// "backend built, frontend incomplete" shape as the Building Control
// reference gap (see building-control-reference.spec.ts's own
// docstring). Added "COMMISSIONING" to ComponentDetailClient.tsx's
// DOCUMENT_TYPES alongside this spec.
test("uploading commissioning evidence against a component clears the readiness check that flags its absence", async ({ page }) => {
  await signUp(page, "E2E Commissioning Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Commissioning Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Commissioning Gardens")).toBeVisible();

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E Commissioning Block");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E Commissioning Gardens" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Commissioning Block")).toBeVisible();

  await page.goto("/properties");
  await page.getByLabel("Address").fill("Flat 1, E2E Commissioning Block");
  await page.getByLabel("Building (optional)").selectOption({ label: "E2E Commissioning Block" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Flat 1, E2E Commissioning Block")).toBeVisible();

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Commissioning Boiler Co");
  await page.getByLabel("Property (optional)").selectOption({ label: "Flat 1, E2E Commissioning Block" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Commissioning Boiler Co")).toBeVisible();

  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E Commissioning Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);
  await expect(page.getByText(/commissioning records missing/)).toBeVisible();

  await page.goto("/components");
  await page.getByRole("row", { name: /E2E Commissioning Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await page.locator("#evidence-title").fill("Boiler commissioning record");
  await page.locator("#evidence-type").selectOption("COMMISSIONING");
  await page.setInputFiles("#evidence-file", {
    name: "commissioning-record.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("commissioning record content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/Boiler commissioning record \(COMMISSIONING\)/)).toBeVisible();

  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E Commissioning Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);
  await expect(page.getByText(/commissioning records missing/)).not.toBeVisible();
});
