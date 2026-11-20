import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getBooksMeta } from './helpers/doctypes.mjs';
import { stubFrappe } from './helpers/frappe.mjs';
import {
  AutoComplete,
  Color,
  frappeModels,
  fyo,
  loadFrappeDocTypes,
  newFrappeDoc,
  registerFrappeModels,
  Select,
} from './helpers/ui.mjs';

stubFrappe(({ body }) => ({ message: getBooksMeta(body.doctypes) }));
registerFrappeModels(frappeModels);
await loadFrappeDocTypes();

/** A control's script, without its template or its Base parent. */
function getControl(Component, values) {
  const control = { ...values };
  for (const [name, method] of Object.entries(Component.methods ?? {})) {
    control[name] = method.bind(control);
  }
  for (const [name, getter] of Object.entries(Component.computed ?? {})) {
    Object.defineProperty(control, name, { get: () => getter.call(control) });
  }
  return control;
}

test('a Select that may be left empty offers no value first, unless one is required', () => {
  const df = {
    fieldtype: 'Select',
    allowEmpty: true,
    options: [{ label: 'CGST', value: 'CGST' }],
  };

  const optional = getControl(Select, { df, isRequired: false });
  assert.deepEqual(
    optional.options.map(({ value }) => value),
    ['', 'CGST']
  );
  const required = getControl(Select, { df, isRequired: true });
  assert.deepEqual(
    required.options.map(({ value }) => value),
    ['CGST']
  );
});

test('an AutoComplete keeps only a listed value, as Frappe desk does, unless it takes its own', () => {
  const df = {
    fieldtype: 'AutoComplete',
    options: [
      { label: 'Maharashtra', value: 'Maharashtra' },
      { label: '23/03/2022', value: 'dd/MM/yyyy' },
    ],
  };
  const changes = [];
  const getChange = (value, field = df) => {
    const control = getControl(AutoComplete, {
      df: field,
      value,
      triggerChange: (change) => changes.push(change),
    });
    control.clearUnlistedValue();
    return changes.splice(0);
  };

  assert.deepEqual(getChange('Maharashta'), ['']);
  assert.deepEqual(getChange('23/03/2022'), ['dd/MM/yyyy']);
  assert.deepEqual(getChange('Maharashtra'), []);
  assert.deepEqual(getChange('Goa', { ...df, allowCustom: true }), []);
  assert.deepEqual(getChange('Goa', { ...df, options: [] }), []);
});

test('a Color takes a hex value, and an emptied one clears it, as Frappe desk does', () => {
  const changes = [];
  const color = getControl(Color, {
    triggerChange: (change) => changes.push(change),
  });

  color.setColorValue('ff0000');
  color.setColorValue('#12');
  color.setColorValue('');
  assert.deepEqual(changes, ['#ff0000', null]);
});

// covers: AC-17
test('expense account links open their entry only for a user who can read accounts', () => {
  const expense = newFrappeDoc('Expense', {
    paid_from: 'Cash',
    accounts: [{ account: 'Rent' }],
  });
  const [row] = expense.accounts;
  const openable = (canRead) => {
    fyo.store.permissions = {
      doctypes: { Account: 'Books Account', Expense: 'Books Expense' },
      user: { can_read: canRead },
    };
    return [
      [expense, 'paid_from'],
      [row, 'account'],
    ].map(([doc, fieldname]) => {
      const df = doc.schema.fields.find(
        (field) => field.fieldname === fieldname
      );
      return getControl(AutoComplete, { df, doc, value: doc[fieldname] })
        .canLink;
    });
  };

  const booksUser = openable(['Books Expense']);
  const booksManager = openable(['Books Expense', 'Books Account']);
  fyo.store.permissions = null;

  assert.deepEqual(booksUser, [false, false], 'a Books User sees plain names');
  assert.deepEqual(booksManager, [true, true]);
});
