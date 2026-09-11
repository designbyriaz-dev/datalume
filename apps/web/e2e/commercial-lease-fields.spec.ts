import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §78: "Add leases". Lease.break_date/rent_review_date/
// service_charge_amount_pence have always been real columns
// CreateLeaseRequest accepted, and api.ts's createLease() already
// typed and threaded all three through — but the "Add a lease" form
// only ever exposed Property/Tenant/Start/Expiry/Rent/Frequency, so a
// real user could never actually set a break date, a rent review
// date, or a service charge, even though the backend, schema, and API
// client all fully supported it. Same "backend built, frontend
// incomplete" shape as the Building Control reference fix from the
// New Build side. Recording a payment's `method` field had the exact
// same gap — fixed alongside since it's the same page's sibling form.
test("a lease's break date, rent review date, and service charge are genuinely captured", async ({ page }) => {
  await signUp(page, "E2E Lease Fields Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Lease Fields Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Lease Fields Unit")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Lease Fields Tenant Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Lease Fields Tenant Ltd")).toBeVisible();

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Lease Fields Unit" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Lease Fields Tenant Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByLabel("Break date (optional)").fill("2028-06-01");
  await page.getByLabel("Rent review (optional)").fill("2029-01-01");
  await page.getByLabel("Service charge £ (optional)").fill("450");
  await page.getByRole("button", { name: "Add" }).click();

  const leaseItem = page.locator("li", { hasText: "E2E Lease Fields Tenant Ltd" });
  await expect(leaseItem).toBeVisible();
  await expect(leaseItem).toContainText("break 2028-06-01");
  await expect(leaseItem).toContainText("rent review 2029-01-01");
  await expect(leaseItem).toContainText("service charge £450.00");

  // The "Record a payment" form's own method field, same page.
  await page.goto("/rent-and-payments");
  await page.locator("#payment-amount").fill("2500");
  await page.locator("#payment-received-date").fill("2026-01-01");
  await page.getByLabel("Method (optional)").fill("BANK_TRANSFER");
  await page.getByRole("button", { name: "Record" }).click();
  await expect(page.getByText(/Recorded — reconciliation result/)).toBeVisible();
});
