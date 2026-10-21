import base from './playwright.config.mjs';
export default {
  ...base, testIgnore: [], testMatch: ['oauth.spec.mjs'],
  outputDir: '/tmp/juanzhan-oauth-browser-results',
  webServer: { ...base.webServer, command: '../.venv/bin/python e2e/oauth-server.py' },
};
