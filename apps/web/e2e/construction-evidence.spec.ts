import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 steps 22-23: "Upload construction evidence", "Link evidence
// to exact component". Document.related_entity_type/related_entity_id
// (documents/models.py) has always supported linking to any entity,
// and upload_document (documents/router.py) always accepted them as
// form fields — but no page ever exposed that on the upload form, and
// api.uploadDocument/listDocuments never passed them through, so a
// component's own evidence was unreachable from the UI. Added an
// "Evidence" section to ComponentDetailClient.tsx alongside this spec,
// same "backend built, frontend incomplete" gap as Planned Investment
// Intelligence's missing fields.
test("evidence uploaded against a component is linked to it, not just to the organisation", async ({ page }) => {
  await signUp(page, "E2E Evidence Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Evidence Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Evidence Boiler Co")).toBeVisible();
  await page.getByRole("row", { name: /E2E Evidence Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await expect(page.getByText("No evidence linked to this component yet.")).toBeVisible();

  await page.locator("#evidence-title").fill("Commissioning certificate");
  await page.locator("#evidence-type").selectOption("CERTIFICATE");
  await page.setInputFiles("#evidence-file", {
    name: "commissioning.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("commissioning certificate content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();

  await expect(page.getByText(/Commissioning certificate \(CERTIFICATE\)/)).toBeVisible();
  await expect(page.getByText("No evidence linked to this component yet.")).not.toBeVisible();

  // The proof this is real entity-linking, not just an upload: the org's
  // general documents list (data-and-uploads) shows the same document,
  // and reloading this component's own page still shows it scoped here
  // — both views read the same related_entity_type/id, not a fluke of
  // local component state.
  await page.goto("/data-and-uploads");
  await expect(page.getByText("Commissioning certificate")).toBeVisible();

  await page.goBack();
  await page.reload();
  await expect(page.getByText(/Commissioning certificate \(CERTIFICATE\)/)).toBeVisible();
});
