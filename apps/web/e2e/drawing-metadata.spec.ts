import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Spec §76 step 21, "Upload drawing metadata" / spec §28's document
// metadata field list (document_reference, title, document_type,
// revision, status, uploaded_by, uploaded_at, related_entity, ...).
// Unlike the other "backend built, frontend incomplete" gaps this
// session found, this one turned out to already be substantially
// real: the generic Document model (app/documents/models.py) already
// tracks every field spec §28 names, and "DRAWING" has been a
// selectable document_type on the general /data-and-uploads upload
// form and ComponentDetailClient.tsx's own Evidence section since
// early in the build — document_type is a free-text column, not a
// backend-enforced enum, so adding a new type anywhere is a frontend-
// only change. The one real gap: DevelopmentDetailClient.tsx's own
// Evidence section (added earlier this session for O&M documentation)
// never offered "DRAWING" as an option. Closed alongside this spec.
test("a drawing uploaded against a component captures real metadata and is linked to it", async ({ page }) => {
  await signUp(page, "E2E Drawing Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Drawing Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Drawing Boiler Co")).toBeVisible();
  await page.getByRole("row", { name: /E2E Drawing Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await expect(page.getByText("No evidence linked to this component yet.")).toBeVisible();

  await page.locator("#evidence-title").fill("Boiler room layout");
  await page.locator("#evidence-type").selectOption("DRAWING");
  await page.setInputFiles("#evidence-file", {
    name: "boiler-room-layout.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("drawing content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();

  // Real metadata, not just a successful upload: a generated reference
  // (DOC-NNNNNN) and the type genuinely recorded as DRAWING, not a
  // default.
  await expect(page.getByText(/DOC-\d+/)).toBeVisible();
  await expect(page.getByText(/Boiler room layout \(DRAWING\)/)).toBeVisible();
  await expect(page.getByText("No evidence linked to this component yet.")).not.toBeVisible();

  // Real entity-linking, not just local component state: the org's
  // general documents list shows the same document, and reloading
  // this component's own page still shows it scoped here — same proof
  // shape as construction-evidence.spec.ts/commissioning-evidence.spec.ts.
  await page.goto("/data-and-uploads");
  await expect(page.getByText("Boiler room layout")).toBeVisible();

  await page.goBack();
  await page.reload();
  await expect(page.getByText(/Boiler room layout \(DRAWING\)/)).toBeVisible();
});

test("a drawing uploaded against a development is captured the same way", async ({ page }) => {
  await signUp(page, "E2E Development Drawing Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Drawing Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Drawing Gardens")).toBeVisible();

  await page.getByRole("row", { name: /E2E Drawing Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);
  await expect(page.getByText("No evidence linked to this development yet.")).toBeVisible();

  await page.locator("#development-evidence-title").fill("Site layout plan");
  await page.locator("#development-evidence-type").selectOption("DRAWING");
  await page.setInputFiles("#development-evidence-file", {
    name: "site-layout.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("site layout content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();

  await expect(page.getByText(/Site layout plan \(DRAWING\)/)).toBeVisible();
  await expect(page.getByText("No evidence linked to this development yet.")).not.toBeVisible();
});
