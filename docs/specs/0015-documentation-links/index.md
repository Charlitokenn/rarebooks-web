# 0015. Point documentation links at the RareBooks docs

**Date**: 2026-11-23
**Status**: Accepted

## Summary

Every help link in the /books app opens the RareBooks docs on `rarebooks.cc`, not Frappe's `docs.frappe.io`. The docs address lives in one frontend file, next to one map from each screen to its docs page. A screen with no page of its own opens the nearest overview page, and if there is none, the docs Getting started page, so a link never lands on a 404 (a "page not found" error). A unit test checks every link against a committed list of real docs pages.

## Requirements

**User stories**:
- As a Books User, I want Documentation on any screen to open the RareBooks page for that screen, so that the help I read matches the app I use.
- As a Books User on a screen with no docs page yet, I want a useful overview page, not a "page not found".
- As a maintainer, I want one place to change the docs address, and a test that fails when a link points at a page that does not exist.

**Acceptance criteria**:
- **AC-1**: No file under `frontend/src` (sources, not built assets) contains `docs.frappe.io`.
- **AC-2**: The docs base address `https://rarebooks.cc` is defined once, as `DOCS_BASE_URL` in `frontend/src/utils/docs.ts`; every docs link in the app is built from it by `docsUrl()`.
- **AC-3**: Opening Documentation (sidebar item or F1) from a form, list, report, Settings, Chart of Accounts, Print template, Import wizard or Dashboard screen opens, in a new tab with `noopener,noreferrer`, `DOCS_BASE_URL` plus that screen's mapped path from `docsPathMap` (the table under *Feature design*).
- **AC-4**: Fallbacks: a report with no entry opens the Reports overview (`/financial-reports/reports/`); a list or form with no entry opens Master data (`/masters/master-data/`); any other screen, or no screen (`docsPathRef` empty), opens `DOCS_HOME` (`/getting-started/getting-started-with-rarebooks/`). Sales Quote opens Sales Invoice and Expense opens Payments until they get pages of their own.
- **AC-5**: The search bar's docs link opens `/getting-started/quick-search/`.
- **AC-6**: Each Get started card's Documentation opens the matching RareBooks page, with the heading anchor where today's link has one (`#add-taxes`, `#add-sales-items`, `#add-customers`, `#creating-purchase-invoices`).
- **AC-7**: The Settings screen (phone page and desktop dialog) points Documentation at the active tab's page when it has one (Inventory Settings, POS Settings), else `/settings/settings/`; closing the desktop dialog puts back the value the screen underneath had. The POS screen points it at `/transactions/point-of-sale/`. Lead forms and lists point at `/transactions/lead/`.
- **AC-8**: A node unit test fails if any `docsPathMap` value, `DOCS_HOME`, or Get started link (path and anchor) is not in `frontend/tests/docs_pages.json`, the committed list of `rarebooks-site` docs paths and their linked anchors.

## Decision

**Chosen option**: Option 1: Frontend constant and a frontend map.

Move the docs map into `frontend/src/utils/docs.ts`, point it at RareBooks docs paths on `https://rarebooks.cc`, build every docs link through `docsUrl()`, and guard the paths with a unit test against a committed page list.

**Implementation skills**: `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`)

## Feature design

**Data model sketch**: none. No DocType, field or migration. One new TS module and one JSON fixture.

**Module** `frontend/src/utils/docs.ts`:
- `DOCS_BASE_URL = 'https://rarebooks.cc'` (no trailing slash)
- `DOCS_HOME = '/getting-started/getting-started-with-rarebooks/'`
- `docsPathMap: Record<string, string | undefined>` (moved from `misc.ts`; `misc.ts` stops exporting it and every importer switches to `src/utils/docs`)
- `docsUrl(path: string, anchor?: string): string` returns `DOCS_BASE_URL + (path || DOCS_HOME) + (anchor ? '#' + anchor : '')`
- `openDocs(path: string, anchor?: string): void` calls `window.open(docsUrl(path, anchor), '_blank', 'noopener,noreferrer')`; `openDocumentation` in `appMenu.ts` (as `openDocs(docsPathRef.value)`), `SearchBar.openDocs` and `GetStarted.handleDocumentation` call it.
- `settingsDocsPath(tab: string): string` returns `docsPathMap[tab] ?? docsPathMap.Settings ?? DOCS_HOME` (pure, so the tab rule is unit tested without mounting a component).
- `holdDocsPath(path: string): { update(path: string): void; release(): void }` sets `docsPathRef` to `path` and returns a handle. `release()` puts back the value `docsPathRef` had before, but only if `docsPathRef` still equals the value last held. If another screen has set its own path in the meantime (a route change closed the dialog), it leaves that value alone. The returned handle also has `update(path)` to change the held value (a tab switch) while keeping the guard.
- The `!` assertions on `docsPathMap.Reports` (`Report.vue`) and `docsPathMap.ChartOfAccounts` (`ChartOfAccounts.vue`) become `?? DOCS_HOME`.

