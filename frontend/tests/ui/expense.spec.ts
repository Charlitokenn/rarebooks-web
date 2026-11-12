import { expect, test, type Browser, type Page } from '@playwright/test';
import { getLeafAccounts, insertDocument } from './helpers/records';
import { useBooksSession, waitForBooks } from './helpers/session';

// Frappe serves expenses; submitting one posts it to the ledger and the dashboard.
useBooksSession('/books/list/Expense');

const run = Date.now().toString(36);

test('Purchases lists Expenses, and a new expense takes its series and one row', async ({
  page,
}) => {
  await expect(
    page.getByRole('link', { name: 'Expenses', exact: true })
  ).toBeVisible();

  await page.getByRole('button', { name: 'New', exact: true }).click();
  await expect(page).toHaveURL(/\/books\/edit\/Expense\//);
  // The server's preview fills the default series once the form opens.
  await expect(
    page.getByRole('combobox', { name: 'Number Series (required)' })
  ).toHaveValue('EXP-');
  await expect(
    page.getByRole('combobox', { name: 'Paid From (required)' })
  ).toBeVisible();
  // The rows table starts with one empty row, after its header.
  await expect(page.getByRole('row')).toHaveCount(2);
});

// covers: AC-3, AC-6
test('an expense filled in the form saves, submits read only and cancels', async ({
  page,
}) => {
  const [rent] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await expect(page).toHaveURL(/\/books\/edit\/Expense\//);

  await pickLink(page, 'Paid From (required)', cash);
  // The first data row, after the header: Account, Description, Amount.
  const row = page.getByRole('row').nth(1);
  await pickLink(page, 'Account', rent, row);
  await row.getByRole('textbox').last().fill('42');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Total', { exact: true })).toHaveValue(/42\.00/);

  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(page).toHaveURL(/\/books\/edit\/Expense\/EXP-[^/]+$/);
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(page.getByText('Submitted', { exact: true })).toBeVisible();
  // A submitted expense is read only: no Save, and its fields take no edits.
  await expect(
    page.getByRole('button', { name: 'Save', exact: true })
  ).toHaveCount(0);
  // Read only fields show as disabled text, not as pickers.
  await expect(
    page.getByRole('textbox', { name: /^Paid From/ })
  ).toBeDisabled();

  await page.getByRole('button', { name: 'Actions', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Cancel', exact: true }).click();
  await page
    .getByRole('button', { name: 'Cancel Expense', exact: true })
    .click();
  await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();
});

// covers: AC-6, AC-14
test('a cancelled expense has no Amend, and Duplicate opens a draft with its rows', async ({
  page,
}) => {
  const expense = await submitExpense(page, `Cancelled Copy ${run}`);
  await cancelExpense(page, expense);
  await page.goto(`/books/edit/Expense/${expense}`);
  await waitForBooks(page);
  await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();

  // Like every other cancelled document, it offers no Amend, only Duplicate.
  await expect(page.getByRole('button', { name: /amend/i })).toHaveCount(0);
  await page.getByRole('button', { name: 'Actions', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: /amend/i })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Duplicate', exact: true }).click();

  await expect(page).not.toHaveURL(new RegExp(`/${expense}$`));
  await expect(
    page.getByRole('combobox', { name: 'Paid From (required)' })
  ).toBeEnabled();
  // The header row and the two copied rows.
  await expect(page.getByRole('row')).toHaveCount(3);
  await expect(page.getByLabel('Total', { exact: true })).toHaveValue(/35\.00/);
});

test('a submitted expense posts to the ledger and Top Expenses, and cancelling takes it out', async ({
  page,
}) => {
  const spentBefore = await getMonthSpending(page);
  const expense = await submitExpense(page, `EXP ${run}`);

  await page.goto(`/books/edit/Expense/${expense}`);
  await waitForBooks(page);
  await expect(page.getByText('Submitted', { exact: true })).toBeVisible();

  // Two expense rows on two accounts debit each, and the paid from account takes one credit.
  await page.goto('/books/list/AccountingLedgerEntry');
  await waitForBooks(page);
  await expect(page.getByText(expense, { exact: true })).toHaveCount(3);
  expect(await getMonthSpending(page)).toBeCloseTo(spentBefore + 35, 2);

  await cancelExpense(page, expense);
  expect(await getMonthSpending(page)).toBeCloseTo(spentBefore, 2);
  await page.goto('/books/list/Expense');
  await waitForBooks(page);
  await expect(
    page.getByRole('row').filter({ hasText: expense }).getByText('Cancelled')
  ).toBeVisible();
});

test('the general ledger offers Expenses as a Ref Type', async ({ page }) => {
  await page.goto('/books/report/GeneralLedger');
  await waitForBooks(page);
  await page.getByRole('combobox', { name: 'Ref Type' }).click();
  await expect(
    page.getByRole('option', { name: 'Expenses', exact: true })
  ).toBeVisible();
});

// covers: AC-8
test('a Books User records an expense but cannot delete it', async ({
  page,
  browser,
  baseURL,
}) => {
  const user = await signInAs(page, browser, baseURL, 'Books User');
  try {
    await user.page.goto('/books/list/Expense');
    await waitForBooks(user.page);
    await expect(
      user.page.getByRole('link', { name: 'Expenses', exact: true })
    ).toBeVisible();

    const draft = await insertDocument(user.page, 'Books Expense', {
      paid_from: await getCashAccount(user.page),
      accounts: [
        { account: (await getLeafAccounts(page, 'Expense'))[0], amount: 5 },
      ],
    });
    const response = await request(
      user.page,
      'DELETE',
      `/api/v2/document/Books Expense/${draft.name as string}`
    );
    expect(response.status).toBe(403);
  } finally {
    await user.close();
  }
});

// covers: AC-1, AC-8
test('a Books Cashier sees no Expenses and every expense call is refused', async ({
  page,
  browser,
  baseURL,
}) => {
  const cash = await getCashAccount(page);
  const cashier = await signInAs(page, browser, baseURL, 'Books Cashier');
  try {
    await cashier.page.goto('/books');
    await waitForBooks(cashier.page);
    await expect(
      cashier.page.getByRole('link', { name: 'Expenses', exact: true })
    ).toHaveCount(0);

    const list = await request(
      cashier.page,
      'GET',
      '/api/v2/document/Books Expense'
    );
    expect(list.status).toBe(403);
    const insert = await request(
      cashier.page,
      'POST',
      '/api/v2/document/Books Expense',
      { paid_from: cash, accounts: [] }
    );
    expect(insert.status).toBe(403);
    const search = await request(
      cashier.page,
      'POST',
      '/api/method/frappe.desk.search.search_widget',
      {
        doctype: 'Books Account',
        txt: '',
        query:
          'frappe_books.accounting.accounts.search_expense_payment_accounts',
      }
    );
    // Outside developer mode Frappe answers a refused query as a missing method.
    expect([403, 404]).toContain(search.status);
  } finally {
    await cashier.close();
  }
});

test.describe('on a phone', () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  // covers: AC-2, AC-15
  test('the list shows an expense on two lines without a sideways scroll', async ({
    page,
  }) => {
    const supplier = `Phone Expense Supplier ${run}`;
    await insertDocument(page, 'Books Party', {
      name: supplier,
      role: 'Supplier',
    });
    const expense = await submitExpense(page, `Phone EXP ${run}`, supplier);

    await page.goto('/books/list/Expense');
    await page.getByRole('searchbox', { name: 'Search' }).fill(expense);
    const row = page.getByRole('listitem').filter({ hasText: expense });
    await expect(row).toHaveCount(1);
    // Line 1 is the supplier and the total; line 2 the name, then the badge.
    await expect(row).toContainText(supplier);
    await expect(row).toContainText('35.00');
    await expect(row.getByText('Submitted', { exact: true })).toBeVisible();
    await expectNoSidewaysScroll(page);

    await row.tap();
    await expect(page).toHaveURL(/\/books\/edit\/Expense\//);
    await expectNoSidewaysScroll(page);
  });

  // covers: AC-3, AC-15
  test('a new expense edits its rows in a sheet', async ({ page }) => {
    await page.goto(`/books/edit/Expense/new-phone-${Date.now()}`);
    await waitForBooks(page);
    await expect(page.getByText('1 row', { exact: true })).toBeVisible();
    await expectNoSidewaysScroll(page);

    // The row the form starts with has no account yet, so it shows its number.
    await page.getByText('Row 1', { exact: true }).click();
    const sheet = page.getByRole('dialog', { name: 'Row 1' });
    for (const label of ['Account', 'Description', 'Amount']) {
      await expect(sheet.getByText(label, { exact: true })).toBeVisible();
    }
    await sheet.getByRole('button', { name: 'Done' }).click();
    await expect(sheet).toBeHidden();

    await page.getByRole('button', { name: 'Add row' }).click();
    await page
      .getByRole('dialog', { name: 'Row 2' })
      .getByRole('button', { name: 'Done' })
      .click();
    await expect(page.getByText('2 rows', { exact: true })).toBeVisible();
    await expectNoSidewaysScroll(page);
  });

  // covers: AC-6, AC-15
  test('a submitted expense cancels from the header menu', async ({ page }) => {
    const expense = await submitExpense(page, `Phone Cancel ${run}`);
    await page.goto(`/books/edit/Expense/${expense}`);
    await waitForBooks(page);
    await expect(page.getByText('Submitted', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'More actions' }).click();
    await page.getByRole('menuitem', { name: 'Cancel', exact: true }).click();
    await page
      .getByRole('button', { name: 'Cancel Expense', exact: true })
      .click();
    await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();
  });
  // covers: AC-6, AC-14, AC-15
  test('a cancelled expense has no Amend on a phone, and Duplicate opens a draft', async ({
    page,
  }) => {
    const expense = await submitExpense(page, `Phone Copy ${run}`);
    await cancelExpense(page, expense);
    await page.goto(`/books/edit/Expense/${expense}`);
    await waitForBooks(page);
    await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'More actions' }).click();
    await expect(page.getByRole('menuitem', { name: /amend/i })).toHaveCount(0);
    await page
      .getByRole('menuitem', { name: 'Duplicate', exact: true })
      .click();
    await expect(page).not.toHaveURL(new RegExp(`/${expense}$`));
    await expect(page.getByText('2 rows', { exact: true })).toBeVisible();
    await expectNoSidewaysScroll(page);
  });
});

/** Submits an expense today: 25 and 10 on two Expense accounts, paid from a Cash account. */
async function submitExpense(
  page: Page,
  reference: string,
  party?: string
): Promise<string> {
  const [rent, fuel] = await getLeafAccounts(page, 'Expense');
  const expense = await insertDocument(page, 'Books Expense', {
    paid_from: await getCashAccount(page),
    party,
    reference_number: reference,
    docstatus: 1,
    accounts: [
      { account: rent, amount: 25 },
      { account: fuel, amount: 10 },
    ],
  });
  return expense.name as string;
}

async function getCashAccount(page: Page): Promise<string> {
  return await page.evaluate(async () => {
    const filters = JSON.stringify([
      ['is_group', '=', 0],
      ['account_type', '=', 'Cash'],
    ]);
    const result = await fetch(
      `/api/v2/document/Books Account?filters=${encodeURIComponent(filters)}&limit=1`
    );
    const { data } = await result.json();
    return data[0].name as string;
  });
}

async function cancelExpense(page: Page, name: string) {
  const response = await page.evaluate(async (name) => {
    const result = await fetch('/api/method/frappe.client.cancel', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window as any).csrf_token,
      },
      body: JSON.stringify({ doctype: 'Books Expense', name }),
    });
    return { ok: result.ok, text: await result.text() };
  }, name);
  expect(response.ok, response.text).toBe(true);
}

