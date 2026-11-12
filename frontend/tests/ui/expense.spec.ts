import { expect, test, type Page } from '@playwright/test';
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

/** Submits an expense today: 25 and 10 on two Expense accounts, paid from a Cash account. */
async function submitExpense(page: Page, reference: string): Promise<string> {
  const [rent, fuel] = await getLeafAccounts(page, 'Expense');
  const expense = await insertDocument(page, 'Books Expense', {
    paid_from: await getCashAccount(page),
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
