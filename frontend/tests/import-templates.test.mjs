import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { test } from 'node:test';
import { loadFrappeModels } from './helpers/frappeModels.mjs';
import {
  frappeModels,
  fyo,
  getDocType,
  getImportableSchemaNames,
  getSchema,
  Importer,
} from './helpers/frappe.mjs';

await loadFrappeModels(frappeModels);

// The site's bulk import reads the wizard's template columns from this file (spec 0025 AC-3, AC-15).
const TEMPLATES = new URL(
  '../../frappe_books/subscription/import_templates.json',
  import.meta.url
);

/** What the Import Wizard offers a user who may import everything, inventory on. */
function getAllImportableSchemaNames() {
  const everything = {
    singles: { AccountingSettings: { enable_inventory: true } },
    can: () => true,
  };
  return getImportableSchemaNames(everything);
}

/** The column Frappe's Data Import reads a template field from, or null when it is not sent. */
function getCsvKey(field, schema) {
  const table = field.parentSchemaChildField;
  if (table) {
    return field.fieldname === 'name'
      ? null
      : `${table.fieldname}.${field.fieldname}`;
  }

  if (field.fieldname !== 'name') {
    return field.fieldname;
  }

  return schema.naming === 'manual' ? 'name' : null;
}

/** One type's template as the wizard's Save template makes it, in the wizard's order. */
function getTemplate(schemaName) {
  const importer = new Importer(schemaName, fyo);
  const schema = getSchema(schemaName);
  const { doctype, meta } = getDocType(schemaName);
  const [rule, namingField] = (meta.autoname ?? '').split(':');
  const columns = [...importer.templateFieldsMap.values()].map((field) => {
    const table = field.parentSchemaChildField;
    return {
      key: table ? `${table.fieldname}.${field.fieldname}` : field.fieldname,
      label: importer.templateHeadersByFieldKey.get(field.fieldKey),
      required: !!field.required,
      table: table?.fieldname ?? null,
      table_label: table?.label ?? null,
      csv_key: getCsvKey(field, schema),
    };
  });

  return {
    schema_name: schemaName,
    doctype,
    label: schema.label,
    naming: schema.naming,
    name_key: rule.toLowerCase() === 'field' ? namingField : 'name',
    submittable: !!schema.isSubmittable,
    columns,
  };
}

function getTemplates() {
  return getAllImportableSchemaNames().map(getTemplate);
}

// covers: AC-3, AC-15
test('the site’s import templates are the wizard’s Save template columns', () => {
  const templates = getTemplates();
  if (process.env.UPDATE_IMPORT_TEMPLATES) {
    writeFileSync(TEMPLATES, `${JSON.stringify(templates, null, 1)}\n`);
  }

  const committed = JSON.parse(readFileSync(TEMPLATES, 'utf8'));
  assert.deepEqual(
    committed,
    templates,
    'Run UPDATE_IMPORT_TEMPLATES=1 yarn test to refresh import_templates.json'
  );
});

// covers: AC-3
test('each template starts with the name column, which is required', () => {
  for (const template of getTemplates()) {
    const [first] = template.columns;
    assert.equal(first.key, template.name_key, template.schema_name);
    assert.equal(first.required, true, template.schema_name);
    assert.ok(
      template.columns.every(({ table, required }) => !table || !required),
      `${template.schema_name}: child columns are never required`
    );
  }
});
