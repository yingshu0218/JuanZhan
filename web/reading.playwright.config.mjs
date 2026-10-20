import base from "./playwright.config.mjs";
export default {
  ...base,
  testIgnore: [],
  testMatch: ["reading.spec.mjs", "overview-formats.spec.mjs"],
  outputDir: "/tmp/juanzhan-reading-browser-results",
  webServer: { ...base.webServer, command: "../.venv/bin/python e2e/reading-server.py", timeout: 45000 },
};
