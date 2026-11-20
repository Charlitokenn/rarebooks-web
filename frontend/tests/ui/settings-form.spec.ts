import { expect, test, type Page } from '@playwright/test';
import {
  getLeafAccounts,
  insertDocument,
  updateSingle,
} from './helpers/records';
import { useBooksSession, waitForBooks } from './helpers/session';

// Frappe serves the settings singles; desktop shows them in a dialog over the dashboard.
useBooksSession('/books/settings');

const SETTINGS = 'Books Accounting Settings';

const settings = (page: Page) => page.getByRole('dialog', { name: 'Settings' });
const balancesCard = (page: Page) =>
  page.locator('[data-slot="chart-container"]', {
    hasText: 'Account balances',
  });

test('settings open over the page they were opened from', async ({ page }) => {
  await expect(page).toHaveURL(/\/books\/?$/);
  await expect(settings(page)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(settings(page)).toHaveCount(0);

  await page.goto('/books/list/SalesInvoice');
  await waitForBooks(page);
  await page.evaluate(() =>
    (
      document.querySelector('#app') as any
    ).__vue_app__.config.globalProperties.$router.push({
      path: '/settings',
      query: { tab: 'PrintSettings' },
    })
  );
  await expect(
    settings(page).getByRole('tab', { name: 'Print' })
  ).toHaveAttribute('aria-selected', 'true');
  await expect(page).toHaveURL(/\/books\/list\/SalesInvoice$/);
});

test('the System tab saves through Frappe and keeps the value after a reload', async ({
  page,
}) => {
  await settings(page).getByRole('tab', { name: 'System' }).click();
  const bypass = page.getByRole('switch', {
    name: 'Allow to bypass filters',
  });
  const wasChecked = await bypass.isChecked();
  await expect(page.getByRole('combobox', { name: 'Date Format' })).toHaveValue(
    /\d{4}/
  );
  await expect(page.getByRole('textbox', { name: 'Currency' })).toBeDisabled();
  const save = page.getByRole('button', { name: 'Save', exact: true });
  await expect(save).toBeDisabled();

  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().includes('/api/v2/document/Books%20System%20Settings')
  );
  await bypass.click();
  await save.click();
  expect((await saved).ok()).toBe(true);
  const reloaded = page.waitForEvent('load');
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await reloaded;
  await waitForBooks(page);

  await page.goto('/books/settings?tab=SystemSettings');
  await waitForBooks(page);
  await expect(bypass).toBeChecked({ checked: !wasChecked });
  await bypass.click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await expect(bypass).toBeChecked({ checked: wasChecked });
});

test('the General tab shows the company country read only', async ({
  page,
}) => {
  await expect(
    settings(page).getByRole('tab', { name: 'General' })
  ).toHaveAttribute('aria-selected', 'true');
  const country = page.getByRole('textbox', { name: 'Country' });
  await expect(country).toBeDisabled();
  await expect(country).not.toHaveValue('');
});

// covers: AC-1, AC-2, AC-4, AC-5, AC-6
test('accounts picked on the General tab show on the card after the reload', async ({
  page,
}) => {
  // Three full app loads: the tab, the reload after Save, and the dashboard.
  test.slow();
  const [asset] = await getLeafAccounts(page, 'Asset');
  const [liability] = await getLeafAccounts(page, 'Liability');
  const [income] = await getLeafAccounts(page, 'Income');
  await updateSingle(page, SETTINGS, { dashboard_accounts: [] });
  // A reload would land on the dashboard without the dialog, so open the tab again.
  await page.goto('/books/settings?tab=AccountingSettings');
  await waitForBooks(page);

  try {
    await expect(
      settings(page).getByText(
        "The accounts the dashboard's Account balances card lists. Leave empty to list every cash and bank account."
      )
    ).toBeVisible();
    await settings(page).getByText('Add row', { exact: true }).click();
    const account = settings(page)
      .getByRole('combobox', { name: 'Account', exact: true })
      .last();
    await account.click();
    await account.fill(income.slice(0, 6));
    await expect(page.getByRole('option', { name: income })).toHaveCount(0);
    await expect(page.getByRole('option', { name: /^Create/ })).toHaveCount(0);
    await account.fill(asset);
    await page.getByRole('option', { name: asset, exact: true }).click();

    await settings(page).getByText('Add row', { exact: true }).click();
    await account.click();
    await account.fill(liability);
    await page.getByRole('option', { name: liability, exact: true }).click();

    await page.getByRole('button', { name: 'Save', exact: true }).click();
    const reloaded = page.waitForEvent('load');
    await page.getByRole('button', { name: 'Yes', exact: true }).click();
    await reloaded;
    await page.goto('/books');
    await waitForBooks(page);

    const links = balancesCard(page).locator('tbody').getByRole('link');
    await expect(links).toHaveCount(2);
    const shown = (await links.allTextContents()).map((name) => name.trim());
    expect(shown.sort()).toEqual([asset, liability].sort());
  } finally {
    await updateSingle(page, SETTINGS, { dashboard_accounts: [] });
  }

  await page.reload();
  await waitForBooks(page);
  await expect(balancesCard(page)).toHaveAttribute('data-state', /ready|empty/);
  await expect(
    balancesCard(page).getByRole('link', { name: liability, exact: true })
  ).toHaveCount(0);
});

