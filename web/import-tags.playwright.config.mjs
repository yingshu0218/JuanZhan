import base from './reading.playwright.config.mjs';
export default {...base,testMatch:['import-tags.spec.mjs','agent-import.spec.mjs'],outputDir:'/tmp/juanzhan-import-tags-browser-results'};
