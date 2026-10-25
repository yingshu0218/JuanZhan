import base from './upload-panel.playwright.config.mjs';
export default {...base,testMatch:[...base.testMatch,'upload-policy.spec.mjs'],outputDir:'/tmp/juanzhan-upload-policy-results'};
