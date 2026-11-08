const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 120000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  globalSetup: require.resolve('./tests/e2e/email-safety-setup.cjs'),
  reporter: [['list'], ['json', { outputFile: 'artifacts/browser-acceptance.json' }]],
  outputDir: 'artifacts/browser-results',
  use: { baseURL: process.env.IBANKING_E2E_BASE_URL || 'http://127.0.0.1:8001', headless: true, channel: process.platform === 'win32' ? 'msedge' : undefined,
    viewport: { width: 1440, height: 1000 }, screenshot: 'only-on-failure', trace: 'off' },
});
