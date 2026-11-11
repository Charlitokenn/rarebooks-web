# 0003. Choose the accounts the dashboard lists

**Date**: 2026-11-10
**Status**: Proposed

Decision history: [rationale.md](rationale.md).

## Summary

Accounting Settings gets a "Dashboard" section with a table of accounts, and the Account balances card lists only those accounts once any are picked. You may pick any leaf (not a group) Asset or Liability account, so a petty cash box or a loan can sit next to the bank. With the table empty, or when no picked account still qualifies, the card lists every Cash and Bank account, as it does today. This is a hand port of develop's spec 0003 onto v16's own Accounting Settings, and it follows v16's rule that reports read through `get_list` (so the caller's rights apply) rather than develop's permission bypass.

## Requirements

**User stories**:
- As a Books Manager, I want to pick which accounts the Account balances card lists, so the dashboard shows the money accounts my business actually watches (for example petty cash, or a loan).
- As a Books Manager, I want to reach that setting from the card itself, so I don't have to hunt for it in Settings.
- As any reader of the card, I want it to keep working with no setup, so a new company sees its Cash and Bank accounts right away.

**Acceptance criteria**:
- **AC-1**: The General tab of Settings (Books Accounting Settings) has a "Dashboard" section after the Fiscal Year fields (after `setup_complete`) and before the regional section (`default_section_break_30`, which holds Tax ID and GSTIN). It holds a "Dashboard Accounts" table with one Account link per row, and under the table the help line "The accounts the dashboard's Account balances card lists. Leave empty to list every cash and bank account." Users who can write Accounting Settings (System Manager, Books Manager) can add, remove and save rows, with no limit on the number of rows (the card body already scrolls, spec 0001 AC-9). Books User and Books Cashier see the table read only, as they see the rest of the tab.
- **AC-2**: The Account picker in that table offers only leaf (`is_group = 0`) accounts whose `root_type` is Asset or Liability, in /books and in Desk, and /books offers no Create.
- **AC-3**: Saving Accounting Settings is refused, with a message naming the account, when a newly added or changed row holds a group account or an account whose root type is not Asset or Liability. Saving is always refused when the same account is on the table more than once. A row that was valid when saved and has since stopped qualifying does not block saving other settings. These rules live in the controller.
- **AC-4**: When at least one picked account is still a leaf Asset or Liability account, the card lists exactly those accounts (and no others), in chart of accounts order (`lft`), each with its balance and the Total, following every rule of spec 0001 AC-2 to AC-12. A liability shows its debit minus credit balance (usually negative, so in red with a minus sign, spec 0001 AC-6) and lowers the Total.
- **AC-5**: When the table is empty, or none of the picked accounts is still a leaf Asset or Liability account, the card lists every leaf Cash and Bank account, exactly as spec 0001 AC-1 describes. The empty copy stays "No cash or bank accounts" and the subtitle stays "As of {date}" (spec 0001 AC-3) in every case. The fallback is silent on purpose: the card does not say that picked accounts were skipped, even while the table still holds them.
- **AC-6**: After the settings are saved, the card shows the new list once the user accepts the "Reload RareBooks?" prompt that Settings shows after every save, or the next time the dashboard page is opened. Closing the Settings dialog without the reload leaves the card as it was, the same as every other setting.
- **AC-7**: The card header shows a small ghost icon button (settings icon) with the tooltip and accessible name "Choose accounts", only to users who can write Accounting Settings, in every state of the card (loading, error, empty and loaded). It opens Settings on the General tab (`/settings?tab=AccountingSettings`): the settings dialog on desktop, the settings page on a phone.
- **AC-8**: Deleting a Books Account that is on the dashboard table is refused with `frappe.LinkExistsError`, whose message names Books Accounting Settings, and the card is unchanged.
- **AC-9**: `get_cash_balances` keeps its signature (no arguments) and its response shape (`accounts: [{account, balance}]`, `total`, `as_of`). Every read in it goes through `frappe.get_list` or an explicit permission check, with no `ignore_permissions`: the caller needs read on Books Ledger Entry, Books Account and Books Accounting Settings, and gets `frappe.PermissionError` (403) without any one of them. The client shows the card, and its dashboard row, only when the user can read all three. All four Books roles read Accounting Settings today, so no existing role loses the card.
- **AC-10**: The new doctype and fields arrive through `bench migrate` on MariaDB with no patch. An existing site's table starts empty, so its card is unchanged until someone picks accounts.

