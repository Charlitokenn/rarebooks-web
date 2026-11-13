import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getBooksMeta } from './helpers/doctypes.mjs';
import { stubFrappe } from './helpers/frappe.mjs';
import {
  frappeModels,
  getActionsForDoc,
  loadFrappeDocTypes,
  newFrappeDoc,
  registerFrappeModels,
} from './helpers/ui.mjs';

stubFrappe(({ body }) => ({ message: getBooksMeta(body.doctypes) }));
registerFrappeModels(frappeModels);
await loadFrappeDocTypes();

test('a party links to its General Ledger only once saved', async () => {
  const party = newFrappeDoc('Party', { name: 'Acme', role: 'Customer' });
  const ledger = () =>
    getActionsForDoc(party).find(({ label }) => label === 'General Ledger');

  assert.equal(ledger(), undefined);
  party._notInserted = false;
  const routes = [];
  await ledger().action(party, { push: (route) => routes.push(route) });
  assert.deepEqual(routes, [
    {
      path: '/report/GeneralLedger',
      query: { defaultFilters: '{"party":"Acme"}' },
    },
  ]);
});

// covers: AC-6, AC-14
test('a cancelled expense offers the same actions as a cancelled journal entry, with Duplicate and no Amend', () => {
  const labelsFor = (schemaName, name) => {
    const doc = newFrappeDoc(schemaName, { name, docstatus: 2 });
    doc._notInserted = false;
    return getActionsForDoc(doc).map(({ label }) => label);
  };

  const expense = labelsFor('Expense', 'EXP-0001');
  const journal = labelsFor('JournalEntry', 'JV-0001');
  assert.ok(expense.includes('Duplicate'));
  assert.ok(!expense.some((label) => /amend/i.test(label)));
  assert.ok(!expense.includes('Cancel'));
  // Expenses mirror the other documents: no lifecycle action of their own.
  const lifecycle = ['Duplicate', 'New entry', 'Delete', 'Cancel'];
  assert.deepEqual(
    expense.filter((label) => lifecycle.includes(label)),
    journal.filter((label) => lifecycle.includes(label))
  );
});
