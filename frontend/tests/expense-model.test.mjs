import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getFilterFields } from './helpers/accounting.mjs';
import {
  frappeModels,
  fyo,
  getLedgerLink,
  getModel,
  getSchema,
  newFrappeDoc,
  stubFrappe,
} from './helpers/frappe.mjs';
import { getLayout, loadFrappeModels } from './helpers/models.mjs';

await loadFrappeModels();
const { Expense } = frappeModels;

test('the expense form shows its fields in the sections of the DocType', () => {
  const schema = getSchema('Expense');
  assert.equal(schema.label, 'Expense');
  assert.equal(schema.isSubmittable, true);
  assert.deepEqual(getLayout(schema), [
    'name | Expense No |  | Default',
    'number_series | Number Series |  | Default',
    'date | Date |  | Default',
    'paid_from | Paid From | Paid From | Default',
    'party | Supplier | Supplier | Default',
    'reference_number | Reference Number | Receipt, cheque or transfer number | Default',
    'accounts | Expenses |  | Expenses',
    'total | Total |  | Expenses',
    'user_remark | Remark | Add a remark | References',
    'attachment | Attachment | Add the receipt | References',
  ]);
  const total = schema.fields.find(({ fieldname }) => fieldname === 'total');
  assert.equal(total.readOnly, true);
});

test('expense rows show the account, description and amount', () => {
  const schema = getSchema('ExpenseAccount');
  assert.equal(schema.label, 'Expense Account');
  assert.deepEqual(schema.tableFields, ['account', 'description', 'amount']);
  assert.deepEqual(getLayout(schema), [
    'account | Account | Account | Default',
    'description | Description | Description | Default',
    'amount | Amount |  | Default',
  ]);
});

test('a new expense gets a temporary name, today and one empty row', () => {
  const expense = newFrappeDoc('Expense');
  assert.match(expense.name, /^New Expense \d{2}$/);
  assert.equal(expense.isTransactional, true);
  assert.equal(
    expense.date.toDateString(),
    new Date().toDateString(),
    'the DocType default Today'
  );
  assert.equal(expense.accounts.length, 1);
  assert.equal(expense.accounts[0].schemaName, 'ExpenseAccount');
  assert.equal(expense.accounts[0].account ?? null, null);
});

test('an expense made with rows, or duplicated, keeps only its own rows', async () => {
  const expense = newFrappeDoc('Expense', {
    accounts: [
      { account: 'Rent', amount: fyo.pesa(100) },
      { account: 'Fuel', amount: fyo.pesa(20) },
    ],
  });
  assert.equal(expense.accounts.length, 2);

  const copy = await expense.duplicate();
  assert.deepEqual(
    copy.accounts.map((row) => row.account),
    ['Rent', 'Fuel']
  );
});

test('expense links filter series and row accounts, and rows offer no Create', async () => {
  assert.deepEqual(await Expense.filters.number_series(), [
    ['reference_type', '=', 'Expense'],
  ]);
  const ExpenseAccount = getModel('ExpenseAccount');
  assert.deepEqual(await ExpenseAccount.filters.account(), [
    ['is_group', '=', 0],
    ['root_type', '=', 'Expense'],
  ]);
  const [account] = getSchema('ExpenseAccount').fields;
  assert.equal(account.create, false);
});

// covers: AC-3
test('an expense picks a supplier, makes a supplier, and pays from the server rule', async () => {
  assert.deepEqual(await Expense.filters.party(), [
    ['role', 'in', ['Supplier', 'Both']],
  ]);
  assert.deepEqual(await Expense.createFilters.party(), [
    ['role', '=', 'Supplier'],
  ]);
  assert.equal(
    Expense.linkQueries.paid_from,
    'frappe_books.accounting.accounts.search_expense_payment_accounts'
  );
  assert.equal(
    Expense.filters.paid_from,
    undefined,
    'the search ignores client filters, so the model sends none'
  );
  const fields = getSchema('Expense').fields;
  const paidFrom = fields.find(({ fieldname }) => fieldname === 'paid_from');
  const party = fields.find(({ fieldname }) => fieldname === 'party');
  assert.equal(paidFrom.create, false);
  assert.notEqual(party.create, false);
});

test('a new expense is saved without its temporary name, which the server replaces', async () => {
  const requests = stubFrappe(({ path, body }) =>
    path.endsWith('run_doc_method')
      ? { docs: [body.document] }
      : { data: { ...body, name: 'EXP-0001', modified: '2026-11-12 10:00:00' } }
  );
  const expense = newFrappeDoc('Expense', {
    number_series: 'EXP-',
    paid_from: 'Cash',
    accounts: [{ account: 'Rent', amount: fyo.pesa(100) }],
  });
  await expense.sync();

  const insert = requests.find(
    ({ method, path }) => method === 'POST' && path.endsWith('Expense')
  );
  assert.equal(insert.path, '/api/v2/document/Books Expense');
  assert.equal('name' in insert.body, false);
  assert.equal(insert.body.accounts.length, 1);
  assert.equal(expense.name, 'EXP-0001');
});

test('the expense list shows its columns and filters by status', () => {
  const { columns } = Expense.getListViewSettings(fyo);
  assert.deepEqual(
    columns.map((column) =>
      typeof column === 'string' ? column : column.fieldname
    ),
    ['name', 'status', 'date', 'party', 'paid_from', 'total']
  );

  const filters = getFilterFields(getSchema('Expense').fields, columns);
  const status = filters.find(({ fieldname }) => fieldname === 'status');
  assert.deepEqual(
    status.options.map(({ value }) => value),
    ['Saved', 'Submitted', 'Cancelled']
  );
});

test("a submitted expense's accounting entries open on its date", () => {
  const expense = newFrappeDoc('Expense', {
    name: 'EXP-0001',
    date: new Date(2026, 10, 3),
  });
  const { referenceType, referenceName, fromDate, toDate } = JSON.parse(
    getLedgerLink(expense, 'GeneralLedger').query.defaultFilters
  );
  assert.deepEqual(
    [referenceType, referenceName],
    ['Books Expense', 'EXP-0001']
  );
  assert.equal(fromDate, toDate);
  assert.equal(new Date(fromDate).getDate(), 3);

  const [ledger] = Expense.getActions(fyo);
  assert.equal(ledger.label, 'Accounting entries');
  assert.equal(ledger.condition(expense), false, 'not before it is submitted');
});
