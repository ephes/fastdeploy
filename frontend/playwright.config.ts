import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './browser-tests',
  use: { baseURL: 'http://127.0.0.1:5178' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5178 --strictPort',
    url: 'http://127.0.0.1:5178',
    reuseExistingServer: !process.env.CI,
  },
});
