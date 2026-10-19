import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/grid',
  testMatch: '**/*.e2e.cjs',
  timeout: 60_000,
  workers: 1,
  outputDir: './.codex-output/grid-playwright',
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:15175',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    headless: true,
    viewport: { width: 1450, height: 1000 },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 15175 --strictPort',
    url: 'http://127.0.0.1:15175/tests/grid/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
