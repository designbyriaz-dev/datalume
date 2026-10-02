import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §78's last genuinely missing item, "Monitor lease events":
// break_date/rent_review_date/lease_expiry were always real, captured
// Lease fields (see commercial-lease-fields.spec.ts), but nothing
// computed or surfaced an approaching one. LEASE_EVENT_UPCOMING
// (app/attention/rules.py) closes it by flagging active leases with a
// break/review/expiry date inside a 90-day window — same manual
// "Run scan now" trigger attention-scan.spec.ts already proves for
// REPEAT_FAILURE.
test("a lease with an upcoming break date surfaces a real attention signal", async ({ page }) => {
  await signUp(page, "E2E Lease Event Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Lease Event Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Lease Event Unit")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Lease Event Tenant Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Lease Event Tenant Ltd")).toBeVisible();

  const breakDate = new Date();
  breakDate.setDate(breakDate.getDate() + 30);
  const breakDateIso = breakDate.toISOString().slice(0, 10);

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Lease Event Unit" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Lease Event Tenant Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByLabel("Break date").fill(breakDateIso);
  await page.getByRole("button", { name: "Add" }).click();
  const leaseReferenceText = await page.getByText(/LSE-\d+/).first().innerText();
  const leaseReference = leaseReferenceText.match(/LSE-\d+/)?.[0];
  expect(leaseReference).toBeTruthy();

  // A new lease isn't ACTIVE by default — the rule only scans active
  // leases, same as LEASE_ARREARS, so this lease's own status workflow
  // has to run first, not just a direct DB write a test could skip.
  const leaseItem = page.locator("li", { hasText: leaseReference! });
  await leaseItem.getByRole("button", { name: "active" }).click();
  await expect(leaseItem.getByText("ACTIVE")).toBeVisible();

  await page.goto("/home");
  await page.getByRole("button", { name: "Run scan now" }).click();
  await expect(page.getByText(/1 new, \d+ updated\./)).toBeVisible();
  await expect(page.getByText(new RegExp(`${leaseReference} has an upcoming break option on ${breakDateIso}`))).toBeVisible();
});
