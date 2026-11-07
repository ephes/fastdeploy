import { test, expect } from '@playwright/test';

test('credential Enter submission is native, single-flight and retryable', async ({ page }) => {
  let attempts = 0;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization,content-type',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  };
  await page.route('http://localhost:8000/**', async route => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers });
    } else if (new URL(route.request().url()).pathname === '/token') {
      attempts++;
      if (attempts === 1) await pending;
      await route.fulfill({ status: attempts === 1 ? 401 : 200, headers,
        contentType: 'application/json', body: attempts === 1
          ? JSON.stringify({ detail: 'Invalid credentials' })
          : JSON.stringify({ access_token: 'synthetic-access-value' }) });
    } else {
      await route.fulfill({ headers, contentType: 'application/json', body: '[]' });
    }
  });
  // Keep all session transport synthetic, including the post-login websocket.
  await page.routeWebSocket('ws://localhost:8000/**', () => {});
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill('fixture-user');
  await page.getByLabel('Password', { exact: true }).fill('fixture-password');
  await page.getByLabel('Username', { exact: true }).press('Enter');
  await expect.poll(() => attempts).toBe(1);
  await expect(page.getByRole('button', { name: 'Logging in…' })).toBeDisabled();
  await page.getByLabel('Password', { exact: true }).press('Enter');
  expect(attempts).toBe(1);
  release();
  await expect(page.getByRole('alert')).toContainText('Invalid username or password');
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('fixture-password');
  await page.getByLabel('Password', { exact: true }).press('Enter');
  await expect(page).toHaveURL('/');
  expect(attempts).toBe(2);
});