## Decision

**Chosen option**: Option 2: develop's child table design, ported onto v16's Accounting Settings, with every read through `get_list` and a third read gate on the card.

Add a `dashboard_accounts` table (new child doctype Books Dashboard Account, one required `account` link with `link_filters`) to Books Accounting Settings, validate it per row in that controller, and change `_dashboard_accounts()` in `reports/dashboard.py` to list the picked leaf Asset or Liability accounts in chart order, falling back to the leaf Cash and Bank accounts when none qualify.

Every leaf Asset or Liability account may be picked on purpose, not just money accounts: receivables, stock and fixed assets included. The business decides what the card means; the setting does not narrow it to cash.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:

| DocType | Field | Type | Required | Notes |
|---|---|---|---|---|
| Books Accounting Settings (single, existing) | `dashboard_section_break` | Section Break | | label "Dashboard", in `field_order` right after `setup_complete` and before `default_section_break_30` |
| | `dashboard_accounts` | Table, options Books Dashboard Account | no | label "Dashboard Accounts", `description` holds the help line from AC-1 |
| Books Dashboard Account (new child doctype) | `account` | Link, options Books Account | yes | label "Account", `reqd: 1`, `in_list_view: 1` (this makes it the table's column), `link_filters` `[["Books Account","is_group","=",0],["Books Account","root_type","in",["Asset","Liability"]]]` |

The child doctype JSON copies the doctype keys of `books_default_cash_denominations.json` (the child table Books Defaults already shows on Settings): `istable: 1`, `editable_grid: 1`, `module: "Frappe Books"`, `engine: "InnoDB"`, `row_format: "Dynamic"`, `field_order: ["account"]`, `permissions: []` (a child takes its parent's permissions), and no `track_changes` (the parent single already has `track_changes: 1`, so row changes land in its version history). The two new fields on the single take the default `permlevel` 0 and are not `read_only`.

Relationships: Books Accounting Settings 1:N Books Dashboard Account (rows, `parenttype = "Books Accounting Settings"`, `parentfield = "dashboard_accounts"`). Books Dashboard Account N:1 Books Account (`account` points at `Books Account.name`, which is the `account_name`).

Constraints (in the controller, not the database): each `account` at most once per table; each newly added or changed row is a leaf Asset or Liability account. No index (a handful of rows). No retention rule: rows live as long as the setting.

Migration: the new child doctype and the two fields arrive through `bench migrate`. No patch, since an empty table is the intended starting state (the fallback).

**State transitions**: none.

**API surface**:
| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `frappe_books.reports.dashboard.get_cash_balances` (signature and shape unchanged) | POST via `call()` | none | `accounts: [{account, balance}]`, `total`, `as_of` | logged in; read on Books Ledger Entry, Books Accounting Settings and Books Account | `frappe.PermissionError` (403) without any of the three |
| Save of Books Accounting Settings (existing `/api/v2` document save through `FrappeDoc.sync`, or Desk) | PUT | the single, with `dashboard_accounts` rows `[{name?, account}]` | the saved single | write on Books Accounting Settings | `frappe.ValidationError` (417) for a duplicate, a group, or a root type other than Asset or Liability |
| Delete of a Books Account (existing) | DELETE | account name | | existing | `frappe.LinkExistsError` when a dashboard row links it |

Server shape:
- `frappe_books/frappe_books/doctype/books_dashboard_account/`: `__init__.py`, `books_dashboard_account.json`, and `books_dashboard_account.py` with an empty `BooksDashboardAccount(Document)` and the auto generated typing block (let Frappe generate it).
- `frappe_books/accounting/accounts.py`: add `DASHBOARD_ROOT_TYPES = ("Asset", "Liability")` beside `PAYMENT_ACCOUNT_TYPES`. It is the one source of the allowed root types. Both the controller and `dashboard.py` import it from here, so the report never imports a doctype controller.
- `books_accounting_settings.py`:
  - `validate()` calls a new `self.validate_dashboard_accounts()` after `validate_changed_accounts(self, ACCOUNT_TYPES)`. The existing helper checks single fields with `has_value_changed`, which does not apply to a table, so the table gets its own method:
    - Rows with an empty `account` are skipped in every step below. Frappe's required field check reports them.
    - Duplicates first, over every row: the first account seen twice throws `_("{0} is on the dashboard more than once.").format(account)`.
    - Then only rows that are new or whose `account` changed, matched row by row by the child row's `name`, not against the set of accounts the table held before. `before = self.get_doc_before_save()`, `previous = {row.name: row.account for row in before.dashboard_accounts} if before else {}`, and a row is checked when `previous.get(row.name) != row.account`. A new row has no `name` in `previous`, so it is checked. This also catches a row edited to an account that another row held until it was removed in the same save, which a set of previous accounts would wrongly skip. This relies on the client sending each saved row's `name`, which it does (`frontend/src/frappe/document.ts`, the `_savedRows` check near line 411), and Desk does the same. `get_doc_before_save()` is never None for a Single once it exists (the controller's `has_value_changed` calls already rely on this); the `if before else {}` guard only covers a first ever save.
    - For each such row call `validate_account(row, "account", root_types=DASHBOARD_ROOT_TYPES)`. It already throws for a group account and for a wrong root type, naming the field label ("Account", from the row's meta) and the account.
  - Keep the auto generated typing block in sync (Frappe regenerates it with `dashboard_accounts: DF.Table[BooksDashboardAccount]`).
- `reports/dashboard.py`:
  - Add `SETTINGS = "Books Accounting Settings"` beside `LEDGER`.
  - `_dashboard_accounts()`, the seam spec 0001 left for this feature, docstring "Return the picked accounts the balances card lists, else the leaf cash and bank accounts, in chart order.":
    - `frappe.has_permission(SETTINGS, "read", throw=True)` first, so a caller without Settings read gets the same 403 every time, whatever `get_list` does with a child of a single.
    - `picked = frappe.get_list("Books Dashboard Account", parent_doctype=SETTINGS, filters={"parenttype": SETTINGS, "parentfield": "dashboard_accounts"}, pluck="account", limit_page_length=0)`. Reading the child rows directly is lighter than `frappe.get_single`, which loads the whole single and its virtual `country`. The `parent_doctype` pattern is already used in `reports/gst.py` and `printing.py`, but there with regular parent documents, not a Single, so build step 1 tests it first (see Critical test scenarios). Decided fallback if `get_list` on this child fails or returns nothing for a reader who can read the Settings: keep the explicit `has_permission` check above, then read `[row.account for row in frappe.get_cached_doc(SETTINGS).dashboard_accounts if row.account]`. Rights are still checked before the read, so this is not a bypass.
    - If `picked`: `names = frappe.get_list("Books Account", filters={"name": ["in", picked], "is_group": 0, "root_type": ["in", DASHBOARD_ROOT_TYPES]}, order_by="lft", pluck="name", limit_page_length=0)`, then `if names: return names`.
    - After that `if` (reached when nothing is picked, or every picked account is stale), return today's Cash and Bank query unchanged. Write it as an early return plus one fall through, not an `else`.
    - Books Account has no `disabled` field on v16, so no disabled filter is needed in either branch.
    - A rename with merge of two picked accounts (Books Account has `allow_rename`) can leave one account on two rows. The `name in picked` filter still lists it once on the card, and the next save of the settings reports the duplicate, so no extra handling is needed.
  - `get_cash_balances()` itself does not change: its ledger check, its query and its response stay as they are. Update its docstring to "Return the balance as of today of each account the dashboard lists, and their total."

Client shape:
- `frontend/models/baseModels/AccountingSettings/AccountingSettings.ts`:
  - A row model `export class DashboardAccount extends FrappeDoc` with `static override presentation = { label: 'Dashboard Account', fields: withoutCreate(['account']) }`, written like `DefaultCashDenominations` in `Defaults.ts`.
  - On `AccountingSettings`: `static override rowModels = { dashboard_accounts: DashboardAccount };` and `declare dashboard_accounts?: (FrappeDoc & { account?: string })[];`. `rowModels` is the only registration; row models are not listed in `frappeModels`, and the schema name comes out as `DashboardAccount`.
  - The picker's filters come from the DocField `link_filters` (`schema.ts` `getLinkFilters`), so no `static filters` entry is added for the row. The existing `static filters` for the three single account fields stay as they are.
- `frontend/src/pages/Settings/SettingsField.vue`: one edit. The stacked branch (every Table field) shows the table's label but never `field.sub_label`, so the help line would not appear. Under the `<Table>` in that branch, add `<p v-if="field.sub_label" class="text-p-sm text-ink-gray-5">{{ field.sub_label }}</p>`. Nothing else in Settings changes: the General tab renders the new section and table the way the Defaults tab renders `pos_cash_denominations`.
- Read only for non writers (AC-1): `Table.vue` decides row editing from `df.edit` and add or remove from `isReadOnly`, and it is not yet confirmed that Settings sets them for a user who cannot write the single. Build step 2 checks it in the browser as a Books User. If rows can still be added, removed or edited, pass read only into the stacked `<Table>` from the doc's save permission (`doc.canSave`) in `SettingsField.vue`, and nowhere else.
- `frontend/src/pages/Dashboard/Dashboard.vue`: add `settings: fyo.can(ModelNameEnum.AccountingSettings, 'read')` to `canRead`, and add `&& canRead.settings` to both the row gate and the card gate (today `canRead.ledger && canRead.accounts`). Update the comment that says Best sellers will widen the row gate, so it still reads true.
- `frontend/src/pages/Dashboard/AccountBalances.vue`: fill `FrappeChartContainer`'s `#actions` slot with a `FrappeButton` written like the one in `InvoiceCards.vue`: `variant="ghost"`, `:size="isMobile ? 'md' : 'sm'"`, `icon="lucide-settings-2"`, `:label` and `:tooltip` both ``t`Choose accounts` ``, and `:route="{ path: '/settings', query: { tab: ModelNameEnum.AccountingSettings } }"`, rendered only when `fyo.can(ModelNameEnum.AccountingSettings, 'write')`. Check in the browser that the icon only button exposes "Choose accounts" as its accessible name; if it does not, add an `aria-label` with the same text. The router guard already opens the dialog on desktop and the page on a phone; the dialog path takes `query.tab` into `settingsDialog.tab` (`openSettingsDialog` in `src/router.ts`), and the page reads `query.tab` in `Settings.vue`. The `#actions` slot sits in the container's header, outside the loading, error and empty slots the card fills, so the button shows in every state (checked in frappe-ui 1.0.0's `ChartContainer.vue`).
- The card is not refetched when the Settings dialog closes. It follows the reload prompt like every other setting (AC-6), so no watcher or event is added.
- The empty copy and the subtitle do not change.

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| Settings | whether the table can be edited | the existing Settings save permission (write on Books Accounting Settings), which the Table's row editing follows, as for every other field on the tab |
| Settings | the help line | the `dashboard_accounts` DocField `description`, mapped to `sub_label` by `schema.ts` and shown by the stacked branch of `SettingsField.vue` (translated by Frappe) |
| Settings save | the picked accounts | the user's rows, stored as Books Dashboard Account `account` under Books Accounting Settings |
| Settings save | "unchanged row" for the stale row rule | `get_doc_before_save().dashboard_accounts`, matched to the current rows by row `name` |
| Settings save | allowed root types and leaf rule | `DASHBOARD_ROOT_TYPES` in `accounting/accounts.py`, plus `validate_account`'s `is_group` check |
| Settings save | the label in the group or root type message | `row.meta.get_label("account")`, inside `validate_account` ("Account") |
| Account picker | the accounts offered | the DocField `link_filters` (leaf, Asset or Liability), applied by `schema.ts` and by Desk |
| Account picker | no Create | `withoutCreate(['account'])` on the `DashboardAccount` row model |
| `_dashboard_accounts` | whether the caller may read the picks | `frappe.has_permission(SETTINGS, "read", throw=True)`, then `get_list` with `parent_doctype` |
| `_dashboard_accounts` | which accounts are listed | picked rows filtered by `is_group = 0` and `root_type in DASHBOARD_ROOT_TYPES` through `get_list` on Books Account; when that is empty, the leaf Cash and Bank query (spec 0001) |
| `_dashboard_accounts` | row order | Books Account `lft`, in both branches |
| `get_cash_balances` | balances, Total, `as_of` | unchanged from spec 0001 |
| Dashboard.vue | whether the card and its row show | `canRead.ledger && canRead.accounts && canRead.settings` (boot permissions through `fyo.can`) |
| AccountBalances.vue | whether the settings button shows | `fyo.can(ModelNameEnum.AccountingSettings, 'write')` |
| AccountBalances.vue | where the button goes | route `{ path: '/settings', query: { tab: 'AccountingSettings' } }` |
| Card refresh after a save | the new list | the existing "Reload RareBooks?" prompt in `useSettings.ts`, or the next dashboard page load |

**Translations**: the new strings follow the usual path. The Python message `"{0} is on the dashboard more than once."` is wrapped in `_()`. The DocField labels ("Dashboard", "Dashboard Accounts", "Account") and the help line come from the doctype JSON, which Frappe extracts. "Choose accounts" is a `t` tag. Run the project's usual extraction (`babel_extractors.csv`).

**Key invariants**:
- The card never lists a group account, so no amount is counted twice (spec 0001's leaf invariant still holds).
- The card is never empty only because of the setting: a table that yields no qualifying account falls back to Cash and Bank.
- The allowed root types are defined once (`DASHBOARD_ROOT_TYPES`) and used by both the save rule and the read filter. The DocField `link_filters` mirror them for the picker only, and a Python test keeps the mirror in step.
- `get_cash_balances` still takes no arguments and never depends on the period selector.
- No read in the card's path skips permissions: every query is `frappe.get_list` with dict filters, plus explicit `has_permission` checks (v16 reports rule).

**Security model**:
Changing the list needs write on Books Accounting Settings (System Manager and Books Manager have it; Books User and Books Cashier read only). Frappe's document save enforces that, and the client shows the button only to those users. Reading the list happens inside `get_cash_balances` with the caller's own rights: ledger read (existing check), Settings read (new explicit check plus `get_list` with `parent_doctype`) and Account read (`get_list`). The client gate mirrors all three, so no role is shown a card that would 403. The picks are account names a ledger reader already sees on its entries, so nothing new is exposed. No regulated data, no compliance scope, and no audit log beyond Frappe's own version history of the single.

**Configuration required**: none.

**Critical test scenarios**:

Test setup rules (Python): add a helper to `frappe_books/tests/accounting.py`, for example `set_dashboard_accounts(*accounts)`, that sets the table on the single and saves, and have every test that uses it clear the table in a `finally` (or `addCleanup`), so a later test or teardown that deletes a picked account does not hit `LinkExistsError`. Tests that need saved row names get the single with `frappe.get_single(SETTINGS)`, change `doc.dashboard_accounts` in place (edit `row.account`, `doc.remove(row)`, `doc.append(...)`), then call `doc.save()`. Rebuilding the rows from dicts without their `name`s would make every row look new.

- Read path first (Python, `test_dashboard.py`, build step 1): with picks saved, `_dashboard_accounts()` returns them for a Books Manager, and raises `frappe.PermissionError` for a user with ledger and Account read but no Settings read. If `get_list` with `parent_doctype` on this child of a Single fails this, switch to the decided `get_cached_doc` fallback in Server shape and keep the test. Verifies **AC-4**, **AC-9**.
- Delete block first (Python, `test_dashboard.py`): deleting an account on the table raises `frappe.LinkExistsError`. This is the least certain claim in the spec (a link from a child row of a single), so the test is written in build step 1, before anything is built on it. The test asserts both the error class and that its message names Books Accounting Settings. If Frappe's link check does not raise it, the fallback is decided: in `BooksAccount.on_trash`, after the existing root and child account throws (their messages are more specific) and before `super().on_trash()`, throw `frappe.LinkExistsError` with `_("{0} is on the dashboard. Remove it from Accounting Settings first.")` when `frappe.db.exists("Books Dashboard Account", {"account": self.name})`, and keep the same test. No Books code deletes accounts in bulk (`coa.py` only creates them). Verifies **AC-8**.
- Picked list (Python, `test_dashboard.py`): put two leaf accounts on the table (a Bank and a Liability made with `make_account`), post entries, and assert the card returns exactly those two, in `lft` order, with the liability negative and the Total their sum. Verifies **AC-4**.
- Fallback (Python): an empty table returns the Cash and Bank leaves. A table whose only account was turned into a group (`frappe.db.set_value` on `is_group`, to simulate drift) also returns them. A table with one stale and one valid account returns only the valid one. Verifies **AC-5**.
- Save rules (Python, `test_settings_accounts.py`, beside the other Accounting Settings account rules): a duplicate throws; a group account throws; an Income account throws; a valid Asset and a valid Liability save. With a saved row made stale by `db.set_value`, saving another field still succeeds. Editing that stale row to a different invalid account throws. With two saved rows, the first on a since staled account, removing the first row and editing the second to that stale account in the same save throws. The tests send the saved rows with their `name`s, as the client does. Verifies **AC-3**.
- Mirror (Python): the `account` DocField's `link_filters` on Books Dashboard Account, parsed from the meta, name exactly the root types in `DASHBOARD_ROOT_TYPES` plus `is_group = 0`. Verifies **AC-2**.
- Permission (Python): a user with ledger and Account read but no Accounting Settings read gets `frappe.PermissionError`; a user without ledger read still gets it; a Books Manager gets the picked accounts. Verifies **AC-9**.
- Migrate (CI): the MariaDB CI job runs `bench migrate` on a fresh site and the Python suite. Verifies **AC-10**.
- No Create and the table (node, `settings-models.test.mjs`): `getSchema('DashboardAccount')`'s `account` field has a falsy `create`, and `AccountingSettings` lists `dashboard_accounts` as a Table of `DashboardAccount`. `link-create.test.mjs` only visits the fields in `previousForms.linkCreate`, so it never sees the new link. Then `yarn test` passes, including the `settings-readers`, `settings-models` and `link-create` guards. Verifies **AC-2**.
- Settings flow (Playwright, `settings-form.spec.ts`, desktop): open Settings, General tab, Dashboard section, and see the help line; the picker lists no group, Income or Expense account and no Create; add a bank and a liability, save, accept the reload; the card shows only those two. Clear the table, save, reload; the card shows Cash and Bank again. Verifies **AC-1**, **AC-2**, **AC-4**, **AC-5**, **AC-6**.
- Settings button (Playwright, `dashboard-account-balances.spec.ts` and `mobile-dashboard.spec.ts`): as a Books Manager the button shows with the tooltip and accessible name "Choose accounts", including while the request is held (loading) and when it is failed (error), and it opens the General tab (a dialog on desktop, the page on a phone). As a user who can read the ledger, Accounts and Settings but not write Settings, the button is absent. Verifies **AC-7**.
- Card gate (node or Playwright): with Settings read removed from a ledger and Account reader, the card and its row do not render. Verifies **AC-9**.

## Build plan

Tracer Bullet: first one thin thread from the setting to the card (schema, seam, Settings screen, card), then thicken it with the save rules, the permission gate, the button and the browser tests.

1. Add the Books Dashboard Account child doctype and the `dashboard_section_break` and `dashboard_accounts` fields on Books Accounting Settings (with `link_filters` and the description), and run `bench migrate`. Add the test helper that sets and clears the table. Write the read path and delete block tests first: if `get_list` on the child of the Single fails, use the `get_cached_doc` fallback, and if `LinkExistsError` is not raised, add the `on_trash` fallback, both named in Critical test scenarios, before going on. Then add `DASHBOARD_ROOT_TYPES` and change `_dashboard_accounts()` to read the picked rows through `get_list` (with the Settings permission check and the Cash and Bank fallback), and add the Python tests for the picked list and the empty table fallback. Satisfies **AC-4**, **AC-5**, **AC-8**, **AC-10**.
2. Add the `DashboardAccount` row model (no Create) and `rowModels` on `AccountingSettings`, add the help line to the stacked branch of `SettingsField.vue`, add the node test, then check in the browser that the General tab shows the Dashboard section and its help line, the table is read only for a Books User (else apply the `doc.canSave` fix in Client shape), a pick saves, and after the reload the card lists the pick. This closes the thread end to end. Satisfies **AC-1**, **AC-2**, **AC-6**.
3. Add `validate_dashboard_accounts()` to the Accounting Settings controller, and add the Python tests for the save rules, the stale row, the stale fallback, the liability sign, the `link_filters` mirror and the three read permissions. Add `canRead.settings` to the dashboard's row and card gates. Satisfies **AC-3**, **AC-4**, **AC-5**, **AC-9**.
4. Add the "Choose accounts" icon button to the card's `#actions` slot, gated on write to Accounting Settings, and check it shows while loading, on error, when empty and when loaded, on a phone and in dark mode, with the right accessible name. Satisfies **AC-7**.
5. Add the Playwright tests for the settings flow, the button (desktop and the mobile dashboard spec) and the card gate, then run `yarn test`, `yarn lint`, `yarn typecheck` and ruff. Satisfies **AC-1**, **AC-2**, **AC-4**, **AC-5**, **AC-6**, **AC-7**, **AC-9**.

## Consequences

**Positive**:
- The change lands in one seam (`_dashboard_accounts()`) that spec 0001 left for it. `get_cash_balances`, its response and its client call stay as they are.
- No new settings single, tab or endpoint. The Settings screen, its save and its reload prompt are reused as they are.
- A new company still sees its Cash and Bank accounts with zero setup.
- The card stays inside v16's reports rule, so a future per user restriction on accounts or settings hides data instead of leaking it.

**Negative / tradeoffs**:
- Any leaf Asset may be picked, so a business that adds receivables, stock or fixed assets gets a Total that is no longer money it can spend. The card does not warn about it.
- Once a liability is picked, the Total is a net figure (money minus debt), not cash on hand. Nobody is told the Total changed meaning.
- A picked account that stops qualifying is skipped silently, and its row stays in the table until someone removes it.
- Only new or changed rows are checked on save. An unrelated settings save keeps working, but the stored table can hold an account that would no longer pass.
- The card now needs a third read (Accounting Settings). Every Books role has it today, but a custom role with ledger and Account read and no Settings read loses the card it had before.
- A link from the settings' child table now blocks deleting a picked account. Someone cleaning up the chart of accounts has to remove the row first.
- The General tab gets longer, and the setting sits far from the dashboard. The card button only helps users who can write the settings.

**Neutral**:
- Spec 0001's AC-1 (every Cash and Bank account) is now the fallback rule, not the only rule, and its AC-8 card gate gains Settings read.
- The order stays chart order. Reordering rows in the table has no effect on the card.
- This port drops develop's three database criterion (v16 is MariaDB only) and develop's `account_name` in the response (spec 0001 removed it).

## Follow-up

- [ ] Tick spec 0001's Follow-up item "Feature 4 (choose dashboard accounts) replaces `_dashboard_accounts()`" once this ships, and note there that its AC-8 gate now includes Settings read.
- [ ] Feature 3 (best sellers) widens the dashboard row gate to `|| canRead.sales`; it must keep the card's own gate at all three reads.
- [ ] If people pick liabilities often, consider labelling the Total "Net", or adding a tooltip, when any listed account is a liability. Left out on purpose to keep spec 0001's card unchanged. Revisit after the first users pick a liability.
- [ ] `frontend/node_modules` holds frappe-ui 1.0.2 while the lockfile pins 1.0.0; run `yarn install --check-files` in `frontend/` before building (also spec 0001's follow up). The `#actions` slot and the Button props used here were checked against 1.0.0.
