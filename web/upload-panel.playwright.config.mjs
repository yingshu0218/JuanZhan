import base from './reading.playwright.config.mjs';
export default {...base,testMatch:['upload-panel.spec.mjs','folder-upload.spec.mjs','upload-exclusions.spec.mjs'],outputDir:'/tmp/juanzhan-upload-panel-results'};
