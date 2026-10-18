import base from "./reading.playwright.config.mjs";
export default { ...base, testMatch: "jobs.spec.mjs", outputDir: "/tmp/juanzhan-jobs-browser-results" };
