import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §78: "Reconcile payments". The manual split-allocation endpoint
// (POST /payments/{id}/allocations, add_manual_allocation) has always
// existed — "splitting one payment across several obligations... is a
// deliberate human act" per its own docstring, and api.ts's
// createManualAllocation has always been able to call it — but no page
// ever exposed a way to actually split a payment, only to resolve one
// ambiguous allocation against a single obligation. Two obligations
// sharing the same invoice reference reliably produces a genuinely
// ambiguous NEEDS_REVIEW allocation (the exact reconciliation.py rule
// this session's own commercial reconciliation tests already use).
test("an ambiguous payment can be split across two different obligations", async ({ page }) => {
  await signUp(page, "E2E Split Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Split Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Split Unit")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Split Tenant Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Split Tenant Ltd")).toBeVisible();

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Split Unit" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Split Tenant Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText(/LSE-\d+/)).toBeVisible();

  await page.goto("/rent-and-payments");
  // Two obligations sharing an invoice reference is exactly what
  // reconciliation.py's rule 1 treats as ambiguous — an equally
  // plausible match against either one.
  for (let i = 1; i <= 2; i++) {
    await page.getByLabel("Type").selectOption({ label: "RENT" });
    await page.locator("#obligation-due-date").fill("2026-01-01");
    await page.locator("#obligation-period-start").fill("2026-01-01");
    await page.locator("#obligation-period-end").fill("2026-01-31");
    await page.locator("#obligation-amount").fill("2500");
    await page.locator("#obligation-invoice-ref").fill("INV-DUP");
    await page.getByRole("button", { name: "Add" }).click();
    // Wait for this obligation to actually land before adding the
    // next one — the Add button submits asynchronously, and firing a
    // second click before the first request settles can race it.
    await expect(page.getByText("RENT · due 2026-01-01 · INV-DUP")).toHaveCount(i);
  }

  await page.locator("#payment-amount").fill("2500");
  await page.locator("#payment-received-date").fill("2026-01-01");
  await page.locator("#payment-payer-reference").fill("INV-DUP");
  await page.getByRole("button", { name: "Record" }).click();
  await expect(page.getByText(/reconciliation result: NEEDS REVIEW/)).toBeVisible();

  await expect(page.getByText("Needs attention (1)")).toBeVisible();
  await page.getByText("Split across obligations").click();

  const obligationSelects = page.getByLabel("Obligation to split into");
  await obligationSelects.selectOption({ index: 1 });
  await page.getByLabel("Amount to split").fill("1000");
  await page.getByRole("button", { name: "Add split" }).click();

  // The split succeeded without an error, and the original ambiguous
  // row is still here (untouched by the split) — reduce it to the
  // real remainder and resolve the rest for real, not still £2500.
  await expect(page.getByText(/Couldn't add that split/)).not.toBeVisible();
  await expect(page.getByText("Needs attention (1)")).toBeVisible();

  await page.getByLabel("Amount to resolve").fill("1500");
  await page.getByRole("button", { name: "Resolve" }).click();

  await expect(page.getByText("Needs attention (1)")).not.toBeVisible();
});
