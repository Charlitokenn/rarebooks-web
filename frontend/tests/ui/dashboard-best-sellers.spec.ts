import { expect, test, type Page, type Route } from '@playwright/test';
import { useBooksSession, waitForBooks } from './helpers/session';

useBooksSession();

const METHOD = /reports\.dashboard\.get_best_sellers/;

const card = (page: Page) =>
  page.locator('[data-slot="chart-container"]', { hasText: 'Best sellers' });

const legend = (page: Page) => card(page).locator('[data-slot="chart-legend"]');

const FIVE = [
  { item: 'Folio Atlas', amount: 500 },
  { item: 'Map Case', amount: 400 },
  { item: 'Vellum Bible', amount: 300 },
  { item: 'Quarto Hymnal', amount: 200 },
  { item: 'Octavo Novel', amount: 100 },
];

function sellers(items: { item: string; amount: number }[], total?: number) {
  const sum = items.reduce((value, row) => value + row.amount, 0);
  return { message: { items, total: total ?? sum } };
}

async function routeSellers(
  page: Page,
  handle: (route: Route) => Promise<void> | void
) {
  await page.route(METHOD, handle);
  await page.reload();
  await waitForBooks(page);
}

/** Drops a doctype from the boot's read list before Books reads it. */
async function denyRead(page: Page, doctype: string) {
  await page.addInitScript((denied) => {
    let boot: { user?: { can_read?: string[] } } | undefined;
    const frappe: Record<string, unknown> = {};
    Object.defineProperty(frappe, 'boot', {
      configurable: true,
      get: () => boot,
      set(value) {
        boot = value;
        const user = boot?.user;
        if (user?.can_read) {
          user.can_read = user.can_read.filter((name) => name !== denied);
        }
      },
    });
    (window as unknown as { frappe: unknown }).frappe = frappe;
  }, doctype);
}

async function rowBox(page: Page) {
  return card(page)
    .locator('xpath=ancestor::div[contains(@class, "lg:grid-cols-2")]')
    .boundingBox();
}

// covers: AC-6
test('shows the five items, the server total and a Top 5 centre', async ({
  page,
}) => {
  await routeSellers(page, (route) =>
    route.fulfill({ json: sellers(FIVE, 1800) })
  );

  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  await expect(card(page)).toContainText('Total sales:');
  await expect(card(page)).toContainText('1,800.00');
  await expect(card(page)).toContainText('Top 5');
  for (const { item } of FIVE) {
    await expect(
      legend(page).getByRole('button', { name: item })
    ).toBeVisible();
  }
  await expect(legend(page).getByRole('button')).toHaveCount(5);
  await expect(legend(page)).not.toContainText('Others');
});

// covers: AC-6
test('the centre names how many items came back', async ({ page }) => {
  await routeSellers(page, (route) =>
    route.fulfill({ json: sellers(FIVE.slice(0, 3)) })
  );

  await expect(card(page)).toContainText('Top 3');
  await expect(legend(page).getByRole('button')).toHaveCount(3);
});

// covers: AC-6
test('hiding a legend entry recomputes the centre but keeps the Top N label', async ({
  page,
}) => {
  await routeSellers(page, (route) => route.fulfill({ json: sellers(FIVE) }));
  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  const label = card(page).getByText('Top 5', { exact: true });
  // The label sits in the centre slot's second line; the value is the first.
  const value = label.locator('xpath=../../div[1]');
  const before = await value.innerText();

  await legend(page).getByRole('button', { name: 'Folio Atlas' }).click();

  await expect(value).not.toHaveText(before);
  await expect(label).toBeVisible();
  await expect(card(page)).toContainText('1,500.00');
});

// covers: AC-7
test('changing the period loads the chart for the new period', async ({
  page,
}) => {
  const periods: string[] = [];
  await routeSellers(page, (route) => {
    periods.push(route.request().postDataJSON()?.period);
    return route.fulfill({ json: sellers(FIVE) });
  });
  await expect(card(page)).toHaveAttribute('data-state', 'ready');

  await page.getByRole('combobox').filter({ hasText: 'This year' }).click();
  await page.getByRole('option', { name: 'This quarter' }).click();

  await expect.poll(() => periods.at(-1)).toBe('This Quarter');
});

// covers: AC-9
test('no sales shows the empty copy', async ({ page }) => {
  await routeSellers(page, (route) => route.fulfill({ json: sellers([]) }));

  await expect(card(page)).toContainText('No sales in this period');
  await expect(card(page)).not.toContainText('Total sales');
});

// covers: AC-9
test('a failed load can be retried', async ({ page }) => {
  let fail = true;
  await routeSellers(page, (route) =>
    fail
      ? route.fulfill({ status: 500, json: {} })
      : route.fulfill({ json: sellers(FIVE) })
  );
  await expect(card(page)).toContainText('Failed to load');

  fail = false;
  await card(page).getByRole('button', { name: 'Try again' }).click();
  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  await expect(card(page)).not.toContainText('Failed to load');
});

// covers: AC-11
test('clicking a slice or a legend entry does not navigate', async ({
  page,
}) => {
  await routeSellers(page, (route) => route.fulfill({ json: sellers(FIVE) }));
  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  const url = page.url();

  const plot = card(page).locator('canvas, svg').first();
  const box = (await plot.boundingBox())!;
  // The ring's top edge, where the largest slice starts.
  await page.mouse.click(box.x + box.width / 2 + 10, box.y + box.height * 0.1);
  await legend(page).getByRole('button', { name: 'Map Case' }).click();

  await expect(
    legend(page).getByRole('button', { name: 'Map Case' })
  ).toHaveAttribute('aria-pressed', 'false');
  expect(page.url()).toBe(url);
});

// covers: AC-10
test('the card takes the right half next to Account balances', async ({
  page,
}) => {
  await routeSellers(page, (route) => route.fulfill({ json: sellers(FIVE) }));

  const box = await card(page).boundingBox();
  const row = await rowBox(page);
  expect(box && row).toBeTruthy();
  expect(box!.width).toBeLessThan(row!.width * 0.6);
  expect(Math.abs(box!.x + box!.width - (row!.x + row!.width))).toBeLessThan(2);
});

// covers: AC-8, AC-10
test('without ledger read the card takes the left half', async ({ page }) => {
  await denyRead(page, 'Books Ledger Entry');
  await routeSellers(page, (route) => route.fulfill({ json: sellers(FIVE) }));

  await expect(card(page)).toHaveAttribute('data-state', 'ready');
  await expect(
    page.locator('[data-slot="chart-container"]', {
      hasText: 'Account balances',
    })
  ).toHaveCount(0);
  const box = await card(page).boundingBox();
  const row = await rowBox(page);
  expect(box && row).toBeTruthy();
  expect(box!.width).toBeLessThan(row!.width * 0.6);
  expect(Math.abs(box!.x - row!.x)).toBeLessThan(2);
});
