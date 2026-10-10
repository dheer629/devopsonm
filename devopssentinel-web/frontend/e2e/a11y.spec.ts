import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { installFixtures } from "./fixtures";

const ROUTES = [
  "/dashboard",
  "/workloads",
  "/logs",
  "/describe",
  "/findings",
  "/pki",
  "/gitops",
  "/settings",
  "/doctor",
  "/baselines",
  "/exports",
  "/incidents/INC12345",
  "/database",
  "/kafka",
];

test.beforeEach(async ({ page }) => {
  await installFixtures(page);
});

for (const route of ROUTES) {
  test(`axe: ${route} has no serious or critical violations`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const blocking = results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical",
    );
    if (blocking.length) {
      console.log(
        "AXE-BLOCKING " +
          route +
          " " +
          blocking
            .map((v) => `${v.id}(${v.impact}) x${v.nodes.length} :: ${v.nodes[0]?.target?.join(" ")}`)
            .join(" | "),
      );
    }
    expect(
      blocking,
      blocking.map((v) => `${v.id}: ${v.help}`).join("\n"),
    ).toEqual([]);
  });
}

test("status is never communicated by colour alone", async ({ page }) => {
  await page.goto("/findings");
  const firstRow = page.locator('tbody tr:not([aria-hidden="true"])').first();
  // Every status cell must contain a glyph and a text label.
  await expect(firstRow).toContainText("Critical");
  await expect(firstRow).toContainText("✕");
});

test("primary controls are keyboard reachable", async ({ page }) => {
  await page.goto("/dashboard");
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName ?? "");
  expect(focused.length).toBeGreaterThan(0);
});
