import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// listPayments (GET /api/v1/payments) has always been real, but the
// systematic api.ts audit that found it found zero frontend callers —
// /rent-and-payments/page.tsx only ever showed "Needs attention"
// (unresolved allocations) and the obligations list, so a payment that
// reconciliation auto-matched (the common case — this is deterministic
// matching, not a queue everything lands in) never appeared anywhere
// at all: recorded, then immediately invisible. Added a "Payment
// history" section scoped to the same selected-lease dropdown the
// obligations list already uses. This proves a cleanly-matched
// payment — one that genuinely never touches "Needs attention" — is
// still visible afterwards.
test("a cleanly-matched payment stays visible in payment history after it leaves the needs-attention queue", async ({ page }) => {
  await signUp(page, "E2E Payment History Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Ledger Unit");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Ledger Unit")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Ledger Tenant Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Ledger Tenant Ltd")).toBeVisible();

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Ledger Unit" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Ledger Tenant Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText(/LSE-\d+/)).toBeVisible();

  await page.goto("/rent-and-payments");
  await expect(page.getByText("No payments recorded for this lease yet.")).toBeVisible();

  await page.getByLabel("Type").selectOption({ label: "RENT" });
  await page.locator("#obligation-due-date").fill("2026-01-01");
  await page.locator("#obligation-period-start").fill("2026-01-01");
  await page.locator("#obligation-period-end").fill("2026-01-31");
  await page.locator("#obligation-amount").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("RENT · due 2026-01-01")).toBeVisible();

  // An exact amount/date match against a single open obligation is the
  // deterministic MATCHED path — it never lands in "Needs attention"
  // at all, so there is nothing else on the page pointing back at it.
  await page.locator("#payment-amount").fill("2500");
  await page.locator("#payment-received-date").fill("2026-01-01");
  await page.locator("#payment-payer-reference").fill("E2E-LEDGER-REF");
  await page.getByRole("button", { name: "Record" }).click();
  await expect(page.getByText(/reconciliation result: MATCHED/)).toBeVisible();
  await expect(page.getByText(/Needs attention/)).not.toBeVisible();

  // The payer-reference span's own parent <li> is the whole row —
  // one level up, not two.
  const historyRow = page.getByText("E2E-LEDGER-REF").locator("xpath=..");
  await expect(historyRow).toContainText("2026-01-01");
  await expect(historyRow).toContainText("£2500.00");

  // Still there after a reload — a real persisted record, not
  // component state that would vanish on refresh.
  await page.reload();
  await expect(page.getByText("E2E-LEDGER-REF")).toBeVisible();
});
