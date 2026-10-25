import base from './reading.playwright.config.mjs';
import {randomUUID} from 'node:crypto';
process.env.JUANZHAN_E2E_INDEXING='1';
process.env.JUANZHAN_E2E_MARKDOWN='1';
process.env.JUANZHAN_E2E_ARCHIVE_POINTER ||= '/tmp/juanzhan-controls-pointer-'+randomUUID()+'.txt';
export default {...base,testMatch:['job-controls.spec.mjs','jobs.spec.mjs'],outputDir:'/tmp/juanzhan-job-controls-results'};
