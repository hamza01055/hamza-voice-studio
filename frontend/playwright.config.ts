import { defineConfig } from "@playwright/test";

// E2E tests start their own backend (see tests/e2e/server.ts) on a separate port and
// data directory. They need the built frontend (npm run build) and, for the real
// generation workflow, installed Kokoro weights (HVS_E2E_MODELS_DIR).
export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    headless: true,
    viewport: { width: 1440, height: 900 },
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
    trace: "retain-on-failure",
  },
});
