import { expect, test, type Page } from '@playwright/test';
import { useBooksSession, waitForBooks } from './helpers/session';

// Each screen points Documentation (F1 and the account menu) at its page on the RareBooks docs
// (spec 0015). window.open is recorded instead of opening a tab, so nothing leaves the test.

const DOCS = 'https://rarebooks.cc';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const opened: string[][] = [];
    Object.assign(window, { __docsOpened: opened });
    window.open = (...args: (string | URL | undefined)[]) => {
      opened.push(args.map(String));
      return null;
    };
  });
});

useBooksSession();

const opened = (page: Page) =>
  page.evaluate(
    () => (window as unknown as { __docsOpened: string[][] }).__docsOpened
  );

/** Presses F1 outside any field (shortcuts skip key presses typed into a field). */
async function pressF1(page: Page) {
  await page.evaluate(() => (document.activeElement as HTMLElement)?.blur());
  const before = (await opened(page)).length;
  await page.keyboard.press('F1');
  await expect.poll(async () => (await opened(page)).length).toBe(before + 1);
  return (await opened(page)).at(-1)!;
}

async function open(page: Page, path: string) {
  await page.goto(path);
  await waitForBooks(page);
}

const pushRoute = (page: Page, route: { path: string; query?: object }) =>
  page.evaluate(
    (to) =>
      (
        document.querySelector('#app') as any
      ).__vue_app__.config.globalProperties.$router.push(to),
    route
  );

const settings = (page: Page) => page.getByRole('dialog', { name: 'Settings' });

// covers: AC-2, AC-3, AC-4
for (const [screen, path, page] of [
  [
    'a Sales Invoice list',
    '/books/list/SalesInvoice',
    '/transactions/sales-invoice/',
  ],
  [
    'a new Sales Invoice',
    '/books/edit/SalesInvoice/new',
    '/transactions/sales-invoice/',
  ],
  ['the Dashboard', '/books/', '/basics/dashboard/'],
  [
    'the General Ledger',
    '/books/report/GeneralLedger',
    '/financial-reports/general-ledger/',
  ],
  ['the GSTR-1 report', '/books/report/GSTR1', '/financial-reports/reports/'],
  [
    'Chart of Accounts',
    '/books/chart-of-accounts',
    '/getting-started/chart-of-accounts/',
  ],
  [
    'the Import wizard',
    '/books/import-wizard',
    '/getting-started/import-wizard/',
  ],
  [
    'an Account list (no page of its own)',
    '/books/list/Account',
    '/masters/master-data/',
  ],
  [
    'a Sales Quote list',
    '/books/list/SalesQuote',
    '/transactions/sales-invoice/',
  ],
  ['an Expense list', '/books/list/Expense', '/transactions/payments/'],
  ['a Lead list', '/books/list/Lead', '/transactions/lead/'],
  ['a new Lead', '/books/edit/Lead/new', '/transactions/lead/'],
  [
    'Get started (no screen page)',
    '/books/get-started',
    '/getting-started/getting-started-with-rarebooks/',
  ],
  ['the POS', '/books/pos', '/transactions/point-of-sale/'],
]) {
  test(`F1 on ${screen} opens ${page} in a new tab`, async ({ page: tab }) => {
    await open(tab, path);
    expect(await pressF1(tab)).toEqual([
      DOCS + page,
      '_blank',
      'noopener,noreferrer',
    ]);
  });
}

// covers: AC-3
test('the account menu Documentation item opens the same page as F1', async ({
  page,
}) => {
  await open(page, '/books/list/SalesInvoice');
  await page.getByTestId('company-name').getByRole('button').click();
  await page.getByRole('menuitem', { name: 'Documentation' }).click();
  await expect
    .poll(async () => (await opened(page)).at(-1)?.[0])
    .toBe(DOCS + '/transactions/sales-invoice/');
});

// covers: AC-5
test('the search bar Help opens the quick search page', async ({ page }) => {
  await open(page, '/books/list/SalesInvoice');
  await page.keyboard.press('ControlOrMeta+KeyK');
  await page.getByRole('button', { name: 'Help' }).click();
  await expect
    .poll(async () => (await opened(page)).at(-1)?.[0])
    .toBe(DOCS + '/getting-started/quick-search/');
});

// covers: AC-7
test('the Settings dialog follows its tab and closes back to the screen underneath', async ({
  page,
}) => {
  await open(page, '/books/list/Item');
  await pushRoute(page, { path: '/settings' });
  await expect(settings(page)).toBeVisible();
  expect((await pressF1(page))[0]).toBe(DOCS + '/settings/settings/');

  for (const [tab, docsPage] of [
    ['Inventory', '/inventory/inventory-settings/'],
    ['POS Settings', '/transactions/point-of-sale/'],
    ['Print', '/settings/settings/'],
  ]) {
    await settings(page).getByRole('tab', { name: tab }).click();
    expect((await pressF1(page))[0], tab).toBe(DOCS + docsPage);
  }

  await page.keyboard.press('Escape');
  await expect(settings(page)).toHaveCount(0);
  expect((await pressF1(page))[0]).toBe(DOCS + '/masters/items/');
});

// covers: AC-7 (the Dashboard activates after the dialog on a cold load; it must not take over)
test('a cold load of a Settings tab keeps its page over the Dashboard', async ({
  page,
}) => {
  await open(page, '/books/settings?tab=InventorySettings');
  await expect(settings(page)).toBeVisible();
  expect((await pressF1(page))[0]).toBe(
    DOCS + '/inventory/inventory-settings/'
  );

  await page.keyboard.press('Escape');
  await expect(settings(page)).toHaveCount(0);
  expect((await pressF1(page))[0]).toBe(DOCS + '/basics/dashboard/');
});

// covers: AC-7
test('a route change that closes the dialog leaves the new screen its own page', async ({
  page,
}) => {
  await open(page, '/books/list/Item');
  await pushRoute(page, {
    path: '/settings',
    query: { tab: 'InventorySettings' },
  });
  await expect(settings(page)).toBeVisible();
  await pushRoute(page, { path: '/list/SalesInvoice' });
  await expect(settings(page)).toHaveCount(0);
  await waitForBooks(page);
  expect((await pressF1(page))[0]).toBe(DOCS + '/transactions/sales-invoice/');
});

/** Phones have no F1 (the sidebar that listens for it is a drawer): use the account menu. */
async function openFromMenu(page: Page) {
  const before = (await opened(page)).length;
  await page.locator('header button').first().click();
  await page.getByTestId('company-name').getByRole('button').click();
  await page.getByRole('menuitem', { name: 'Documentation' }).click();
  await expect.poll(async () => (await opened(page)).length).toBe(before + 1);
  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  return (await opened(page)).at(-1)![0];
}

test.describe('on a phone', () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  // covers: AC-7
  test('the Settings page follows its tab', async ({ page }) => {
    await page.goto('/books/settings?tab=InventorySettings');
    await expect(page.getByRole('radio', { name: 'Inventory' })).toBeChecked();
    expect(await openFromMenu(page)).toBe(
      DOCS + '/inventory/inventory-settings/'
    );

    await page.getByRole('radio', { name: 'POS Settings' }).click();
    expect(await openFromMenu(page)).toBe(
      DOCS + '/transactions/point-of-sale/'
    );
  });
});
