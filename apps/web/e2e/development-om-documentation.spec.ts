import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Handover Readiness's OM_DOCUMENTATION check (check_om_documentation,
// app/development/handover.py) has always queried for a Document with
// related_entity_type="development" and a document_type containing "O&M"
// — Document.related_entity_type/related_entity_id (documents/models.py)
// has always supported linking to any entity type, and
// ComponentDetailClient.tsx's own "Evidence" section already proves that
// pattern works for components (construction-evidence.spec.ts) — but
// DevelopmentDetailClient.tsx had no equivalent upload section at all, so
// this check could never pass for any real development. Added an
// "Evidence" section to DevelopmentDetailClient.tsx, modeled directly on
// ComponentDetailClient.tsx's, uploading with
// related_entity_type="development" and related_entity_id=the
// development's own id.
test("O&M documentation uploaded against a development clears the readiness check that flags its absence", async ({
  page,
}) => {
  await signUp(page, "E2E OM Documentation Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E OM Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E OM Gardens")).toBeVisible();

  await page.getByRole("row", { name: /E2E OM Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);

  // The check must genuinely fail first — no O&M documentation exists for
  // this development yet.
  await expect(page.getByText("O&M documentation missing")).toBeVisible();
  await expect(page.getByText("No evidence linked to this development yet.")).toBeVisible();

  await page.locator("#development-evidence-title").fill("Riverside O&M manual");
  await page.locator("#development-evidence-type").selectOption("O&M");
  await page.setInputFiles("#development-evidence-file", {
    name: "om-manual.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("O&M manual content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();

  await expect(page.getByText(/Riverside O&M manual \(O&M\)/)).toBeVisible();
  await expect(page.getByText("No evidence linked to this development yet.")).not.toBeVisible();

  // The check must now genuinely pass — the readiness score was recomputed
  // against a real document row linked to this exact development, not
  // just a UI state change.
  await expect(page.getByText("O&M documentation missing")).not.toBeVisible();

  // Proves this is real entity-linking, not just an upload: the org's
  // general documents list (data-and-uploads) shows the same document,
  // and reloading this development's own page still shows it scoped here
  // — same proof shape as construction-evidence.spec.ts.
  await page.goto("/data-and-uploads");
  await expect(page.getByText("Riverside O&M manual")).toBeVisible();

  await page.goBack();
  await page.reload();
  await expect(page.getByText(/Riverside O&M manual \(O&M\)/)).toBeVisible();
  await expect(page.getByText("O&M documentation missing")).not.toBeVisible();
});