// covers: AC-6
test('declining the reload keeps the card until the dashboard is opened again', async ({
  page,
}) => {
  test.slow();
  const [liability] = await getLeafAccounts(page, 'Liability');
  const picked = () =>
    balancesCard(page).getByRole('link', { name: liability, exact: true });
  await updateSingle(page, SETTINGS, { dashboard_accounts: [] });
  await page.goto('/books');
  await waitForBooks(page);
  await expect(balancesCard(page)).toHaveAttribute('data-state', /ready|empty/);
  await expect(picked()).toHaveCount(0);

  try {
    await balancesCard(page)
      .getByRole('link', { name: 'Choose accounts', exact: true })
      .click();
    await settings(page).getByText('Add row', { exact: true }).click();
    const account = settings(page)
      .getByRole('combobox', { name: 'Account', exact: true })
      .last();
    await account.click();
    await account.fill(liability);
    await page.getByRole('option', { name: liability, exact: true }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await page.getByRole('button', { name: 'No', exact: true }).click();
    await page.keyboard.press('Escape');

    await expect(settings(page)).toHaveCount(0);
    await expect(picked()).toHaveCount(0);

    await page.goto('/books');
    await waitForBooks(page);
    await expect(picked()).toBeVisible();
  } finally {
    await updateSingle(page, SETTINGS, { dashboard_accounts: [] });
  }
});

// covers: AC-1, AC-7
test('a Books User sees the dashboard accounts read only and no Choose accounts', async ({
  page,
  browser,
  baseURL,
}) => {
  const email = `books-user-dashboard-${Date.now()}@example.com`;
  const password = `Reader-${Date.now()}-Pass!`;
  await insertDocument(page, 'User', {
    email,
    first_name: 'Dashboard Reader',
    new_password: password,
    send_welcome_email: 0,
    roles: [{ role: 'Books User' }],
  });
  const [bank] = await getLeafAccounts(page, 'Asset');
  await updateSingle(page, SETTINGS, {
    dashboard_accounts: [{ account: bank }],
  });

  const context = await browser.newContext({ baseURL });
  try {
    const login = await context.request.post('/api/method/login', {
      form: { usr: email, pwd: password },
    });
    expect(login.ok()).toBe(true);
    const reader = await context.newPage();
    await reader.goto('/books/settings?tab=AccountingSettings');
    await waitForBooks(reader);

    const dialog = settings(reader);
    await expect(dialog.getByText('Dashboard Accounts')).toBeVisible();
    await expect(dialog.getByText('Add row', { exact: true })).toHaveCount(0);
    await expect(
      dialog.getByRole('combobox', {
        name: 'Account',
        exact: true,
        disabled: false,
      })
    ).toHaveCount(0);

    // A Books User reads neither the ledger nor the accounts, so the card is not shown.
    await reader.keyboard.press('Escape');
    await expect(balancesCard(reader)).toHaveCount(0);
  } finally {
    await context.close();
    await updateSingle(page, SETTINGS, { dashboard_accounts: [] });
  }
});
