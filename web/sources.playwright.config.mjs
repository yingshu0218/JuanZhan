import { defineConfig } from "@playwright/test";
import { randomBytes, randomUUID } from "node:crypto";
process.env.JUANZHAN_E2E_PASSWORD ||= randomBytes(24).toString("base64url");
process.env.JUANZHAN_E2E_SOURCE_ROOT ||=
  "/tmp/juanzhan-source-browser-" + randomUUID();
export default defineConfig({
  testDir: "./e2e",
  testMatch: "sources.spec.mjs",
  workers: 1,
  timeout: 180000,
  reporter: "list",
  outputDir: "/tmp/juanzhan-source-browser-results",
  use: {
    baseURL: "http://127.0.0.1:8768",
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      ...(process.env.JUANZHAN_CHROMIUM_PATH
        ? { executablePath: process.env.JUANZHAN_CHROMIUM_PATH }
        : {}),
      args: ["--no-sandbox"],
    },
  },
  webServer: {
    command: "../.venv/bin/python e2e/sources-server.py",
    url: "http://127.0.0.1:8769",
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15000 },
    timeout: 45000,
  },
});
