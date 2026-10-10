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

test("workload grid charts live CPU and memory usage", async ({ page }) => {
  await page.goto("/workloads");
  await expect(page.getByRole("heading", { name: "CPU usage" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Memory usage" })).toBeVisible();
  // The columns carry the observed usage from the Metrics API.
  await expect(page.getByRole("columnheader", { name: "CPU (cores)" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Memory (bytes)" })).toBeVisible();
  await expect(page.getByText("0.015").first()).toBeVisible();
  await expect(page.getByText("58.000 Mi").first()).toBeVisible();
});

test("Refresh now re-reads the visible resources immediately", async ({ page }) => {
  let reads = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/pods") reads += 1;
  });

  await page.goto("/workloads");
  await expect(page.getByRole("heading", { name: "Workloads" })).toBeVisible();
  const before = reads;

  await page.getByRole("button", { name: "Refresh now" }).click();
  await expect.poll(() => reads).toBeGreaterThan(before);
});

test("LIVE interval keeps the page refreshing without interaction", async ({ page }) => {
  let reads = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/pods") reads += 1;
  });

  await page.goto("/workloads");
  await expect(page.getByRole("heading", { name: "Workloads" })).toBeVisible();

  await page.getByLabel("Live refresh interval").click();
  await page.getByRole("option", { name: "5 sec" }).click();
  const before = reads;

  // No clicking, no navigation: the interval itself must re-read the page.
  await expect.poll(() => reads, { timeout: 15_000 }).toBeGreaterThan(before);
});

test("usage charts observe the cluster on their own and can be paused", async ({ page }) => {
  test.setTimeout(60_000);
  let reads = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/metrics/nodes") reads += 1;
  });

  await page.goto("/workloads");
  await expect(page.getByRole("heading", { name: "CPU usage" })).toBeVisible();

  // Observation is the chart's own behaviour -- no LIVE switch, no interaction.
  // The Metrics API answers with an instantaneous value, so repeated reads are
  // the only way a trend can exist, and the card has to say it is doing that.
  await expect(page.getByText("observing every 5s").first()).toBeVisible();
  const before = reads;
  await expect.poll(() => reads, { timeout: 20_000 }).toBeGreaterThan(before);
  // The samples the chart reports are the ones it collected, not just traffic.
  await expect(page.getByText(/15 min window · [2-9]\d* samples/).first()).toBeVisible();

  await page.getByRole("button", { name: "Pause chart observation" }).first().click();
  await expect(page.getByText("observation paused").first()).toBeVisible();
  const paused = reads;
  await page.waitForTimeout(7_000);
  expect(reads).toBe(paused);
  // Pausing stops the sampling; it never discards what was already observed.
  await expect(page.getByText(/15 min window · [2-9]\d* samples/).first()).toBeVisible();

  await page.getByRole("button", { name: "Resume chart observation" }).first().click();
  await expect(page.getByText("observing every 5s").first()).toBeVisible();
  await expect.poll(() => reads, { timeout: 20_000 }).toBeGreaterThan(paused);
});