/** What the dashboard's Top Expenses shows as spent this month, Others included. */
async function getMonthSpending(page: Page): Promise<number> {
  return await page.evaluate(async () => {
    const result = await fetch(
      '/api/method/frappe_books.reports.dashboard.get_top_expenses',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': (window as any).csrf_token,
        },
        body: JSON.stringify({ period: 'This Month' }),
      }
    );
    const { message } = await result.json();
    return (message as { total: number }[]).reduce(
      (sum, row) => sum + row.total,
      0
    );
  });
}

async function pickLink(
  page: Page,
  label: string,
  value: string,
  scope = page.locator('body')
) {
  const input = scope.getByRole('combobox', { name: label }).last();
  await input.click();
  await input.fill(value.slice(0, 6));
  await page.getByRole('option', { name: value }).first().click();
}

/** Makes a user with one role and signs them in on a page of their own. */
async function signInAs(
  page: Page,
  browser: Browser,
  baseURL: string | undefined,
  role: string
) {
  const stamp = `${run}-${Date.now()}`;
  const email = `expense-${role.replace(/\W/g, '').toLowerCase()}-${stamp}@example.com`;
  const password = `Expense-${stamp}-Pass!`;
  await insertDocument(page, 'User', {
    email,
    first_name: role,
    new_password: password,
    send_welcome_email: 0,
    roles: [{ role }],
  });

  const context = await browser.newContext({ baseURL });
  const login = await context.request.post('/api/method/login', {
    form: { usr: email, pwd: password },
  });
  expect(login.ok()).toBe(true);
  const userPage = await context.newPage();
  await userPage.goto('/books');
  await waitForBooks(userPage);
  return { page: userPage, close: () => context.close() };
}

/** Calls the server as the page's user and returns the status, so a refusal can be checked. */
async function request(
  page: Page,
  method: string,
  url: string,
  body?: Record<string, unknown>
): Promise<{ status: number; text: string }> {
  return await page.evaluate(
    async ({ method, url, body }) => {
      const result = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': (window as any).csrf_token,
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      return { status: result.status, text: await result.text() };
    },
    { method, url, body }
  );
}

async function expectNoSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(
    () =>
      document.scrollingElement!.scrollWidth -
      document.scrollingElement!.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(0);
}
