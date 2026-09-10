import { Page, expect } from "@playwright/test";

let counter = 0;

/** A fresh org + owner login for one test — real signup through the
 * actual UI, not a fixture seeded directly into the database, so this
 * exercises the same signup form real users go through. Each call
 * uses a unique email so tests never collide on the same org, even
 * though they all run against one shared smoketest database. */
export async function signUp(page: Page, orgName: string) {
  counter += 1;
  const email = `e2e-${Date.now()}-${counter}@example.com`;

  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("E2E Test User");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByLabel("Organisation name").fill(orgName);
  await page.getByRole("button", { name: "Start your free trial" }).click();

  await expect(page).toHaveURL(/\/home$/, { timeout: 10_000 });
  return { email };
}
