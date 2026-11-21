import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';

async function intercept(page: Page, token: string, deployments = (_url: URL): unknown => []) {
  await page.route('http://localhost:8000/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const headers = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'authorization,content-type',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    };
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers });
      return;
    }
    await route.fulfill({
      status: 200,
      headers,
      contentType: 'application/json',
      body: path === '/token' ? token : path === '/services/'
        ? '[{"id":1,"name":"kept","data":{}}]' : path === '/deployments/'
          ? JSON.stringify(deployments(url)) : '[]',
    });
  });
}
async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill('synthetic');
  await page.getByLabel('Password', { exact: true }).fill('synthetic');
  await page.getByLabel('Password', { exact: true }).press('Enter');
}

test('duplicate decoded token members cannot log in', async ({ page }) => {
  await intercept(page, '{"access_token":"first","access_\\u0074oken":"second"}');
  await login(page);
  await expect(page.getByRole('button', { name: 'Login', exact: true })).toBeEnabled();
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('heading', { name: 'Services', exact: true })).toHaveCount(0);
});

for (const raw of [
  '{"type":"service","id":1,"name":"replaced","data":{"key":1,"k\\u0065y":2}}',
  '{"type":"deployment","id":2,"service_id":1,"origin":"fixture","user":"synthetic","started":"2026-02-30T12:00:00Z","finished":null}',
]) {
  test(`invalid websocket preserves the visible snapshot: ${raw}`, async ({ page }) => {
    await intercept(page, '{"access_token":"synthetic"}');
    let socket!: WebSocketRoute;
    await page.routeWebSocket('ws://localhost:8000/**', ws => {
      socket = ws;
      ws.onMessage(() => ws.send('{"type":"authentication","status":"success"}'));
    });
    await login(page);
    await expect(page.getByRole('button', { name: 'Deploy kept', exact: true })).toBeVisible();
    socket.send(raw);
    await expect(page.getByRole('alert')).toContainText('Invalid websocket message');
    await expect(page.getByRole('button', { name: 'Deploy kept', exact: true })).toBeVisible();
    await expect(page.getByText('replaced', { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL('/');
  });
}


test('conflicting REST row type leaves the previous history page usable', async ({ page }) => {
  const row = (id: number) => ({
    id, service_id: 1, origin: 'fixture', user: 'synthetic',
    started: '2026-11-01T00:00:00Z', finished: null,
  });
  await intercept(page, '{"access_token":"synthetic"}', url => url.searchParams.has('before_id')
    ? [{ ...row(1), type: 'step' }]
    : Array.from({ length: 50 }, (_, index) => row(51 - index)));
  await page.routeWebSocket('ws://localhost:8000/**', ws => {
    ws.onMessage(() => ws.send('{"type":"authentication","status":"success"}'));
  });
  await login(page);
  await page.getByRole('link', { name: 'Deployments', exact: true }).click();
  await expect(page.getByRole('link', { name: 'details for 51', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Load more', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Could not load deployment history');
  await expect(page.getByRole('link', { name: 'details for 1', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'details for 51', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry history', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Load more', exact: true })).toBeEnabled();
});
