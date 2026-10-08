import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 step 50: "Audit all significant changes" — every domain has
// written to AuditEvent via record_audit_event (app/platform/audit.py)
// since early in this build, but until GET /api/v1/audit and this page
// existed there was no way for a user to ever read it back. Exercises
// the real flow: trigger a write elsewhere (adding a property), then
// confirm it shows up here, attributed to the right person.
test("adding a property shows up in the organisation's audit log", async ({ page }) => {
  await signUp(page, "E2E Audit Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("1 Audit Log Way");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("1 Audit Log Way")).toBeVisible();

  await page.goto("/organisation/audit");
  await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible();

  await page.getByLabel("Entity type").fill("property");
  await page.getByRole("button", { name: "Apply" }).click();

  const row = page.getByRole("row", { name: /Property — created/ });
  await expect(row).toBeVisible();
  await expect(row.getByText("E2E Test User")).toBeVisible();

  await row.getByText("View").click();
  await expect(row.getByText(/"property_reference": "PROP-/)).toBeVisible();
});
