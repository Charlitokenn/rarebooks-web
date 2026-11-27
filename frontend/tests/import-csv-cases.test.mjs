import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { parseCSV } from './helpers/accounting.mjs';
import { loadFrappeModels } from './helpers/frappeModels.mjs';
import { frappeModels, fyo, Importer } from './helpers/frappe.mjs';

await loadFrappeModels(frappeModels);

// Grid text in, import CSV out, shared with the site's builder (spec 0025 AC-17).
const { cases } = JSON.parse(
  readFileSync(
    new URL('../../frappe_books/tests/import_csv_cases.json', import.meta.url),
    'utf8'
  )
);

/** The template field a case column key names: `fieldname`, or `<table>.<fieldname>`. */
function getFieldKey(importer, key) {
  const [first, second] = key.split('.');
  const field = [...importer.templateFieldsMap.values()].find((field) =>
    second
      ? field.parentSchemaChildField?.fieldname === first &&
        field.fieldname === second
      : !field.parentSchemaChildField && field.fieldname === first
  );
  assert.ok(field, `${importer.schemaName} has no column ${key}`);
  return field.fieldKey;
}

/** A case through the wizard's own load step and getImportFile, keeping only its own columns. */
function getWizardCsv(testCase) {
  const books = window.frappe.boot.books;
  books.number_format = testCase.number_format;
  try {
    const importer = new Importer(testCase.schema_name, fyo);
    importer.assignedTemplateFields = testCase.columns.map((key) =>
      getFieldKey(importer, key)
    );
    importer.valueMatrix = [];
    importer.assignValueMatrixFromParsed(testCase.rows);
    const matrix = parseCSV(importer.getImportFile().csv);
    const keep = testCase.csv[0].map((key) => matrix[0].indexOf(key));
    return matrix.map((row) => keep.map((index) => row[index] ?? ''));
  } finally {
    delete books.number_format;
  }
}

// covers: AC-17
for (const testCase of cases.filter(({ site_only }) => !site_only)) {
  test(`the wizard builds the golden CSV: ${testCase.name}`, () => {
    assert.deepEqual(getWizardCsv(testCase), testCase.csv);
  });
}

// covers: AC-17
test('a #.###,## user’s quantity of 1,5 is written as the importer reads it', () => {
  const [, row] = getWizardCsv({
    schema_name: 'Expense',
    number_format: '#.###,##',
    columns: ['name', 'accounts.amount'],
    rows: [['E1', '1.5']],
    csv: [['docstatus', 'accounts.amount']],
  });
  assert.deepEqual(row, ['0', '1,5']);
});
