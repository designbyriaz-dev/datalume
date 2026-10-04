import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 step 11: "Add floors" — the one step in the New Build
// acceptance list with a real, working backend (POST/GET /api/v1/floors,
// app/development/hierarchy_router.py) and UI (the building detail
// page's own "Add a floor" form) but no Playwright spec of its own;
// every other spec that touches a building stops at creating it on the
// /buildings list, never opens its detail page.
test("adding a floor to a building shows up on the building's detail page", async ({ page }) => {
  await signUp(page, "E2E Floors Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Floors Development");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Floors Development")).toBeVisible();

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E Floors Block");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E Floors Development" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Floors Block")).toBeVisible();

  // The buildings list links each row by its internal reference
  // (BLD-000001, ...), not its name — same "generated internal
  // reference" step (§76 step 10) the list page itself exists to show.
  await page.getByRole("link", { name: /BLD-\d+/ }).click();
  await expect(page).toHaveURL(/\/buildings\/[0-9a-f-]+$/);

  await expect(page.getByText("No floors yet.")).toBeVisible();

  // The building detail page has several "Add" buttons (floors,
  // properties, specifications, ...) — scope to the "Add a floor"
  // card specifically rather than the page's first/only match.
  const addFloorCard = page.getByRole("heading", { name: "Add a floor" }).locator("..");
  await addFloorCard.getByLabel("Name").fill("Ground Floor");
  await addFloorCard.getByLabel("Level index").fill("0");
  await addFloorCard.getByRole("button", { name: "Add" }).click();

  await expect(page.getByText("No floors yet.")).not.toBeVisible();
  await expect(page.getByText("Ground Floor")).toBeVisible();
  await expect(page.getByText("Level 0")).toBeVisible();
});
