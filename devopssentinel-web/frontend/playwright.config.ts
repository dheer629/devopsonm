import { defineConfig, devices } from "@playwright/test";

/**
 * Frontend-only E2E. The API is intercepted with deterministic fixtures so
 * this suite runs without a Kubernetes cluster (spec section 74). Real
 * cluster validation lives in the DevOpsSentinel WSL E2E harness.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-dark", use: { ...devices["Desktop Chrome"], colorScheme: "dark" } },
    { name: "desktop-light", use: { ...devices["Desktop Chrome"], colorScheme: "light" } },
  ],
  webServer: {
    command: "npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
