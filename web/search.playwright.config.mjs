import base from "./reading.playwright.config.mjs";
export default {
  ...base,
  testMatch: "search.spec.mjs",
  outputDir: "/tmp/juanzhan-search-browser-results",
  webServer: { ...base.webServer, command: "JUANZHAN_E2E_INDEXING=1 ../.venv/bin/python e2e/reading-server.py" },
};
