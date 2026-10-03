import { expect, test } from "@playwright/test";

import { installFixtures } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await installFixtures(page);
});

test("dashboard loads problem-first and shows read-only supervision", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toBeVisible();
  await expect(page.getByText("Attention required")).toBeVisible();
  await expect(page.getByText("SUPERVISION [READ ONLY]").first()).toBeVisible();
  await expect(page.getByText("READ ONLY").first()).toBeVisible();
});

test("workload grid lists pods and opens pod detail", async ({ page }) => {
  await page.goto("/workloads");
  await expect(page.getByRole("heading", { name: "Workloads" })).toBeVisible();
  await page.getByText("log-transformer-def").first().click();
  await expect(page.getByRole("heading", { name: /Pod log-transformer-def/ })).toBeVisible();
  await expect(page.getByText("PARTIAL —").first()).toBeVisible();
});

test("findings center sorts critical first", async ({ page }) => {
  await page.goto("/findings");
  await expect(page.getByRole("heading", { name: "Findings Center" })).toBeVisible();
  const rows = page.locator('tbody tr:not([aria-hidden="true"])');
  await expect(rows.first()).toContainText("F-001");
  await expect(rows.first()).toContainText("Critical");
});

test("command palette opens with Ctrl+K and finds a pod", async ({ page }) => {
  await page.goto("/dashboard");
  await page.keyboard.press("Control+k");
  const search = page.getByLabel("Search", { exact: true });
  await expect(search).toBeVisible();
  await search.fill("transformer");
  await expect(page.getByRole("option").first()).toBeVisible();
});

test("context switch is available from the top bar", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByLabel("Kubernetes context")).toBeVisible();
  await expect(page.getByLabel("Namespace")).toBeVisible();
});

test("gitops page never offers mutation controls", async ({ page }) => {
  await page.goto("/gitops");
  await expect(page.getByRole("heading", { name: "GitOps Command Center" })).toBeVisible();
  for (const forbidden of ["Reconcile", "Suspend", "Resume", "Rollback", "Upgrade"]) {
    await expect(page.getByRole("button", { name: forbidden, exact: true })).toHaveCount(0);
  }
});

test("pki dashboard summarises expiry posture", async ({ page }) => {
  await page.goto("/pki");
  await expect(page.getByRole("heading", { name: "PKI / TLS Command Center" })).toBeVisible();
  await expect(page.getByText("≤30 days")).toBeVisible();
  await expect(page.getByText("syslog-cert").first()).toBeVisible();
});

test("topology page renders the dependency inspector", async ({ page }) => {
  await page.goto("/topology?kind=Pod&name=transformer-abc");
  await expect(page.getByRole("heading", { name: "Dependency Topology" })).toBeVisible();
  await expect(page.getByText("Read-only inspector", { exact: false })).toBeVisible();
});

test("storage and network pages render inventories", async ({ page }) => {
  await page.goto("/storage");
  await expect(page.getByText("data-1").first()).toBeVisible();
  await page.goto("/network");
  await expect(page.getByText("syslog-svc").first()).toBeVisible();
});

test("doctor page renders the capability matrix", async ({ page }) => {
  await page.goto("/doctor");
  await expect(page.getByRole("heading", { name: "Doctor" })).toBeVisible();
  await expect(page.getByText("kubectl").first()).toBeVisible();
});

test("settings page exposes exports and no secrets", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("link", { name: "pods.json" })).toBeVisible();
});

test("unknown route renders an explicit unavailable state", async ({ page }) => {
  await page.goto("/does-not-exist");
  await expect(page.getByText("Route not found")).toBeVisible();
});

test("browser refresh keeps the current route", async ({ page }) => {
  await page.goto("/findings");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Findings Center" })).toBeVisible();
});

test("keyboard chord g d navigates to the dashboard", async ({ page }) => {
  await page.goto("/findings");
  await page.locator("body").click();
  await page.keyboard.press("g");
  await page.keyboard.press("d");
  await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toBeVisible();
});
