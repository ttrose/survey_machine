import { defineConfig, devices } from '@playwright/test';

const d1 = process.env.SM_TEST_D1 === '1';
const port = d1 ? 8788 : 8001;

export default defineConfig({
  testDir: './tests/browser',
  outputDir: './test-results/' + (d1 ? 'd1' : 'sqlite'),
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:' + port,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...(process.env.PLAYWRIGHT_WS_ENDPOINT ? { connectOptions: { wsEndpoint: process.env.PLAYWRIGHT_WS_ENDPOINT } } : {}),
  },
  projects: [{ name: d1 ? 'chromium-d1' : 'chromium-sqlite', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'uv run --extra local --extra dev --group workers python scripts/test_server.py --backend ' + (d1 ? 'd1' : 'sqlite') + ' --port ' + port,
    url: 'http://127.0.0.1:' + port + '/health',
    timeout: 180_000,
    reuseExistingServer: false,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 20_000 },
  },
});
