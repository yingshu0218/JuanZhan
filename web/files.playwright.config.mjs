import base from "./reading.playwright.config.mjs";
import {randomUUID} from "node:crypto";
process.env.JUANZHAN_E2E_ARCHIVE_POINTER ||= "/tmp/juanzhan-files-pointer-"+randomUUID()+".txt";
export default { ...base, testMatch:"files.spec.mjs", outputDir:"/tmp/juanzhan-files-browser-results" };
