import { expect, test } from '@playwright/test';
import { useBooksSession } from './helpers/session';

useBooksSession('/books');

test('the app opened at /books lands on /books/, inside the manifest scope', async ({
  page,
}) => {
  // Chrome shows its URL bar over an installed app on any page outside the scope.
  await expect(page).toHaveURL(/\/books\/$/);

  const href = await page.locator('link[rel="manifest"]').getAttribute('href');
  const response = await page.request.get(href!);
  const manifest = await response.json();

  expect(response.headers()['cache-control']).toBe('no-cache');
  expect(new URL(page.url()).pathname.startsWith(manifest.scope)).toBe(true);
  expect('/books'.startsWith(manifest.scope)).toBe(true);
  expect(manifest.short_name).toBe('RareBooks');
});

test('a deep link keeps its path and query', async ({ page }) => {
  await page.goto('/books/list/SalesInvoice?status=Paid');

  await expect(page).toHaveURL(/\/books\/list\/SalesInvoice\?status=Paid$/);
});
