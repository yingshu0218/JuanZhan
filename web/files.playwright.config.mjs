import base from "./reading.playwright.config.mjs";
export default { ...base, testMatch:"files.spec.mjs", outputDir:"/tmp/juanzhan-files-browser-results" };
