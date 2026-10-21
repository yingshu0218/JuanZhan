import { defineConfig } from "@playwright/test";
import { randomBytes } from "node:crypto";
process.env.JUANZHAN_E2E_PASSWORD ||= randomBytes(24).toString("base64url");
export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["oauth.spec.mjs", "agents.spec.mjs", "overview-formats.spec.mjs", "backups.spec.mjs", "sources.spec.mjs", "reading.spec.mjs", "search.spec.mjs", "jobs.spec.mjs", "files.spec.mjs"],
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  reporter: "list",
  outputDir: process.env.JUANZHAN_QA_DIR || "/tmp/juanzhan-browser-results",
  use: {
    baseURL: "http://127.0.0.1:8767",
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      ...(process.env.JUANZHAN_CHROMIUM_PATH
        ? { executablePath: process.env.JUANZHAN_CHROMIUM_PATH }
        : {}),
      args: ["--no-sandbox"],
    },
  },
  webServer: {
    command: "../.venv/bin/python e2e/server.py",
    url: "http://127.0.0.1:8767/healthz",
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15000 },
    timeout: 30000,
  },
});
