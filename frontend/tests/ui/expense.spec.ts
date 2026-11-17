import {
  expect,
  test,
  type Browser,
  type BrowserContextOptions,
  type Locator,
  type Page,
} from '@playwright/test';
import { readFile } from 'node:fs/promises';
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
  // The rows table starts with one empty row; the header and Add row rows have no Delete row.
  await expect(dataRows(page)).toHaveCount(1);
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
  await page.keyboard.press('Escape');
  // On desktop, Duplicate sits in the Create menu with New entry.
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: /amend/i })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Duplicate', exact: true }).click();

  await expect(page).not.toHaveURL(new RegExp(`/${expense}$`));
  await expect(
    page.getByRole('combobox', { name: 'Paid From (required)' })
  ).toBeEnabled();
  // The two copied rows.
  await expect(dataRows(page)).toHaveCount(2);
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

// covers: AC-3, AC-8, AC-17
test('a Books User picks both accounts without account rights, submits, and cannot delete', async ({
  page,
  browser,
  baseURL,
}) => {
  // The Manager session reads the accounts; the Books User never does.
  const [rent] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  const user = await signInAs(page, browser, baseURL, 'Books User');
  try {
    const accounts = await request(
      user.page,
      'GET',
      '/api/v2/document/Books Account'
    );
    expect(accounts.status).toBe(403);

    await user.page.goto('/books/list/Expense');
    await waitForBooks(user.page);
    await expect(
      user.page.getByRole('link', { name: 'Expenses', exact: true })
    ).toBeVisible();
    await user.page.getByRole('button', { name: 'New', exact: true }).click();
    await expect(user.page).toHaveURL(/\/books\/edit\/Expense\//);

    await pickLink(user.page, 'Paid From (required)', cash);
    const row = user.page.getByRole('row').nth(1);
    await pickLink(user.page, 'Account', rent, row);
    await row.getByRole('textbox').last().fill('5');
    await user.page.keyboard.press('Tab');
    await expect(user.page.getByLabel('Total', { exact: true })).toHaveValue(
      /5\.00/
    );
    // Accounts show as plain names; the series the user may read still opens.
    const paidFrom = fieldBlock(
      user.page,
      user.page.getByRole('combobox', { name: 'Paid From (required)' }),
      'Paid From'
    );
    await expect(openButton(paidFrom)).toHaveCount(0);
    await expect(openButton(row)).toHaveCount(0);
    await expect(
      openButton(
        fieldBlock(
          user.page,
          user.page.getByRole('combobox', { name: 'Number Series (required)' }),
          'Number Series'
        )
      )
    ).toHaveCount(1);

    await user.page.getByRole('button', { name: 'Save', exact: true }).click();
    await user.page.getByRole('button', { name: 'Yes', exact: true }).click();
    await expect(user.page).toHaveURL(/\/books\/edit\/Expense\/EXP-[^/]+$/);
    await user.page
      .getByRole('button', { name: 'Submit', exact: true })
      .click();
    await user.page.getByRole('button', { name: 'Yes', exact: true }).click();
    await expect(
      user.page.getByText('Submitted', { exact: true })
    ).toBeVisible();
    const submittedPaidFrom = fieldBlock(
      user.page,
      user.page.getByRole('textbox', { name: /^Paid From/ }),
      'Paid From'
    );
    await expect(
      user.page.getByRole('textbox', { name: /^Paid From/ })
    ).toHaveValue(cash);
    await expect(openButton(submittedPaidFrom)).toHaveCount(0);
    await expect(openButton(user.page.getByRole('row').nth(1))).toHaveCount(0);
    await user.page
      .getByRole('button', { name: 'Actions', exact: true })
      .click();
    await expect(
      user.page.getByRole('menuitem', { name: 'Cancel', exact: true })
    ).toBeVisible();
    await user.page.keyboard.press('Escape');
    // "Accounting entries" sits in the View menu, which a Books User doesn't get.
    await expect(
      user.page.getByRole('button', { name: 'View', exact: true })
    ).toHaveCount(0);

    const draft = await insertDocument(user.page, 'Books Expense', {
      paid_from: cash,
      accounts: [{ account: rent, amount: 5 }],
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

// covers: AC-11
test("a supplier's Linked entries list the expense with its date and total", async ({
  page,
}) => {
  const supplier = `Linked Expense Supplier ${run}`;
  await insertDocument(page, 'Books Party', {
    name: supplier,
    role: 'Supplier',
  });
  const expense = await submitExpense(page, `Linked EXP ${run}`, supplier);

  await page.goto(`/books/edit/Party/${encodeURIComponent(supplier)}`);
  await waitForBooks(page);
  await page.getByRole('button', { name: 'Actions', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Linked entries' }).click();

  // submitExpense posts 25 and 10, so the entry shows a total of 35.
  const entry = page
    .getByRole('region', { name: 'Expense 1' })
    .getByRole('listitem')
    .filter({ hasText: expense });
  await expect(entry).toBeVisible();
  await expect(entry).toContainText(supplier);
  await expect(entry).toContainText(/35\.00/);
});

// covers: AC-7
test('a repeated supplier reference saves and warns until you close the warning', async ({
  page,
}) => {
  const supplier = `Duplicate Expense Supplier ${run}`;
  const reference = `DUP ${run}`;
  await insertDocument(page, 'Books Party', {
    name: supplier,
    role: 'Supplier',
  });
  const first = await submitExpense(page, reference, supplier);
  // A draft with the same supplier and reference, saved again from the form.
  const [rent] = await getLeafAccounts(page, 'Expense');
  const second = await insertDocument(page, 'Books Expense', {
    paid_from: await getCashAccount(page),
    party: supplier,
    reference_number: reference,
    accounts: [{ account: rent, amount: 5 }],
  });
  await page.goto(`/books/edit/Expense/${second.name}`);
  await waitForBooks(page);

  await page.getByRole('textbox', { name: 'Remark' }).fill('Second copy');
  // The remark commits when it loses focus, which makes the form unsaved.
  await page.keyboard.press('Tab');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();

  // The save goes through, and the server's warning shows beside it.
  const saved = page.getByText(`${second.name} saved`);
  await expect(saved).toBeVisible();
  const warning = page.locator('[data-sonner-toast]').filter({
    hasText: `${first} already has reference ${reference} for ${supplier}.`,
  });
  await expect(warning).toBeVisible();
  // The saved toast fades after a few seconds; the warning stays until closed.
  await expect(saved).toBeHidden({ timeout: 10_000 });
  await expect(warning).toBeVisible();
  await warning.getByRole('button', { name: 'Close toast' }).click();
  await expect(warning).toBeHidden();
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
    for (const query of [
      'frappe_books.accounting.accounts.search_expense_payment_accounts',
      'frappe_books.accounting.accounts.search_expense_accounts',
    ]) {
      const search = await request(
        cashier.page,
        'POST',
        '/api/method/frappe.desk.search.search_widget',
        { doctype: 'Books Account', txt: '', query }
      );
      // Outside developer mode Frappe answers a refused query as a missing method.
      expect([403, 404], query).toContain(search.status);
    }
  } finally {
    await cashier.close();
  }
});

// covers: AC-8
test('a Books Cashier is refused the expense preview', async ({
  page,
  browser,
  baseURL,
}) => {
  const [rent] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  const cashier = await signInAs(page, browser, baseURL, 'Books Cashier');
  try {
    const preview = await request(
      cashier.page,
      'POST',
      '/api/v2/method/run_doc_method',
      {
        method: 'preview',
        document: {
          doctype: 'Books Expense',
          paid_from: cash,
          accounts: [{ account: rent, amount: 1 }],
        },
      }
    );
    expect(preview.status).toBe(403);
  } finally {
    await cashier.close();
  }
});

// covers: AC-1
test('Purchases places Expenses after Purchase Payments and before Suppliers', async ({
  page,
}) => {
  const links = (await page.getByRole('link').allInnerTexts()).map((text) =>
    text.trim()
  );
  const at = (name: string) => links.indexOf(name);

  expect(at('Purchase Payments')).toBeGreaterThan(-1);
  expect(at('Expenses')).toBe(at('Purchase Payments') + 1);
  expect(at('Suppliers')).toBe(at('Expenses') + 1);
});

// covers: AC-2
test('the list filters by Submitted and by Cancelled, newest date first', async ({
  page,
}) => {
  const draft = await insertExpense(page, { date: '2026-01-04' });
  const submitted = await submitExpense(page, `Filter Submitted ${run}`);
  const cancelled = await submitExpense(page, `Filter Cancelled ${run}`);
  await cancelExpense(page, cancelled);
  await page.goto('/books/list/Expense');
  await waitForBooks(page);

  const header = await page.getByRole('columnheader').allInnerTexts();
  expect(header.map((text) => text.trim()).filter(Boolean)).toEqual([
    '#',
    'Expense No',
    'Status',
    'Date',
    'Supplier',
    'Paid From',
    'Total',
  ]);
  const dates = (await listRows(page)).map(getDateKey);
  expect(dates).toEqual([...dates].sort().reverse());

  for (const [status, shown, hidden] of [
    ['Submitted', submitted, cancelled],
    ['Cancelled', cancelled, submitted],
  ] as const) {
    await filterByStatus(page, status);
    const rows = await listRows(page);
    expect(rows.join('\n')).toContain(shown);
    expect(rows.join('\n')).not.toContain(hidden);
    expect(rows.join('\n')).not.toContain(draft);
    for (const row of rows) {
      expect(row).toContain(status);
    }
  }
});

// covers: AC-3
test('the Supplier picker offers only suppliers, and Create makes a supplier', async ({
  page,
}) => {
  const supplier = `Picker Supplier ${run}`;
  const both = `Picker Both ${run}`;
  const customer = `Picker Customer ${run}`;
  for (const [name, role] of [
    [supplier, 'Supplier'],
    [both, 'Both'],
    [customer, 'Customer'],
  ]) {
    await insertDocument(page, 'Books Party', { name, role });
  }
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await expect(page).toHaveURL(/\/books\/edit\/Expense\//);

  const party = page.getByRole('combobox', { name: 'Supplier' });
  await party.click();
  await party.fill(`Picker `);
  await expect(page.getByRole('option', { name: supplier })).toBeVisible();
  await expect(page.getByRole('option', { name: both })).toBeVisible();
  await expect(page.getByRole('option', { name: customer })).toHaveCount(0);

  await page
    .getByRole('option', { name: /^Create/ })
    .first()
    .click();
  await expect(
    page.getByRole('combobox', { name: 'Role', exact: true })
  ).toHaveText('Supplier');
});

// covers: AC-3, AC-8, AC-17
test('a Books User picks only what the save accepts, and gets no Paid From filter', async ({
  page,
  browser,
  baseURL,
}) => {
  const accounts = await getAccounts(page);
  const paidFromOk = accounts
    .filter(
      (account) =>
        !account.is_group &&
        (['Cash', 'Bank'].includes(account.account_type ?? '') ||
          (account.root_type === 'Liability' && !account.account_type))
    )
    .map((account) => account.name);
  const rowOk = accounts
    .filter((account) => !account.is_group && account.root_type === 'Expense')
    .map((account) => account.name);
  const user = await signInAs(page, browser, baseURL, 'Books User');
  try {
    await user.page.goto('/books/list/Expense');
    await waitForBooks(user.page);
    await user.page.getByRole('button', { name: 'New', exact: true }).click();

    await user.page
      .getByRole('combobox', { name: 'Paid From (required)' })
      .click();
    const paidFrom = await getOptions(user.page);
    expect(paidFrom.length).toBeGreaterThan(0);
    expect(paidFrom.filter((name) => !paidFromOk.includes(name))).toEqual([]);
    await user.page.keyboard.press('Escape');

    const account = user.page
      .getByRole('row')
      .nth(1)
      .getByRole('combobox', { name: 'Account' })
      .last();
    await account.click();
    const rows = await getOptions(user.page);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.filter((name) => !rowOk.includes(name))).toEqual([]);
    // Typing narrows the list.
    await account.fill(rows[0].slice(0, 6));
    await expect(
      user.page.getByRole('option', { name: rows[0], exact: true })
    ).toBeVisible();
    await user.page.keyboard.press('Escape');

    await user.page.goto('/books/list/Expense');
    await waitForBooks(user.page);
    expect(await getFilterFields(user.page)).not.toContain('Paid From');
  } finally {
    await user.close();
  }
});

// covers: AC-17
test('a Books User opens a submitted expense without reading Books Account', async ({
  page,
  browser,
  baseURL,
}) => {
  const [rent] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  const expense = await submitExpense(page, `No Account Read ${run}`);
  const user = await signInAs(page, browser, baseURL, 'Books User');
  try {
    const accountReads: string[] = [];
    user.page.on('request', (sent) => {
      // The form's field definitions name Books Account; only record reads.
      if (sent.url().includes('get_books_meta')) return;
      const url = decodeURIComponent(sent.url());
      const body = sent.postData() ?? '';
      if (
        /Books Account([/?"]|$)/.test(url) ||
        body.includes('"Books Account"')
      ) {
        accountReads.push(url);
      }
    });
    await user.page.goto(`/books/edit/Expense/${expense}`);
    await waitForBooks(user.page);

    await expect(
      user.page.getByRole('textbox', { name: /^Paid From/ })
    ).toHaveValue(cash);
    await expect(
      user.page.getByRole('row').nth(1).getByRole('textbox').first()
    ).toHaveValue(rent);
    expect(accountReads).toEqual([]);
  } finally {
    await user.close();
  }
});

// covers: AC-17
test('a Books Manager gets open buttons, Accounting entries and a Paid From filter', async ({
  page,
}) => {
  expect(await getFilterFields(page)).toContain('Paid From');
  const expense = await submitExpense(page, `Manager View ${run}`);
  await page.goto(`/books/edit/Expense/${expense}`);
  await waitForBooks(page);

  const paidFrom = fieldBlock(
    page,
    page.getByRole('textbox', { name: /^Paid From/ }),
    'Paid From'
  );
  await expect(openButton(paidFrom)).toHaveCount(1);
  await page.getByRole('button', { name: 'View', exact: true }).click();
  await expect(
    page.getByRole('menuitem', { name: 'Accounting entries' })
  ).toBeVisible();
});

// covers: AC-5
test('Accounting entries opens the General Ledger on the expense', async ({
  page,
}) => {
  const expense = await submitExpense(page, `Ledger Link ${run}`);
  await page.goto(`/books/edit/Expense/${expense}`);
  await waitForBooks(page);

  await page.getByRole('button', { name: 'View', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Accounting entries' }).click();

  await expect(page).toHaveURL(/\/books\/report\/GeneralLedger/);
  expect(decodeURIComponent(page.url())).toContain(
    `"referenceName":"${expense}"`
  );
  // submitExpense posts 25 and 10, credited as 35.
  for (const amount of ['25.00', '10.00', '35.00']) {
    await expect(page.getByText(amount).first()).toBeVisible();
  }
  await page.getByRole('combobox', { name: 'Ref Type' }).click();
  const types = await getOptions(page);
  expect(types.indexOf('Expenses')).toBe(types.indexOf('Journal Entries') + 1);
});

// covers: AC-7 (spec 0006: the preview stays quiet, a refusal keeps its own error)
test('typing shows no server message, and a refused save shows only its error', async ({
  page,
}) => {
  const [rent] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  const previews: string[] = [];
  page.on('request', (sent) => {
    if ((sent.postData() ?? '').includes('"method":"preview"')) {
      previews.push(sent.url());
    }
  });
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await pickLink(page, 'Paid From (required)', cash);
  const row = page.getByRole('row').nth(1);
  await pickLink(page, 'Account', rent, row);
  await row.getByRole('textbox').last().fill('9');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Total', { exact: true })).toHaveValue(/9\.00/);

  expect(previews.length).toBeGreaterThan(0);
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);

  await row.getByRole('textbox').last().fill('0');
  await page.keyboard.press('Tab');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(
    page.getByText('Row 1: amount must be greater than zero.').first()
  ).toBeVisible();
  await expect(
    page
      .locator('[data-sonner-toast]')
      .filter({ hasNotText: 'Row 1: amount must be greater than zero.' })
  ).toHaveCount(0);
});

// covers: AC-13
test('Print uses Business - Expense with the header, rows and remark', async ({
  page,
}) => {
  const [rent] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  const supplier = `Print Supplier ${run}`;
  await insertDocument(page, 'Books Party', {
    name: supplier,
    role: 'Supplier',
  });
  const expense = await insertExpense(page, {
    party: supplier,
    reference_number: `PRINT-${run}`,
    user_remark: `Print remark ${run}`,
    docstatus: 1,
    accounts: [{ account: rent, amount: 8, description: `Print row ${run}` }],
  });

  await page.goto(`/books/print/Expense/${expense}`);
  await waitForBooks(page);

  await expect(
    page.getByRole('combobox', { name: 'Template Name' })
  ).toContainText('Business - Expense');
  const print = page.frameLocator('iframe[title="Print preview"]');
  for (const text of [
    expense,
    cash,
    supplier,
    `PRINT-${run}`,
    rent,
    `Print row ${run}`,
    `Print remark ${run}`,
  ]) {
    await expect(print.getByText(text).first()).toBeVisible();
  }
});

// covers: AC-14
test('Duplicate of a submitted expense with a receipt copies everything but the receipt', async ({
  page,
}) => {
  const supplier = `Duplicate Copy Supplier ${run}`;
  await insertDocument(page, 'Books Party', {
    name: supplier,
    role: 'Supplier',
  });
  const expense = await insertExpense(page, {
    party: supplier,
    reference_number: `COPY-${run}`,
    user_remark: 'Copy me',
    date: '2026-10-02',
    docstatus: 1,
    attachment: '/files/receipt.png',
  });
  await page.goto(`/books/edit/Expense/${expense}`);
  await waitForBooks(page);

  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Duplicate', exact: true }).click();
  await expect(page).not.toHaveURL(new RegExp(`/${expense}$`));
  await expect(
    page.getByRole('textbox', { name: 'Reference Number' })
  ).toHaveValue(`COPY-${run}`);
  await expect(page.getByRole('combobox', { name: 'Supplier' })).toHaveValue(
    supplier
  );
  await expect(page.getByRole('textbox', { name: 'Remark' })).toHaveValue(
    'Copy me'
  );
  await expect(
    page.getByRole('combobox', { name: 'Date (required)' })
  ).toHaveValue('02-10-2026');
  await expect(page.getByText('receipt.png')).toHaveCount(0);

  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(page).toHaveURL(/\/books\/edit\/Expense\/EXP-[^/]+$/);
  const copy = await getExpense(page, page.url().split('/').pop()!);
  expect(copy).toMatchObject({ status: 'Saved', docstatus: 0 });
  expect(copy.attachment ?? null).toBeNull();
  expect(copy.amended_from ?? null).toBeNull();
});

// covers: AC-8, AC-12
test('the Import Wizard imports a draft expense, refuses a zero row, and is a Manager tool', async ({
  page,
  browser,
  baseURL,
}) => {
  const [rent, fuel] = await getLeafAccounts(page, 'Expense');
  const cash = await getCashAccount(page);
  await page.goto('/books/import-wizard');
  await waitForBooks(page);
  await page.getByRole('combobox').first().click();
  await page.getByRole('option', { name: 'Expense', exact: true }).click();

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Save template' }).click();
  const template = await readFile((await (await download).path())!, 'utf8');
  const columns = template
    .split(/\r?\n/)[0]
    .split(',')
    .map((column) => column.replace(/"/g, ''));
  expect(columns).toEqual([
    'Expense No',
    'Number Series',
    'Date',
    'Paid From',
    'Supplier',
    'Reference Number',
    'Remark',
    'ID (Expenses)',
    'Account (Expenses)',
    'Description (Expenses)',
    'Amount (Expenses)',
  ]);

  // Rows that share an Expense No become one expense; the server fills the empty Number Series.
  const kept = `IMP-${run}`;
  const refused = `IMPZ-${run}`;
  const csv = [
    'Expense No,Number Series,Date,Paid From,Reference Number,Account (Expenses),Amount (Expenses)',
    `A,,2026-11-02,${cash},${kept},${rent},100`,
    `A,,,,,${fuel},20`,
    `B,,2026-11-03,${cash},${refused},${rent},0`,
  ].join('\n');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Select file', exact: true }).click();
  await (
    await chooser
  ).setFiles({
    name: 'import.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv),
  });
  await page.getByRole('button', { name: 'Import data', exact: true }).click();

  // Keep them as drafts.
  await page
    .getByRole('dialog', { name: 'Submit entries?' })
    .getByRole('button', { name: 'No', exact: true })
    .click();

  const results = page.getByRole('dialog', { name: 'Import complete' });
  await expect(results).toContainText('1 entry imported');
  await expect(results).toContainText('1 entry failed');
  await expect(results).toContainText(
    'Row 1: amount must be greater than zero.'
  );
  const imported = await getExpenses(page, [kept, refused]);
  expect(imported).toHaveLength(1);
  expect(imported[0]).toMatchObject({
    reference_number: kept,
    docstatus: 0,
    status: 'Saved',
    total: 120,
  });

  const user = await signInAs(page, browser, baseURL, 'Books User');
  try {
    await user.page.goto('/books/import-wizard');
    await waitForBooks(user.page);
    await user.page.getByRole('combobox').first().click();
    await expect(
      user.page.getByRole('option', { name: 'Expense', exact: true })
    ).toHaveCount(0);
  } finally {
    await user.close();
  }
});

test.describe('on a phone', () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  // covers: AC-8, AC-9
  test("a Books Cashier's create menu offers no Expense", async ({
    page,
    browser,
    baseURL,
  }) => {
    const cashier = await signInAs(page, browser, baseURL, 'Books Cashier', {
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    try {
      const create = cashier.page.getByRole('button', {
        name: 'Create',
        exact: true,
      });
      if (await create.count()) {
        await create.click();
      }
      await expect(
        cashier.page.getByRole('menuitem', { name: 'Expense', exact: true })
      ).toHaveCount(0);
      await expect(
        cashier.page.getByRole('button', { name: 'Expense', exact: true })
      ).toHaveCount(0);
    } finally {
      await cashier.close();
    }
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
      // A required field's label reads "Amount (required)", so match the label as a part.
      await expect(sheet.getByText(label).first()).toBeVisible();
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
  role: string,
  options: BrowserContextOptions = {}
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

  const context = await browser.newContext({ ...options, baseURL });
  const login = await context.request.post('/api/method/login', {
    form: { usr: email, pwd: password },
  });
  expect(login.ok()).toBe(true);
  const userPage = await context.newPage();
  await userPage.goto('/books');
  await waitForBooks(userPage);
  return { page: userPage, close: () => context.close() };
}

/** Inserts an expense paid from a Cash account with one 25 row, overriding any value given. */
async function insertExpense(
  page: Page,
  values: Record<string, unknown> = {}
): Promise<string> {
  const [rent] = await getLeafAccounts(page, 'Expense');
  const expense = await insertDocument(page, 'Books Expense', {
    paid_from: await getCashAccount(page),
    accounts: [{ account: rent, amount: 25 }],
    ...values,
  });
  return expense.name as string;
}

async function getExpense(
  page: Page,
  name: string
): Promise<Record<string, any>> {
  const { text } = await request(
    page,
    'GET',
    `/api/v2/document/Books Expense/${name}`
  );
  return JSON.parse(text).data;
}

/** The expenses with these reference numbers. */
async function getExpenses(
  page: Page,
  references: string[]
): Promise<Record<string, any>[]> {
  const filters = JSON.stringify([['reference_number', 'in', references]]);
  const fields = JSON.stringify([
    'name',
    'reference_number',
    'docstatus',
    'status',
    'total',
  ]);
  const { text } = await request(
    page,
    'GET',
    `/api/v2/document/Books Expense?filters=${encodeURIComponent(filters)}&fields=${encodeURIComponent(fields)}`
  );
  return JSON.parse(text).data;
}

/** Every Books Account, read as the page's user (a Manager). */
async function getAccounts(page: Page): Promise<
  {
    name: string;
    is_group: number;
    root_type: string;
    account_type: string | null;
  }[]
> {
  const fields = JSON.stringify([
    'name',
    'is_group',
    'root_type',
    'account_type',
  ]);
  const { text } = await request(
    page,
    'GET',
    `/api/v2/document/Books Account?fields=${encodeURIComponent(fields)}&limit=1000`
  );
  return JSON.parse(text).data;
}

/** The options an open picker shows, once it has some. */
async function getOptions(page: Page): Promise<string[]> {
  await expect(page.getByRole('option').first()).toBeVisible();
  const options = await page.getByRole('option').allInnerTexts();
  return options.map((text) => text.trim()).filter(Boolean);
}

/** The fields the list's Filter panel offers. */
async function getFilterFields(page: Page): Promise<string[]> {
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await page.getByRole('button', { name: 'Add a filter', exact: true }).click();
  await page.getByRole('combobox', { name: 'Field', exact: true }).click();
  const fields = await getOptions(page);
  await page.keyboard.press('Escape');
  return fields;
}

async function filterByStatus(page: Page, status: string) {
  await page.goto('/books/list/Expense');
  await waitForBooks(page);
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await page.getByRole('button', { name: 'Add a filter', exact: true }).click();
  await page.getByRole('combobox', { name: 'Field', exact: true }).click();
  await page.getByRole('option', { name: 'Status', exact: true }).click();
  await page.getByRole('combobox', { name: 'Value', exact: true }).click();
  await page.getByRole('option', { name: status, exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('button', { name: /1 filter applied/ })
  ).toBeVisible();
}

/** The text of each list row that shows an expense. */
async function listRows(page: Page): Promise<string[]> {
  await expect(
    page.getByRole('row').filter({ hasText: /EXP-/ }).first()
  ).toBeVisible();
  const rows = await page.getByRole('row').allInnerTexts();
  return rows.filter((text) => /EXP-\d+/.test(text));
}

/** A list row's date as YYYYMMDD, so rows sort by it. */
function getDateKey(row: string): string {
  const [, day, month, year] = row.match(/(\d\d)-(\d\d)-(\d{4})/) ?? [];
  return `${year}${month}${day}`;
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

/** A form field's block: the innermost element holding its label and its control. */
function fieldBlock(page: Page, control: Locator, label: string) {
  return page.locator('div').filter({ has: control, hasText: label }).last();
}

/** The button that opens the linked entry of a link value, within `scope`. */
function openButton(scope: Locator) {
  return scope.getByRole('button', { name: 'Open linked entry' });
}

/** The rows of the Expenses table, without its header and its Add row row. */
function dataRows(page: Page) {
  return page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: 'Delete row' }) });
}

async function expectNoSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(
    () =>
      document.scrollingElement!.scrollWidth -
      document.scrollingElement!.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(0);
}