Paths start and end with `/` (Starlight's canonical form, so no redirect). `docsPathRef` keeps holding a path, now in this form.

**docsPathMap** (key: path):

| Key | Path |
|---|---|
| Dashboard | `/basics/dashboard/` |
| Reports | `/financial-reports/reports/` |
| GeneralLedger | `/financial-reports/general-ledger/` |
| ProfitAndLoss | `/financial-reports/profit-and-loss-statement/` |
| BalanceSheet | `/financial-reports/balance-sheet/` |
| TrialBalance | `/financial-reports/trial-balance/` |
| SalesQuote | `/transactions/sales-invoice/` |
| SalesInvoice | `/transactions/sales-invoice/` |
| PurchaseInvoice | `/transactions/purchase-invoice/` |
| Payment | `/transactions/payments/` |
| Expense | `/transactions/payments/` |
| JournalEntry | `/transactions/journal-entries/` |
| LoyaltyProgram | `/transactions/loyalty-program/` |
| Lead | `/transactions/lead/` |
| POS, POSSettings | `/transactions/point-of-sale/` |
| PricingRule | `/masters/pricing-rule/` |
| CouponCode | `/masters/coupon-code/` |
| StockMovement | `/inventory/stock-movement/` |
| Shipment | `/inventory/shipment/` |
| PurchaseReceipt | `/inventory/purchase-receipt/` |
| StockLedger | `/inventory/stock-ledger/` |
| StockBalance | `/inventory/stock-balance/` |
| Batch | `/inventory/batches/` |
| SerialNumber | `/inventory/serial-number/` |
| InventorySettings | `/inventory/inventory-settings/` |
| Entries | `/masters/master-data/` |
| Party | `/masters/party/` |
| Item | `/masters/items/` |
| Tax | `/masters/taxes/` |
| PriceList | `/masters/price-list/` |
| PrintFormat | `/settings/print-templates/` |
| Search | `/getting-started/quick-search/` |
| NumberSeries | `/settings/number-series/` |
| ImportWizard | `/getting-started/import-wizard/` |
| Settings | `/settings/settings/` |
| ChartOfAccounts | `/getting-started/chart-of-accounts/` |
| CustomForm | `/settings/customize-form/` |

`GSTR1` and `GSTR2` are removed, so they take the Reports fallback. Keys use `ModelNameEnum` where one exists, as today.

**Get started links**: `ListItem.documentation` (in `frontend/src/utils/types.ts`) changes from a URL string to `{ path: string; anchor?: string }`, set inside `getGetStartedConfig()`. `GetStarted.handleDocumentation` calls `openDocs(documentation.path, documentation.anchor)`; the `v-if="item.documentation"` check is unchanged.

| Card | Path | Anchor |
|---|---|---|
| Review accounts | `/getting-started/chart-of-accounts/` | |
| Opening balances | `/getting-started/setup-opening-balances/` | |
| Add taxes | `/getting-started/create-initial-entries/` | `add-taxes` |
| Add items | `/getting-started/create-initial-entries/` | `add-sales-items` |
| Add customers | `/getting-started/create-initial-entries/` | `add-customers` |
| Sales invoice | `/transactions/sales-invoice/` | |
| Purchase invoice | `/transactions/purchase-invoice/` | `creating-purchase-invoices` |

**Screen wiring** (who sets `docsPathRef`, on `activated`, cleared on `deactivated` as today):

| Screen | Value |
|---|---|
| `CommonForm.vue` | `docsPathMap[schemaName] ?? docsPathMap.Entries` (was `?? ''`) |
| `ListView.vue` | unchanged: `docsPathMap[schemaName] ?? docsPathMap.Entries` |
| `Report.vue` | unchanged: `docsPathMap[reportClassName] ?? docsPathMap.Reports` |
| `Dashboard.vue` | `docsPathMap.Dashboard` (was the literal `books/dashboard`) |
| `Settings.vue` (phone) | `settingsDocsPath(activeTab)`, set in `activated` after the line that reads `?tab=`, and again in the `activeTab` watcher |
| `SettingsDialog.vue` (desktop) | a `watch` on `[settingsDialog.open, activeTab]` (the computed tab, which already falls back when the saved tab is hidden): on open, `holdDocsPath(settingsDocsPath(activeTab))`; on a tab change while open, `update(...)` (this covers a deep link through `openSettings(tab)`); on close, `release()`. On a cold load over `/` the held prior value is `''`, so `release()` puts back the home fallback |
| `POS.vue` | `docsPathRef.value = docsPathMap.POS` as the first line of the async `activated`, before any await; cleared in `deactivated` |
| ChartOfAccounts, TemplateBuilder, ImportWizard | unchanged keys, new values |

**API surface**: none on the server. The client surface is `docsUrl`, `openDocs`, `DOCS_BASE_URL`, `DOCS_HOME` and `docsPathMap` above.

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| Open Documentation | base address | `DOCS_BASE_URL` constant |
| Open Documentation | page path | `docsPathRef`, set by the active screen from `docsPathMap` (table above) |
| Open Documentation | path when `docsPathRef` is empty | `DOCS_HOME` |
| Report or list or form fallback | overview path | `docsPathMap.Reports` / `docsPathMap.Entries` |
| Settings path | active tab's schema name | `activeTab` in `Settings.vue` / `SettingsDialog.vue` (tab values are schema names) |
| Search docs link | path | `docsPathMap.Search` |
| Get started link | path and anchor | `getStartedConfig.ts` table above |
| 404 test | the real docs pages and anchors | `frontend/tests/docs_pages.json`, hand edited from `rarebooks-site/src/content/docs` |
| Page language | English | the docs are English only; a translated UI still opens the English page |

**`docs_pages.json` shape**: an object from each docs path to the anchors the app links on it, for example `{"/transactions/purchase-invoice/": ["creating-purchase-invoices"], "/masters/items/": []}`. It lists all 42 current pages, not only the linked ones, so a new map entry can be checked without editing the list. Anchors are the Starlight heading slugs (lowercase, spaces to hyphens).

**Key invariants**:
- Every docs link starts with `DOCS_BASE_URL`; no screen builds a docs URL by hand.
- Every path in `docsPathMap`, `DOCS_HOME` and the Get started table is a key of `docs_pages.json`; every anchor is in that key's list.
- Docs open in a new tab with `noopener,noreferrer`, so the docs page can't reach the app window.

**Security model**: the links are public, carry no query string, no user or site data, and no tracking tag. No role check is needed: every Books role sees the same help.

**Configuration required**: none.

**Critical test scenarios** (`frontend/tests/docs-links.test.mjs`, plus the updated `app-menu.test.mjs`, the only existing test that names a `docs.frappe.io` URL). `tests/helpers/frappe.mjs` adds `src/utils/docs` to its esbuild export list. The new test reads `docs_pages.json` with `node:fs/promises` (not a JSON import) and scans `frontend/src` with a recursive `readdir` walk, with no new dependency. Components are not mounted (the helper stubs `.vue` files and has no DOM); the component wiring is checked in `/check verify`. Playwright tests in `tests/ui` do not assert docs URLs.
- Happy path: with `docsPathRef` set to `docsPathMap.SalesInvoice`, the Documentation item opens `https://rarebooks.cc/transactions/sales-invoice/`, verifies **AC-2**, **AC-3**
- Fallback: with `docsPathRef` empty, it opens `https://rarebooks.cc/getting-started/getting-started-with-rarebooks/`; `docsPathMap.GSTR1` is undefined, so a GST report takes the Reports path; `SalesQuote` and `Expense` map to Sales Invoice and Payments, verifies **AC-4**
- Search: the search bar link opens the quick search page, verifies **AC-5**
- Get started: each card's URL matches the table, anchors included, verifies **AC-6**
- Settings: `settingsDocsPath('InventorySettings')` and `settingsDocsPath('POSSettings')` give their pages and `settingsDocsPath('AccountingSettings')` gives `/settings/settings/`; `holdDocsPath` then `release()` restores the prior value; `update()` then `release()` also restores it; a `release()` after another screen set its own path leaves that path, verifies **AC-7**
- 404 guard: every map value, `DOCS_HOME` and Get started path and anchor is in `docs_pages.json`, verifies **AC-8**
- Drift check: when the sibling checkout `../rarebooks-site/src/content/docs` exists, the keys of `docs_pages.json` equal its `.mdx` file list (as paths); when it is missing (CI), the test is skipped with a message, verifies **AC-8**
- No Frappe links: a test walks `frontend/src` (`.ts`, `.vue`) and finds no `docs.frappe.io`, verifies **AC-1**

## Build plan

Tracer Bullet: the first task is a thin thread through the whole path (module, one screen, the sidebar, a test) that works on its own; the rest widens it.

1. Create `frontend/src/utils/docs.ts` with `DOCS_BASE_URL`, `DOCS_HOME`, `docsUrl`, `openDocs` and the full `docsPathMap`; repoint `openDocumentation` in `appMenu.ts` to `openDocs(docsPathRef.value)`; move importers off `misc.ts`; update `app-menu.test.mjs` to the new URLs, satisfies **AC-2**, **AC-3**
2. Add `frontend/tests/docs_pages.json` (all 42 pages, with the four linked anchors), export `docs.ts` from the test helper, and add `docs-links.test.mjs` with the 404 guard, the sibling drift check and the `docs.frappe.io` scan, satisfies **AC-1**, **AC-8**
3. Wire the fallbacks: `CommonForm` falls back to `Entries`, `Dashboard` reads the map, `GSTR1`/`GSTR2` dropped, the two `!` assertions become `?? DOCS_HOME`; tests for the fallback paths, satisfies **AC-3**, **AC-4**
4. Repoint the search bar link; change `ListItem.documentation` to `{ path, anchor? }` and the seven Get started links with it; tests for both, satisfies **AC-1**, **AC-5**, **AC-6**
5. Add `settingsDocsPath` and `holdDocsPath` with their unit tests, then wire `Settings.vue`, `SettingsDialog.vue` and `POS.vue` as in the screen wiring table, plus the Lead entry, satisfies **AC-7**
6. Run `yarn test`, `yarn lint`, `yarn typecheck`; check with `rg docs.frappe.io frontend/src` that nothing is left, satisfies **AC-1**

## Consequences

**Positive**:
- Help matches the product customers pay for, and sends readers to `rarebooks.cc`.
- One file holds every docs link; a renamed docs page fails a test instead of a customer's click.

**Negative / tradeoffs**:
- `docs_pages.json` is a manual copy of another repo's file list. The drift check catches a renamed page only on a machine with the sibling checkout; in CI it is skipped, so a rename pushed straight to `rarebooks-site` can still break a link in production.
- Sales Quote, Expense and the GST reports open a nearby page that does not describe them exactly.
- The docs address changes only with a frontend release.

**Neutral**:
- `docsPathMap` moves out of `misc.ts`, so eight imports change.
- Built assets under `frappe_books/` still hold the old URLs until the next `yarn build`.

## Follow-up

- [ ] Write docs pages for Sales Quote, the GST reports and Expenses in `rarebooks-site`, then repoint their map entries and add them to `docs_pages.json` (enroll in the scope's Deferred list)
- [ ] Note in `rarebooks-site`'s `AGENTS.md` that renaming or removing a docs page means updating `rarebooks-web/frontend/tests/docs_pages.json` (for `/sync`)
- [ ] `rarebooks-site`'s `src/content/docs/transactions/point-of-sale.mdx` still links to `docs.frappe.io`; repoint it in that repo
- [ ] Desk links at `/app` (Frappe's own Help menu) are out of scope; they are Frappe's, not the /books app's

Decision history (context, options, rationale): [rationale.md](rationale.md). Verify steps: [verify.md](verify.md).
