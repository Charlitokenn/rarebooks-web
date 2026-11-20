import { expect, test, type Page, type Route } from '@playwright/test';
import {
  useBooksSession,
  waitForBooks,
  withoutBootRights,
} from './helpers/session';

useBooksSession();

const SETTINGS = 'Books Accounting Settings';

const METHOD = /reports\.dashboard\.get_cash_balances/;
const AS_OF = '2031-12-15';

const card = (page: Page) =>
  page.locator('[data-slot="chart-container"]', {
    hasText: 'Account balances',
  });

// A button with a route renders as a link.
const chooseAccounts = (page: Page) =>
  card(page).getByRole('link', { name: 'Choose accounts', exact: true });

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

/** A response the test lets through when it is ready. */
function gate() {
  let open!: () => void;
  const opened = new Promise<void>((resolve) => (open = resolve));
  return { open, opened };
}

/** Leaving and coming back activates the dashboard, which loads the card again. */
async function revisitDashboard(page: Page) {
  const sidebar = page.getByRole('navigation', { name: 'Books', exact: true });
  await sidebar.getByRole('link', { name: 'Sales', exact: true }).click();
  await sidebar.getByRole('link', { name: 'Dashboard' }).click();
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

// covers: AC-10, AC-3
test('the first load shows three skeleton rows under "As of today"', async ({
  page,
}) => {
  const first = gate();
  await routeBalances(page, async (route) => {
    await first.opened;
    await route.fulfill({ json: balances([{ account: 'Cash', balance: 1 }]) });
  });

  await expect(card(page)).toHaveAttribute('data-state', 'loading');
  await expect(
    card(page).locator('[data-slot="chart-loading"] > div > div')
  ).toHaveCount(3);
  await expect(
    card(page).getByText('As of today', { exact: true })
  ).toBeVisible();

  first.open();
  await expect(card(page).getByRole('link', { name: 'Cash' })).toBeVisible();
  await expect(
    card(page).getByText('As of today', { exact: true })
  ).toHaveCount(0);
});

// covers: AC-10
test('a reload keeps the previous rows on screen until it settles', async ({
  page,
}) => {
  const second = gate();
  let calls = 0;
  await routeBalances(page, async (route) => {
    calls++;
    if (calls === 1) {
      await route.fulfill({
        json: balances([{ account: 'Cash', balance: 1 }]),
      });
      return;
    }
    await second.opened;
    await route.fulfill({ json: balances([{ account: 'Bank', balance: 2 }]) });
  });
  await expect(card(page).getByRole('link', { name: 'Cash' })).toBeVisible();

  await revisitDashboard(page);
  await expect.poll(() => calls).toBe(2);

  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  await expect(card(page).getByRole('link', { name: 'Cash' })).toBeVisible();
  await expect(card(page).locator('[data-slot="chart-loading"]')).toHaveCount(
    0
  );

  second.open();
  await expect(card(page).getByRole('link', { name: 'Bank' })).toBeVisible();
  await expect(card(page).getByRole('link', { name: 'Cash' })).toHaveCount(0);
});

// covers: AC-10
test('a failed reload replaces rows that loaded earlier', async ({ page }) => {
  let calls = 0;
  await routeBalances(page, (route) => {
    calls++;
    return calls === 1
      ? route.fulfill({ json: balances([{ account: 'Cash', balance: 1 }]) })
      : route.fulfill({ status: 500, json: {} });
  });
  await expect(card(page).getByRole('link', { name: 'Cash' })).toBeVisible();

  await revisitDashboard(page);

  await expect(card(page)).toHaveAttribute('data-state', 'error');
  await expect(card(page)).toContainText('Failed to load');
  await expect(card(page).getByRole('link', { name: 'Cash' })).toBeHidden();
});

// covers: AC-12
test('a stale load that fails writes nothing, not even to the console', async ({
  page,
}) => {
  const first = gate();
  let calls = 0;
  await routeBalances(page, async (route) => {
    calls++;
    if (calls === 1) {
      await first.opened;
      await route.fulfill({ status: 500, json: {} });
      return;
    }
    await route.fulfill({ json: balances([{ account: 'New', balance: 2 }]) });
  });

  await revisitDashboard(page);
  await expect(card(page).getByRole('link', { name: 'New' })).toBeVisible();

  const errors: string[] = [];
  page.on('console', (message) => {
    // The browser reports the 500 itself; only the card's own log counts.
    if (
      message.type() === 'error' &&
      !message.text().includes('Failed to load resource')
    ) {
      errors.push(message.text());
    }
  });
  const stale = page.waitForResponse(
    (response) => METHOD.test(response.url()) && response.status() === 500
  );
  first.open();
  await stale;
  await page.waitForTimeout(500);

  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  await expect(card(page)).not.toContainText('Failed to load');
  await expect(card(page).getByRole('link', { name: 'New' })).toBeVisible();
  expect(errors).toEqual([]);
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

// covers: AC-7
test('"Choose accounts" shows while loading, on error, empty and loaded', async ({
  page,
}) => {
  const first = gate();
  let calls = 0;
  await routeBalances(page, async (route) => {
    calls++;
    if (calls === 1) {
      await first.opened;
      return route.fulfill({ status: 500, json: {} });
    }
    return route.fulfill({
      json: balances(calls === 2 ? [] : [{ account: 'Cash', balance: 1 }]),
    });
  });

  for (const [state, next] of [
    ['loading', () => first.open()],
    [
      'error',
      () => card(page).getByRole('button', { name: 'Try again' }).click(),
    ],
    ['empty', () => revisitDashboard(page)],
    ['ready', async () => {}],
  ] as const) {
    await expect(card(page)).toHaveAttribute('data-state', state);
    await expect(chooseAccounts(page)).toBeVisible();
    await next();
  }
});

// covers: AC-7
test('"Choose accounts" opens the General tab of the settings dialog', async ({
  page,
}) => {
  await routeBalances(page, (route) =>
    route.fulfill({ json: balances([{ account: 'Cash', balance: 1 }]) })
  );

  // Hover once the card has loaded, so the header is not redrawn under the pointer.
  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  // The tooltip opens on pointer movement, so leave and enter again until it shows.
  await expect(async () => {
    await page.mouse.move(0, 0);
    await chooseAccounts(page).hover();
    await expect(page.locator('[data-slot="bubble"]')).toHaveText(
      'Choose accounts',
      { timeout: 2000 }
    );
  }).toPass();
  await chooseAccounts(page).click();

  const settings = page.getByRole('dialog', { name: 'Settings' });
  await expect(settings.getByRole('tab', { name: 'General' })).toHaveAttribute(
    'aria-selected',
    'true'
  );
  await expect(settings.getByText('Dashboard Accounts')).toBeVisible();
});

test.describe('with fewer rights on the settings', () => {
  // The Books service worker answers a reload from its cache, past the page's routes.
  test.use({ serviceWorkers: 'block' });

  // covers: AC-7
  test('without write the card shows but the button does not', async ({
    page,
  }) => {
    await withoutBootRights(page, SETTINGS, ['write']);
    await routeBalances(page, (route) =>
      route.fulfill({ json: balances([{ account: 'Cash', balance: 1 }]) })
    );

    await expect(card(page).getByRole('link', { name: 'Cash' })).toBeVisible();
    await expect(chooseAccounts(page)).toHaveCount(0);
  });

  // covers: AC-9
  test('without read the card is not shown', async ({ page }) => {
    await withoutBootRights(page, SETTINGS, ['read', 'write']);
    await page.reload();
    await waitForBooks(page);

    await expect(
      page.locator('[data-slot="chart-container"]', {
        hasText: 'Best sellers',
      })
    ).toBeVisible();
    await expect(card(page)).toHaveCount(0);
  });
});
