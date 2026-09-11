import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 step 43: "See new-build history" on an operational
// Property 360. golden-thread.spec.ts already proves the portfolio
// summary counts a freshly created Development -> Building -> Property
// chain; handover-authorisation.spec.ts already proves a development's
// own handover UI genuinely flips a property to HANDED_OVER. Neither
// checks what Property 360 itself surfaces afterwards — this closes
// that: the property's own page shows its development/building lineage
// as a real breadcrumb (not just a raw ID), and after handover, the
// readiness score and override reason the development recorded persist
// into the property's own "Handover" field, the same read the property
// keeps carrying long after the development itself may be archived.
test("Property 360 shows the development/building lineage and, after handover, the readiness record", async ({ page }) => {
  await signUp(page, "E2E Property 360 Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E New Build Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E New Build Gardens")).toBeVisible();

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E New Build Block");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E New Build Gardens" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E New Build Block")).toBeVisible();

  await page.goto("/properties");
  await page.getByLabel("Address").fill("Flat 1, E2E New Build Block");
  await page.getByLabel("Building (optional)").selectOption({ label: "E2E New Build Block" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Flat 1, E2E New Build Block")).toBeVisible();
  await page.getByRole("row", { name: /Flat 1, E2E New Build Block/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/properties\/.+/);

  // The lineage breadcrumb — real linked entities, not a raw FK.
  await expect(page.getByRole("link", { name: "E2E New Build Gardens" })).toBeVisible();
  await expect(page.getByRole("link", { name: "E2E New Build Block" })).toBeVisible();
  await expect(page.getByText("Not yet handed over")).toBeVisible();

  await page.getByLabel("Change status:").selectOption("READY_FOR_HANDOVER");
  await expect(page.getByLabel("Change status:")).toHaveValue("READY_FOR_HANDOVER");

  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E New Build Gardens/ }).getByRole("link").click();
  await page.getByLabel(/Override reason/).fill("E2E: new-build history check");
  await page.getByRole("button", { name: "Authorise handover" }).click();
  await expect(page.getByText(/Override: E2E: new-build history check/)).toBeVisible();

  await page.goto("/properties");
  await page.getByRole("row", { name: /Flat 1, E2E New Build Block/ }).getByRole("link").click();

  // The readiness record from handover now shows on the property's own
  // page — its new-build history, not just its current live status.
  await expect(page.getByText(/% at handover \(override\)/)).toBeVisible();
});
