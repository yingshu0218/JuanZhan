import base from './reading.playwright.config.mjs';
export default {...base,testIgnore:[],testMatch:['overview-only.spec.mjs','source-files.spec.mjs'],outputDir:'/tmp/juanzhan-source-files-results'};
