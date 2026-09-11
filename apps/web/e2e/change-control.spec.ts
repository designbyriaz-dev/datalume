import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 steps 25-27: "Record proposed change", "Preserve previous
// specification", "Approve/reject change" — architecture/03-development-
// domain.md §7's append-only revision model, never touched by any
// existing E2E spec. implement_change_control (service.py) creates a
// NEW specification row for the approved change and marks the old one
// SUPERSEDED rather than editing it in place — preservation itself
// (the superseded row still exists, never deleted) is already covered
// at the data level by test_specifications.py/test_change_control.py;
// this confirms the UI side of the same guarantee: the new revision
// replaces the old one in the current-only view a user actually sees,
// it isn't silently overwritten in place.
test("approving and implementing a change control replaces the specification with a new revision", async ({ page }) => {
  await signUp(page, "E2E Change Control Org");

  await page.goto("/components");
  await page.locator("#component-manufacturer").fill("E2E Change Control Co");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Change Control Co")).toBeVisible();
  await page.getByRole("row", { name: /E2E Change Control Co/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/components\/.+/);

  await page.locator("#component-spec-title").fill("Original roofing specification");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(/Original roofing specification rev A/)).toBeVisible();

  await page.locator("#change-proposed-title").fill("Updated roofing specification");
  await page.locator("#change-reason").fill("Original supplier ceased trading");
  await page.getByRole("button", { name: "Propose" }).click();

  const changeItem = page.locator("li", { hasText: "Original supplier ceased trading" });
  await expect(changeItem).toBeVisible();
  await expect(changeItem.getByText("PROPOSED")).toBeVisible();

  await changeItem.getByRole("button", { name: "Approve" }).click();
  await expect(changeItem.getByText("APPROVED")).toBeVisible();

  await changeItem.getByRole("button", { name: "Implement" }).click();
  await expect(changeItem.getByText("IMPLEMENTED")).toBeVisible();

  // The new revision (rev B) is now the current one a user sees; the
  // superseded rev A drops out of the default current-only view (its
  // own row still exists — that's what the backend suite verifies).
  const updatedSpecItem = page.locator("li", { hasText: "Updated roofing specification" });
  await expect(updatedSpecItem).toBeVisible();
  await expect(updatedSpecItem.getByText(/rev B/)).toBeVisible();
  await expect(updatedSpecItem.getByText("ACTIVE")).toBeVisible();
  await expect(page.getByText(/Original roofing specification rev A/)).not.toBeVisible();
});
