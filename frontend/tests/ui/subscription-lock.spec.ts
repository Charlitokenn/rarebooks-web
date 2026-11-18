import { expect, test, type Page } from '@playwright/test';
import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';
import { useBooksSession, waitForBooks } from './helpers/session';

// Locking the site needs `bench execute`; see frappe_books/tests/subscription.py.
const bench = process.env.BOOKS_FILTER_TEST_BENCH;
const site = process.env.BOOKS_FILTER_TEST_SITE;
test.skip(!bench || !site, 'Requires an explicit Frappe test bench and site');
useBooksSession();

const LOCKED = /Your books are read only\. Subscribe by .+ to keep your data\./;

async function benchExecute(method: string) {
  await promisify(execFile)('bench', ['--site', site!, 'execute', method], {
    cwd: bench,
    env: { ...process.env, PYTHONPATH: path.resolve(__dirname, '../../..') },
  });
}

const banner = (page: Page) => page.getByTestId('subscription-banner');

test.beforeAll(() =>
  benchExecute('frappe_books.tests.subscription.lock_hosted_site')
);
test.afterAll(() =>
  benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site')
);

/** Web workers cache site_config.json for 60 seconds, so wait until the server sees the lock. */
async function waitForLock(page: Page) {
  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          '/api/method/frappe_books.subscription.get_subscription'
        );
        return (await response.json()).message.phase;
      },
      { timeout: 90_000, intervals: [2_000] }
    )
    .toBe('locked');
}

test('a locked site shows the banner and refuses a save', async ({ page }) => {
  test.setTimeout(150_000);
  await waitForLock(page);
  await page.reload();
  await waitForBooks(page);
  await expect(banner(page).locator('p').first()).toHaveText(LOCKED);
  await expect(
    banner(page).getByRole('button', { name: 'Dismiss' })
  ).toHaveCount(0);

  const name = `Locked Coin ${Date.now()}`;
  await page.goto('/books/list/Currency');
  await waitForBooks(page);
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Currency Name (required)', exact: true })
    .fill(name);
  await page.keyboard.press('Tab');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();

  const dialog = page.getByRole('dialog', { name: 'Read only' });
  await expect(dialog).toContainText(LOCKED);
  const response = await page.request.get(
    `/api/v2/document/Currency/${encodeURIComponent(name)}`
  );
  expect(response.status()).toBe(404);
  await dialog.getByRole('button', { name: 'Okay' }).click();

  await banner(page).getByRole('button', { name: 'Subscribe' }).click();
  await expect(page).toHaveURL(/\/books\/subscription$/);
  await expect(page.getByRole('heading', { name: 'Read only' })).toBeVisible();
});
