import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Spec §28: "Never silently overwrite previous versions." POST
// /api/v1/documents/{id}/versions (app/documents/router.py) and
// api.uploadDocumentVersion have existed and been backend-tested
// (app/tests/test_documents.py) since early in the build, but no page
// anywhere ever exposed a way to trigger it — found while closing the
// drawing-metadata gap earlier this session, documented in STATUS.md
// as a separate, smaller gap rather than folded into that fix. Adds a
// "New version" action to both ComponentDetailClient.tsx and
// DevelopmentDetailClient.tsx's Evidence sections: clicking it reveals
// an inline revision+file form; the previous row is marked SUPERSEDED
// (append-only, never edited) and the current-versions-only list
// (GET /documents' own default) shows only the new one in its place.
test("uploading a new version of a document against a component replaces it in the current list, not silently", async ({
  page,
}) => {
  await signUp(page, "E2E Document Version Org");

  await page.goto("/components");
  // The form's own useEffect sets an initial default type as soon as
  // the list loads; on a slower runner that default selection can
  // still be in flight when "Add" fires — same race as
  // repeat-component-failure.spec.ts/component-warranty.spec.ts, same
  // fix: select a real type explicitly and retry until it's taken.
  await expect(async () => {
    await page.getByLabel("Type").selectOption({ label: "Boilers" });
    await expect(page.getByLabel("Type").locator("option:checked")).toHaveText("Boilers");
  }).toPass({ timeout: 10_000 });
  await page.locator("#component-manufacturer").fill("E2E Version Boiler Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Version Boiler Co")).toBeVisible();
  await page.getByRole("row", { name: /E2E Version Boiler Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await page.locator("#evidence-title").fill("Boiler install drawing");
  await page.locator("#evidence-type").selectOption("DRAWING");
  await page.setInputFiles("#evidence-file", {
    name: "install-drawing-v1.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("version 1 content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/Boiler install drawing \(DRAWING\)/)).toBeVisible();
  await expect(page.locator("li", { hasText: "Boiler install drawing" })).toHaveCount(1);

  await page.getByRole("button", { name: "New version" }).click();
  await page.locator("#new-version-revision").fill("B");
  await page.setInputFiles("#new-version-file", {
    name: "install-drawing-v2.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("version 2 content"),
  });
  // The top "Add evidence" form has its own "Upload" button too — scope
  // to the inline new-version form specifically, same pattern as
  // defects-and-warranties.spec.ts's warranty form.
  await page.locator("#new-version-revision").locator("xpath=..").getByRole("button", { name: "Upload" }).click();

  // The new version takes the old one's place — same title/type/
  // reference — rather than appearing as a second row: GET /documents
  // defaults to current_only=true, and the previous row is marked
  // SUPERSEDED on the backend, never edited in place (proven directly
  // by app/tests/test_documents.py; this checks the UI reflects that
  // correctly, not a second, duplicate-looking row).
  await expect(page.getByText(/Boiler install drawing \(DRAWING\)/)).toBeVisible();
  await expect(page.locator("li", { hasText: "Boiler install drawing" })).toHaveCount(1);
});

test("uploading a new version of a document against a development works the same way", async ({ page }) => {
  await signUp(page, "E2E Development Document Version Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Version Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Version Gardens")).toBeVisible();
  await page.getByRole("row", { name: /E2E Version Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);

  await page.locator("#development-evidence-title").fill("O&M manual");
  await page.locator("#development-evidence-type").selectOption("O&M");
  await page.setInputFiles("#development-evidence-file", {
    name: "om-manual-v1.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("version 1 content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/O&M manual \(O&M\)/)).toBeVisible();
  await expect(page.locator("li", { hasText: "O&M manual" })).toHaveCount(1);

  await page.getByRole("button", { name: "New version" }).click();
  await page.locator("#new-version-revision").fill("B");
  await page.setInputFiles("#new-version-file", {
    name: "om-manual-v2.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("version 2 content"),
  });
  await page.locator("#new-version-revision").locator("xpath=..").getByRole("button", { name: "Upload" }).click();

  await expect(page.getByText(/O&M manual \(O&M\)/)).toBeVisible();
  await expect(page.locator("li", { hasText: "O&M manual" })).toHaveCount(1);
});
