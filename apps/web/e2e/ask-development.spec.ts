import { test, expect } from "@playwright/test";
import { signUp } from "./helpers";

// spec §76 step 48: "Ask questions about development" — no tool in
// app/intelligence/ask/tools.py ever supported entity_type="development"
// (only building/property/component/lease), and "development" wasn't
// even an option in the /ask page's own dropdown, so every question
// about a development always fell through to the fixed "I don't have
// data" message — not a UI gap like the last two fixes, a genuinely
// missing tool. get_development_summary wraps the exact same
// deterministic computations (compute_handover_readiness,
// properties_in_development) the Development detail page and the
// Handover Readiness report already use — no new calculation invented.
test("asking about a development returns a real, grounded answer", async ({ page }) => {
  await signUp(page, "E2E Ask Development Org");

  await page.goto("/developments");
  await page.getByLabel("Name").fill("E2E Ask Gardens");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Ask Gardens")).toBeVisible();

  await page.goto("/buildings");
  await page.getByLabel("Name", { exact: true }).fill("E2E Ask Block");
  await page.getByLabel("Development (optional)").selectOption({ label: "E2E Ask Gardens" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E Ask Block")).toBeVisible();

  await page.goto("/properties");
  await page.getByLabel("Address").fill("Flat 1, E2E Ask Block");
  await page.getByLabel("Building (optional)").selectOption({ label: "E2E Ask Block" });
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Flat 1, E2E Ask Block")).toBeVisible();

  await page.goto("/ask");
  await page.getByLabel("Ask about").selectOption({ label: "Development" });
  await page.getByLabel("Record").selectOption({ label: "E2E Ask Gardens" });
  await page.getByPlaceholder(/Is this compliant/).fill("Give me a summary overview of this development.");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText("No data")).not.toBeVisible();
  await expect(page.getByText(/building\(s\)/)).toBeVisible();
  await expect(page.getByText(/handover readiness/)).toBeVisible();

  await page.getByText(/Show the data behind this answer/).click();
  await expect(page.getByText("get_development_summary")).toBeVisible();
});
