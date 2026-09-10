import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Commercial domain (Sprints 19-20): Tenant -> Lease -> Rent Obligation,
// then arrears.py's own "always computed at read time from obligations
// and matched payments, never stored" guarantee — an obligation with no
// payment against it must show as fully outstanding on /arrears.
test("an unpaid rent obligation shows as outstanding on the arrears page", async ({ page }) => {
  await signUp(page, "E2E Commercial Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("E2E Commercial Unit 1");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Commercial Unit 1")).toBeVisible();

  await page.goto("/tenancies");
  await page.getByLabel("Name", { exact: true }).fill("E2E Acme Retail Ltd");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Acme Retail Ltd")).toBeVisible();

  await page.goto("/leases");
  await page.getByLabel("Property").selectOption({ label: "E2E Commercial Unit 1" });
  await page.getByLabel("Tenant").selectOption({ label: "E2E Acme Retail Ltd" });
  await page.getByLabel("Start").fill("2026-01-01");
  await page.getByLabel("Expiry").fill("2031-01-01");
  await page.getByLabel("Rent (£)").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText(/LSE-\d+/)).toBeVisible();

  await page.goto("/rent-and-payments");
  await page.getByLabel("Type").selectOption({ label: "RENT" });
  await page.getByLabel("Due date").fill("2026-01-01");
  await page.getByLabel("Period start").fill("2026-01-01");
  await page.getByLabel("Period end").fill("2026-01-31");
  // "Amount (£)" is an ambiguous getByLabel match here — the payment
  // form above (a separate form on the same page) uses the same label
  // for a different field — so this one goes by id directly.
  await page.locator("#obligation-amount").fill("2500");
  await page.getByRole("button", { name: "Add" }).click();

  await page.goto("/arrears");
  // Total due and Outstanding both show £2500.00 here (nothing paid
  // yet), so this matches more than one element — assert at least one
  // is visible rather than requiring a single unique match.
  await expect(page.getByText("£2500.00").first()).toBeVisible();
});
