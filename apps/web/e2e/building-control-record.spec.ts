import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Spec §30: Building Control & regulatory mapping. Building.
// building_control_reference/bsr_reference (see building-control-
// reference.spec.ts) are bare ExternalReference strings only —
// architecture/03-development-domain.md §5 calls for a real
// `building_control_records` table tracking the actual application
// lifecycle (body, application/approval dates, status, conditions,
// completion reference, supporting evidence) that those two strings
// never captured. That table never existed at all — not a UI gap, a
// genuinely missing backend feature. Added the model/migration/router
// plus a "Building Control records" section on BuildingDetailClient.tsx
// alongside this spec.
test("a Building Control record is created, approved, and evidence is linked to it", async ({ page }) => {
  await signUp(page, "E2E Building Control Org");

  await page.goto("/buildings");
  await page.locator("#building-name").fill("E2E BC Record Block");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E BC Record Block")).toBeVisible();
  await page.getByRole("row", { name: /E2E BC Record Block/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/buildings\/.+/);

  await expect(page.getByText("No Building Control records yet.")).toBeVisible();

  await page.locator("#bc-body").fill("Local Authority Building Control");
  await page.locator("#bc-application-date").fill("2025-03-01");
  await page.locator("#bc-application-reference").fill("BC-APP-7001");
  await page.locator("#bc-bsr-reference").fill("BSR-7001");
  // Several other sections on this page have their own "Add" button —
  // scope to the Building Control form's own grid, same pattern as
  // document-new-version.spec.ts's inline-form scoping.
  await page.locator("#bc-bsr-reference").locator("xpath=../..").getByRole("button", { name: "Add" }).click();

  await expect(page.getByText("Local Authority Building Control")).toBeVisible();
  await expect(page.getByText(/App ref BC-APP-7001/)).toBeVisible();
  await expect(page.getByText(/BSR BSR-7001/)).toBeVisible();
  await expect(page.getByText("SUBMITTED")).toBeVisible();
  await expect(page.getByText("No Building Control records yet.")).not.toBeVisible();

  await page.getByRole("button", { name: "Manage" }).click();
  await page.locator("#bc-status").selectOption("COMPLETED");
  await page.locator("#bc-approval-date").fill("2025-06-15");
  await page.locator("#bc-completion-reference").fill("BC-COMP-7002");
  await page.locator("#bc-conditions").fill("Fire-stopping to be re-inspected post-handover.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Completion ref BC-COMP-7002/)).toBeVisible();

  // Collapse the Manage panel before asserting the status badge text —
  // the panel's own <select> also has a "COMPLETED" option, which would
  // otherwise make this a strict-mode-ambiguous match.
  await page.getByRole("button", { name: "Manage" }).click();
  await expect(page.getByText("COMPLETED")).toBeVisible();

  await page.getByRole("button", { name: "Manage" }).click();
  await expect(page.getByText("No evidence linked yet.")).toBeVisible();
  await page.locator("#bc-evidence-title").fill("Completion certificate");
  await page.locator("#bc-evidence-type").selectOption("CERTIFICATE");
  await page.setInputFiles("#bc-evidence-file", {
    name: "completion-cert.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("completion certificate content"),
  });
  await page.getByRole("button", { name: "Upload" }).click();

  await expect(page.getByText(/Completion certificate \(CERTIFICATE\)/)).toBeVisible();
  await expect(page.getByText("No evidence linked yet.")).not.toBeVisible();

  // Real entity-linking, not just local state: the general documents
  // list shows the same evidence, same cross-check shape as
  // construction-evidence.spec.ts/drawing-metadata.spec.ts.
  await page.goto("/data-and-uploads");
  await expect(page.getByText("Completion certificate")).toBeVisible();
});
