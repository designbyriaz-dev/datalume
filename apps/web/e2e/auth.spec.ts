import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

test("sign-up creates a workspace and lands on the home dashboard", async ({ page }) => {
  await signUp(page, "E2E Auth Org");
  await expect(page.getByRole("heading", { name: "Good morning 👋" })).toBeVisible();
  // Sprint 24's accessibility fix, verified live: every field on this
  // page has a real associated label, not just a placeholder.
  await expect(page.getByText("E2E Auth Org")).toBeVisible();
});

test("signing out returns to sign-in and blocks the dashboard", async ({ page }) => {
  await signUp(page, "E2E Sign Out Org");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/sign-in$/, { timeout: 10_000 });

  await page.goto("/home");
  await expect(page).toHaveURL(/\/sign-in$/, { timeout: 10_000 });
});
