import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  docs,
  docsPathRef,
  getAppMenuItems,
  getGetStartedConfig,
} from './helpers/frappe.mjs';

const { DOCS_BASE_URL, DOCS_HOME, docsPathMap, docsUrl } = docs;
const frontend = fileURLToPath(new URL('..', import.meta.url));
const pages = JSON.parse(
  await readFile(path.join(frontend, 'tests/docs_pages.json'), 'utf8')
);
const siteDocs = path.join(frontend, '../../rarebooks-site/src/content/docs');

const getStartedLinks = () =>
  getGetStartedConfig()
    .flatMap(({ items }) => items)
    .filter(({ documentation }) => documentation)
    .map(({ key, documentation }) => [key, documentation]);

const openDocumentation = () => {
  const opened = [];
  globalThis.window.open = (...args) => opened.push(args);
  getAppMenuItems()
    .flatMap(({ options }) => options)
    .find(({ label }) => label === 'Documentation')
    .onClick();
  return opened;
};

async function* walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else {
      yield full;
    }
  }
}

// covers: AC-2, AC-3
test("Documentation opens the screen's RareBooks page in a new tab", () => {
  docsPathRef.value = docsPathMap.SalesInvoice;
  assert.deepEqual(openDocumentation(), [
    [
      'https://rarebooks.cc/transactions/sales-invoice/',
      '_blank',
      'noopener,noreferrer',
    ],
  ]);
  assert.equal(DOCS_BASE_URL, 'https://rarebooks.cc');
  docsPathRef.value = '';
});

// covers: AC-4
test('a screen with no page of its own opens the nearest overview', () => {
  docsPathRef.value = '';
  assert.equal(
    openDocumentation()[0][0],
    'https://rarebooks.cc/getting-started/getting-started-with-rarebooks/'
  );
  assert.equal(docsPathMap.GSTR1, undefined);
  assert.equal(docsPathMap.GSTR2, undefined);
  assert.equal(
    docsPathMap.GSTR1 ?? docsPathMap.Reports,
    '/financial-reports/reports/'
  );
  assert.equal(docsPathMap.Entries, '/masters/master-data/');
  assert.equal(docsPathMap.SalesQuote, docsPathMap.SalesInvoice);
  assert.equal(docsPathMap.Expense, docsPathMap.Payment);
  assert.equal(docsPathMap.Dashboard, '/basics/dashboard/');
});

// covers: AC-5
test('the search bar opens the quick search page', () => {
  assert.equal(
    docsUrl(docsPathMap.Search),
    'https://rarebooks.cc/getting-started/quick-search/'
  );
});

// covers: AC-6
test('each Get started card opens its RareBooks page and heading', () => {
  assert.deepEqual(
    getStartedLinks().map(([key, { path, anchor }]) => [
      key,
      docsUrl(path, anchor),
    ]),
    [
      [
        'Review Accounts',
        'https://rarebooks.cc/getting-started/chart-of-accounts/',
      ],
      [
        'Opening Balances',
        'https://rarebooks.cc/getting-started/setup-opening-balances/',
      ],
      [
        'Add Taxes',
        'https://rarebooks.cc/getting-started/create-initial-entries/#add-taxes',
      ],
      [
        'Add Sales Items',
        'https://rarebooks.cc/getting-started/create-initial-entries/#add-sales-items',
      ],
      [
        'Add Customers',
        'https://rarebooks.cc/getting-started/create-initial-entries/#add-customers',
      ],
      [
        'Create Sales Invoice',
        'https://rarebooks.cc/transactions/sales-invoice/',
      ],
      [
        'Create Purchase Invoice',
        'https://rarebooks.cc/transactions/purchase-invoice/#creating-purchase-invoices',
      ],
    ]
  );
});

// covers: AC-7
test("Settings point at the open tab's page, else the Settings page", () => {
  assert.equal(
    docs.settingsDocsPath('InventorySettings'),
    '/inventory/inventory-settings/'
  );
  assert.equal(
    docs.settingsDocsPath('POSSettings'),
    '/transactions/point-of-sale/'
  );
  assert.equal(
    docs.settingsDocsPath('AccountingSettings'),
    '/settings/settings/'
  );
  assert.equal(docsPathMap.POS, '/transactions/point-of-sale/');
  assert.equal(docsPathMap.Lead, '/transactions/lead/');
});

// covers: AC-7
test('the Settings dialog puts back the page of the screen underneath', () => {
  docsPathRef.value = '/transactions/sales-invoice/';
  const hold = docs.holdDocsPath('/settings/settings/');
  assert.equal(docsPathRef.value, '/settings/settings/');
  hold.release();
  assert.equal(docsPathRef.value, '/transactions/sales-invoice/');

  const switched = docs.holdDocsPath('/settings/settings/');
  switched.update('/inventory/inventory-settings/');
  assert.equal(docsPathRef.value, '/inventory/inventory-settings/');
  switched.release();
  assert.equal(docsPathRef.value, '/transactions/sales-invoice/');

  // A route change closed the dialog: the new screen keeps its own page.
  const routed = docs.holdDocsPath('/settings/settings/');
  docsPathRef.value = '/masters/items/';
  routed.update('/inventory/inventory-settings/');
  routed.release();
  assert.equal(docsPathRef.value, '/masters/items/');
  docsPathRef.value = '';
});

// covers: AC-7
test('on a cold load the dialog keeps its page over the Dashboard that activates under it', () => {
  docsPathRef.value = '';
  const hold = docs.holdDocsPath('/inventory/inventory-settings/');
  docsPathRef.value = docsPathMap.Dashboard;
  assert.equal(docsPathRef.value, '/inventory/inventory-settings/');
  hold.release();
  assert.equal(docsPathRef.value, '/basics/dashboard/');
  docsPathRef.value = '';
});

// covers: AC-8
test('every docs link is a real RareBooks docs page and heading', () => {
  const links = [
    ...Object.entries(docsPathMap).map(([key, path]) => [key, path]),
    ['DOCS_HOME', DOCS_HOME],
    ...getStartedLinks().map(([key, { path, anchor }]) => [
      `Get started ${key}`,
      path,
      anchor,
    ]),
  ];
  const missing = links.filter(
    ([, path, anchor]) =>
      !(path in pages) || (anchor && !pages[path].includes(anchor))
  );
  assert.deepEqual(missing, []);
});

// covers: AC-8
test(
  'docs_pages.json lists the pages of the sibling rarebooks-site checkout',
  {
    skip:
      !existsSync(siteDocs) &&
      'no ../rarebooks-site checkout next to this repo',
  },
  async () => {
    const files = [];
    for await (const file of walk(siteDocs)) {
      if (file.endsWith('.mdx')) {
        files.push(
          '/' +
            path
              .relative(siteDocs, file)
              .split(path.sep)
              .join('/')
              .slice(0, -4) +
            '/'
        );
      }
    }
    assert.deepEqual(Object.keys(pages).sort(), files.sort());
  }
);

// covers: AC-1
test('no source file links to the Frappe docs', async () => {
  const found = [];
  for await (const file of walk(path.join(frontend, 'src'))) {
    if (/\.(ts|vue)$/.test(file)) {
      if ((await readFile(file, 'utf8')).includes('docs.frappe.io')) {
        found.push(path.relative(frontend, file));
      }
    }
  }
  assert.deepEqual(found, []);
});
