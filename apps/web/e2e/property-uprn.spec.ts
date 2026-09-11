import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// UPRN is the flagship "never fabricate an official identifier"
// example throughout the spec, and MISSING_UPRN has been a Data
// Health check since Sprint 5 — but api.createProperty has always
// accepted uprn (Property 360 has always displayed it), and the "Add
// a property" form never had a field for it. A manually-created
// property could never satisfy MISSING_UPRN through the product at
// all — only via CSV import or a raw POST to /external-references,
// neither of which is "enter it" in the way a real user working a new
// development would expect.
test("a UPRN entered at property creation is genuinely captured, not silently dropped", async ({ page }) => {
  await signUp(page, "E2E UPRN Org");

  await page.goto("/properties");
  await page.getByLabel("Address").fill("1 No UPRN Close");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("1 No UPRN Close")).toBeVisible();

  await page.getByLabel("Address").fill("2 UPRN Close");
  await page.getByLabel("UPRN (optional)").fill("100023336956");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("2 UPRN Close")).toBeVisible();

  await page.getByRole("row", { name: /1 No UPRN Close/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/properties\/.+/);
  const uprnValue = page.getByText("UPRN", { exact: true }).locator("xpath=following-sibling::div[1]");
  await expect(uprnValue).toHaveText("—");

  await page.goto("/properties");
  await page.getByRole("row", { name: /2 UPRN Close/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/properties\/.+/);
  await expect(page.getByText("100023336956")).toBeVisible();
});
