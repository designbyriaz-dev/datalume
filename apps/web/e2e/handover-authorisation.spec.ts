import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// Real coverage of a golden-thread step the suite was still missing
// (see STATUS.md's own "still genuinely unwritten" list): handover
// authorisation. HANDOVER_READINESS_THRESHOLD_PCT is 100% (service.py)
// and a freshly created property has no stock condition survey, no
// handover documentation, etc. — genuinely not ready — so this
// exercises the real override-reason path, not a synthetic "everything
// happens to be ready" shortcut.
test("authorising handover with an override reason hands a property over for real", async ({ page }) => {
  await signUp(page, "E2E Handover Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Handover Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Handover Gardens")).toBeVisible();

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E Handover Block");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E Handover Gardens" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Handover Block")).toBeVisible();

  await page.goto("/properties");
  await page.getByLabel("Address").fill("Flat 1, E2E Handover Block");
  await page.getByLabel("Building (optional)").selectOption({ label: "E2E Handover Block" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Flat 1, E2E Handover Block")).toBeVisible();
  await page.getByRole("row", { name: /Flat 1, E2E Handover Block/ }).getByRole("link").click();

  await expect(page).toHaveURL(/\/properties\/.+/);
  await page.getByLabel("Change status:").selectOption("READY_FOR_HANDOVER");
  await expect(page.getByLabel("Change status:")).toHaveValue("READY_FOR_HANDOVER");

  await page.goto("/developments");
  await page.getByRole("row", { name: /E2E Handover Gardens/ }).getByRole("link").click();
  await expect(page).toHaveURL(/\/developments\/.+/);

  await expect(page.getByText("Not ready")).toBeVisible();
  await expect(page.getByText("No properties handed over yet.")).toBeVisible();

  // Authorising below threshold with no reason must fail — a real
  // server-side rejection, not a UI-only gate.
  await page.getByRole("button", { name: "Authorise handover" }).click();
  await expect(page.getByText(/below the required 100/)).toBeVisible();

  await page.getByLabel(/Override reason/).fill("E2E: accepted risk, no O&M docs yet");
  await page.getByRole("button", { name: "Authorise handover" }).click();

  await expect(page.getByText("No properties handed over yet.")).not.toBeVisible();
  await expect(page.getByText(/Override: E2E: accepted risk/)).toBeVisible();

  await page.goto("/properties");
  await page.getByRole("row", { name: /Flat 1, E2E Handover Block/ }).getByRole("link").click();
  await expect(page.getByLabel("Change status:")).toHaveValue("HANDED_OVER");
});