test("breadcrumb band shows the section and current page", async ({ page }) => {
  await page.goto("/workloads");
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs).toContainText("Workloads");
  await expect(crumbs).toContainText("Pods");
  await expect(crumbs.getByRole("listitem")).toHaveCount(2);
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
  // Wait for the shell to mount: a global shortcut sent before its listener is
  // registered is simply lost, and that race is not what this test is about.
  await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toBeVisible();
  await expect(async () => {
    await page.keyboard.press("Control+k");
    await expect(page.getByLabel("Search resources and commands")).toBeVisible({
      timeout: 2_000,
    });
  }).toPass({ timeout: 15_000 });
  const search = page.getByLabel("Search resources and commands");
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

test("pki secrets tab shows secret inventory with certificate expiry", async ({ page }) => {
  await page.goto("/pki");
  await page.getByRole("tab", { name: /Secrets/ }).click();
  await expect(page.getByText("transformer-db")).toBeVisible();
  await expect(page.getByText("kubernetes.io/tls").first()).toBeVisible();
  await expect(page.getByText("Expires")).toBeVisible();
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

test("database and kafka pages render tables and data availability", async ({ page }) => {
  await page.goto("/database");
  await expect(page.getByRole("heading", { name: "Database" })).toBeVisible();
  await expect(page.getByText("pg-svc").first()).toBeVisible();
  await expect(page.getByText("Row-level data").first()).toBeVisible();
  // The Data view joins the discovered database to its backing pod.
  await page.getByRole("tab", { name: "Data" }).click();
  await expect(page.getByText("transformer-abc").first()).toBeVisible();

  await page.goto("/kafka");
  await expect(page.getByRole("heading", { name: "Kafka" })).toBeVisible();
  await expect(page.getByText("kafka.devopsonm.svc:9093").first()).toBeVisible();
  await expect(page.getByText("Topic data availability").first()).toBeVisible();
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
  // `g` arms the chord for 900 ms. A human clears that easily; a browser
  // hosting twelve parallel workers can miss it between two separate CDP
  // keystrokes, so retry the *gesture* (not the assertion) and keep the test
  // measuring the chord rather than the scheduler.
  await expect(async () => {
    await page.keyboard.press("g");
    await page.keyboard.press("d");
    await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toBeVisible({
      timeout: 2_000,
    });
  }).toPass({ timeout: 20_000 });
});

test("incident workspace keeps notes local and shows evidence", async ({ page }) => {
  await page.goto("/incidents/INC12345");
  await expect(page.getByRole("heading", { name: /Incident INC12345/ })).toBeVisible();
  await expect(page.getByText("INCIDENT MODE")).toBeVisible();
  await expect(page.getByText("checked pods after rollout")).toBeVisible();
  await page.getByLabel("New incident note").fill("second observation");
  await page.getByRole("button", { name: "Add" }).click();
});

test("pre/post page compares a stored baseline and classifies the change", async ({ page }) => {
  await page.goto("/baselines");
  await expect(page.getByRole("heading", { name: "PRE / POST Change Validation" })).toBeVisible();
  await expect(page.getByText("CAPTURE PRE")).toBeVisible();
  await page.getByRole("button", { name: "Compare" }).first().click();
  await expect(page.getByText("DEGRADED")).toBeVisible();
  await expect(page.getByText("UNCHANGED")).toBeVisible();
});

test("exports page offers structured downloads only", async ({ page }) => {
  await page.goto("/exports");
  await expect(page.getByRole("heading", { name: "Exports" })).toBeVisible();
  await expect(page.getByRole("link", { name: "JSON" }).first()).toBeVisible();
  await expect(page.getByText(/never a screenshot/)).toBeVisible();
});

test("theme picker switches the whole palette", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.locator("html")).toHaveAttribute("data-theme", /.+/);

  await page.getByRole("button", { name: "Choose theme" }).click();
  await page.getByRole("menuitem", { name: /Nord/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "nord");
  await expect(page.locator("html")).toHaveClass(/dark/);

  await page.getByRole("button", { name: "Choose theme" }).click();
  await page.getByRole("menuitem", { name: /Solarized/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "solarized");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
});

test("topology discovers resources instead of demanding a typed name", async ({ page }) => {
  await page.goto("/topology");
  await expect(page.getByRole("heading", { name: "Dependency Topology" })).toBeVisible();
  // The picker is populated from the cluster and auto-selects the first object.
  await expect(page.getByLabel("Resource name")).toBeVisible();
  await expect(page.getByText(/available$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "GitOps chain" })).toBeVisible();
});

test("log viewer exposes pod/container/stream/window/tail options", async ({ page }) => {
  await page.goto("/logs");
  await expect(page.getByRole("heading", { name: "Log Viewer" })).toBeVisible();
  await expect(page.getByLabel("Pod")).toBeVisible();
  await expect(page.getByLabel("Container")).toBeVisible();
  await expect(page.getByLabel("Time window")).toBeVisible();
  await expect(page.getByLabel("Tail lines")).toBeVisible();
  await expect(page.getByLabel("Follow logs")).toBeVisible();
  await expect(page.getByLabel("Search logs")).toBeVisible();
  // The captured lines render with their level and text.
  await expect(page.getByText("ERROR certificate verify failed").first()).toBeVisible();
  await expect(page.getByText("Repeated patterns")).toBeVisible();
});

test("resource describe viewer offers describe/yaml/json/events options", async ({ page }) => {
  await page.goto("/describe");
  await expect(page.getByRole("heading", { name: "Resource Description" })).toBeVisible();
  await expect(page.getByLabel("Kind")).toBeVisible();
  await expect(page.getByLabel("Resource name")).toBeVisible();
  await expect(page.getByRole("button", { name: "YAML" })).toBeVisible();
  await expect(page.getByRole("button", { name: "JSON" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Events" })).toBeVisible();
  await expect(page.getByText("Name: log-transformer-def")).toBeVisible();
});

test("metrics charts expose a minutes/hours/days range selector", async ({ page }) => {
  await page.goto("/workloads");
  const range = page.getByLabel("Metrics range");
  await expect(range).toBeVisible();
  await range.selectOption("1h");
  await expect(range).toHaveValue("1h");
  // The chart states the window it is showing instead of implying more history.
  await expect(page.getByText(/1 hour window/).first()).toBeVisible();
});
