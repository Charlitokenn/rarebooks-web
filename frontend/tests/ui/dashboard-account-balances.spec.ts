import { expect, test, type Page, type Route } from '@playwright/test';
import { useBooksSession, waitForBooks } from './helpers/session';

useBooksSession();

const METHOD = /reports\.dashboard\.get_cash_balances/;
const AS_OF = '2031-12-15';

const card = (page: Page) =>
  page.locator('[data-slot="chart-container"]', {
    hasText: 'Account balances',
  });

function balances(accounts: { account: string; balance: number }[]) {
  const total = accounts.reduce((sum, row) => sum + row.balance, 0);
  return { message: { accounts, total, as_of: AS_OF } };
}

async function routeBalances(
  page: Page,
  handle: (route: Route) => Promise<void> | void
) {
  await page.route(METHOD, handle);
  await page.reload();
  await waitForBooks(page);
}

test('lists each balance with its total, colored by sign', async ({ page }) => {
  await routeBalances(page, (route) =>
    route.fulfill({
      json: balances([
        { account: 'Cash', balance: 100 },
        { account: 'Overdrawn Bank', balance: -60 },
        { account: 'Petty Cash', balance: 0 },
      ]),
    })
  );

  const rows = card(page).locator('tbody tr');
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0).locator('td').last()).toHaveClass(
    /text-ink-green-5/
  );
  await expect(rows.nth(1).locator('td').last()).toHaveClass(/text-ink-red-6/);
  await expect(rows.nth(1).locator('td').last()).toContainText('-');
  await expect(rows.nth(2).locator('td').last()).toHaveClass(/text-ink-gray-8/);
  await expect(rows.nth(2).locator('td').last()).toContainText('0.00');

  const total = card(page).locator('tfoot tr');
  await expect(total).toContainText('Total');
  await expect(total.locator('td')).toHaveClass(/text-ink-green-5/);
  await expect(total.getByRole('link')).toHaveCount(0);
});

test('the subtitle names the date the server used', async ({ page }) => {
  await routeBalances(page, (route) =>
    route.fulfill({ json: balances([{ account: 'Cash', balance: 1 }]) })
  );

  const subtitle = card(page).getByText(/^As of /);
  await expect(subtitle).toBeVisible();
  await expect(subtitle).not.toHaveText('As of today');
});

test('changing the period does not reload the balances', async ({ page }) => {
  await expect(card(page)).toHaveAttribute('data-state', /ready|empty/);
  let calls = 0;
  page.on('request', (request) => {
    if (METHOD.test(request.url())) {
      calls++;
    }
  });

  await page.getByRole('combobox').filter({ hasText: 'This year' }).click();
  await page.getByRole('option', { name: 'This quarter' }).click();
  await expect(
    page.getByRole('combobox').filter({ hasText: 'This quarter' })
  ).toBeVisible();
  await page.waitForLoadState('networkidle');

  expect(calls).toBe(0);
});

test('an account opens the General Ledger up to the as of date', async ({
  page,
}) => {
  await routeBalances(page, (route) =>
    route.fulfill({ json: balances([{ account: 'Cash', balance: 100 }]) })
  );

  await card(page).getByRole('link', { name: 'Cash', exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/books/report/GeneralLedger\\?.*account=Cash.*toDate=${AS_OF}`)
  );
  await expect(
    page
      .getByRole('group', { name: 'Filters', exact: true })
      .getByRole('combobox', { name: 'Account', exact: true })
  ).toHaveText(/Cash/);
});

test('no accounts shows the empty copy', async ({ page }) => {
  await routeBalances(page, (route) => route.fulfill({ json: balances([]) }));

  await expect(card(page)).toContainText('No cash or bank accounts');
});

test('a failed load can be retried', async ({ page }) => {
  let fail = true;
  await routeBalances(page, (route) =>
    fail
      ? route.fulfill({ status: 500, json: {} })
      : route.fulfill({ json: balances([{ account: 'Cash', balance: 5 }]) })
  );
  await expect(card(page)).toContainText('Failed to load');

  fail = false;
  await card(page).getByRole('button', { name: 'Try again' }).click();
  await expect(card(page).locator('tbody tr')).toHaveCount(1);
  await expect(card(page)).not.toContainText('Failed to load');
});

test('many rows scroll under a header and Total that stay visible', async ({
  page,
}) => {
  const accounts = Array.from({ length: 30 }, (_, index) => ({
    account: `Bank ${index + 1}`,
    balance: index + 1,
  }));
  await routeBalances(page, (route) =>
    route.fulfill({ json: balances(accounts) })
  );

  const last = card(page).getByRole('link', { name: 'Bank 30', exact: true });
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeInViewport();
  await expect(card(page).locator('thead')).toBeInViewport();
  await expect(card(page).locator('tfoot')).toBeInViewport();
  await expect(
    card(page).getByRole('link', { name: 'Bank 1', exact: true })
  ).not.toBeInViewport();
});

test('a slow older load does not overwrite a newer one', async ({ page }) => {
  let calls = 0;
  await routeBalances(page, async (route) => {
    calls++;
    if (calls === 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ json: balances([{ account: 'Old', balance: 1 }]) });
    } else {
      await route.fulfill({ json: balances([{ account: 'New', balance: 2 }]) });
    }
  });

  // Leaving and coming back activates the dashboard again while the first load waits.
  const sidebar = page.getByRole('navigation', { name: 'Books', exact: true });
  await sidebar.getByRole('link', { name: 'Sales', exact: true }).click();
  await sidebar.getByRole('link', { name: 'Dashboard' }).click();
  await expect(card(page).getByRole('link', { name: 'New' })).toBeVisible();

  await page.waitForTimeout(2000);
  await expect(card(page).getByRole('link', { name: 'New' })).toBeVisible();
  await expect(card(page).getByRole('link', { name: 'Old' })).toHaveCount(0);
});

test('the card takes the left half of its row', async ({ page }) => {
  await routeBalances(page, (route) =>
    route.fulfill({ json: balances([{ account: 'Cash', balance: 1 }]) })
  );

  const box = await card(page).boundingBox();
  const row = await card(page)
    .locator('xpath=ancestor::div[contains(@class, "lg:grid-cols-2")]')
    .boundingBox();
  expect(box && row).toBeTruthy();
  expect(box!.width).toBeLessThan(row!.width * 0.6);
  expect(Math.abs(box!.x - row!.x)).toBeLessThan(2);
});
