# 0001. Account balances card on the version-16 dashboard

**Date**: 2026-11-09
**Status**: Proposed

Decision history: [rationale.md](rationale.md).

## Summary

The version-16 dashboard gets a table card that lists each cash and bank account with its balance on the server's today, plus a Total row. It is a hand port of develop's spec 0001 in its final shipped shape, rewritten for the v16 names (`Books Ledger Entry`, `reverted`). One new server method in `dashboard.py` works out the rows and the Total; a small Vue card shows them in the left half of a new dashboard row that Best sellers will later share. No new DocType, field or patch.

## Requirements

**User stories**:
- As a business owner who can read the ledger, I want to see each cash and bank account with its balance today and the total, so I know my cash on hand at a glance.
- As that user, I want to click an account to see its ledger entries, so I can check where a balance comes from.

**Acceptance criteria**:
- **AC-1**: The card lists every leaf (`is_group = 0`) Books Account whose `account_type` is Cash or Bank, in chart of accounts order (`lft`), each row showing the account's `name` and its balance (debit minus credit).
- **AC-2**: A balance counts only Books Ledger Entry rows with `reverted = 0` and `posting_date` on or before the server's today. Entries dated after that day are left out. Changing the period selector neither changes the figures nor reloads the card.
- **AC-3**: The subtitle names the date the server used, "As of {date}" formatted with `fyo.format(as_of, 'Date')`. Before the first load it reads "As of today".
- **AC-4**: A Total row, pinned at the bottom of the table, shows the sum of the listed (rounded) balances, computed on the server.
- **AC-5**: An account with a zero balance is still listed and shows `0.00` in the default ink.
- **AC-6**: A positive amount (row or Total) shows in `text-ink-green-5`. A negative amount shows with a minus sign in `text-ink-red-6`. Zero shows in `text-ink-gray-8`. The color follows the sign of the server rounded value.
- **AC-7**: Clicking an account row opens the General Ledger filtered to that account up to the card's `as_of` date, with no from date, so the ledger's closing balance equals the row's balance. The Total row is not a link.
- **AC-8**: The card renders only for users who can read both Books Ledger Entry and Books Account (`canRead.ledger && canRead.accounts`). On the server, `get_cash_balances` throws `frappe.PermissionError` for a user without ledger read, and the account read goes through `frappe.get_list`, so a user without Account read gets one too. Books User and Books Cashier see no card.
- **AC-9**: When there are more rows than fit, the body rows scroll inside the card and the header and Total row stay visible.
- **AC-10**: Before the first load succeeds, the card shows three skeleton rows. During a later reload the previous rows stay visible (no skeleton). When loaded with no rows, it shows "No cash or bank accounts". When the latest request fails, `ChartLoadError` replaces the table (even if rows loaded earlier, since `error` outranks rows), and Try again reloads it.
- **AC-11**: The card sits in the left column of a new two column row below Profit and Loss and Top expenses (`lg:grid-cols-2`, `md:h-80`). Until Best sellers is built, the row (and its divider) shows only when the card does (`canRead.ledger && canRead.accounts`), so no reader sees an empty row; feature 3 widens it to `|| canRead.sales`. The card keeps the left half even when the right column is empty. On phones it stacks full width on its own bordered card (`cardClass`) at `h-72`. Long account names truncate. It reads correctly in dark mode through frappe-ui tokens only.
- **AC-12**: The card loads each time the dashboard is shown (`activated`) and on Try again, and at no other time. When two loads overlap, only the latest one writes the rows, the Total, the date, `isLoaded` or the error; a stale load writes nothing, not even to the console.

## Decision

**Chosen option**: Option 2: port develop's final shape, adapted to v16 rules.

Add a whitelisted, argument free `get_cash_balances()` to `frappe_books/reports/dashboard.py` that returns each leaf Cash or Bank account's balance on the server's today plus their Total, reading both doctypes through `frappe.get_list`. Render it in an `AccountBalances.vue` card that extends `BaseDashboardChart` and draws its header and states with frappe-ui's `ChartContainer`.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `tailwindcss` (`hairyf/skills`, `.agents/skills/tailwindcss/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:
No new DocType, field, index or patch. Read only use of:

| DocType | Fields read | Role |
|---|---|---|
| Books Account | `name` (PK, set from `account_name` by `autoname: field:account_name`), `account_type`, `is_group`, `lft` | Picks the rows and their order |
| Books Ledger Entry | `account` (FK → Books Account.name), `debit`, `credit`, `posting_date` (Date), `reverted` | Sums each account's balance |

Relationship: Books Account 1:N Books Ledger Entry. A reversal marks the old entry reverted and adds a mirror row that is also reverted, so `reverted = 0` drops both (`accounting/ledger.py`).

**State transitions**: none (read only).

**API surface**:
| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `frappe_books.reports.dashboard.get_cash_balances` | POST via `call()` | none | `accounts: [{account: str, balance: number}]`, `total: number`, `as_of: date` | logged in, read on Books Ledger Entry and Books Account | `frappe.PermissionError` (403) without either read |

Server shape (in `dashboard.py`, after `get_top_expenses`):
- `get_cash_balances() -> dict`, whitelisted and type annotated, docstring "Return each cash and bank account's balance as of today, and their total."
- First line: `frappe.has_permission(LEDGER, "read", throw=True)`. Then `as_of = getdate()`.
- `_dashboard_accounts() -> list[str]`: `frappe.get_list("Books Account", filters={"account_type": ["in", ["Cash", "Bank"]], "is_group": 0}, order_by="lft", pluck="name", limit_page_length=0)`. This is the seam feature 4 (choose dashboard accounts) replaces.
- Skip the ledger query when the list is empty. Otherwise: `frappe.get_list(LEDGER, filters={"reverted": 0, "posting_date": ["<=", as_of], "account": ["in", names]}, fields=["account", DEBIT_MINUS_CREDIT], group_by="account", order_by="account", limit_page_length=0)`. Never order by the `balance` alias (see the comment in `get_top_expenses`).
- Rows in `_dashboard_accounts()` order: `{"account": name, "balance": rounded(sums.get(name, 0))}`. `total = rounded(sum_decimal(row["balance"] for row in rows))`. Return `{"accounts": rows, "total": total, "as_of": as_of}`.

Client shape:
- `frontend/src/utils/dashboard.ts`: add `AccountBalance` (`account`, `balance`) and `CashBalances` (`accounts`, `total`, `as_of`) interfaces, and `getCashBalances(): Promise<CashBalances>` calling `call('frappe_books.reports.dashboard.get_cash_balances')`, shaped like `getInvoiceSummary`.
- `frontend/src/pages/Dashboard/AccountBalances.vue`, ported from develop's file at `4896007a`:
  - Extends `DashboardChartBase`, wraps itself in `cardClass`, and is never given `period`. A component comment says the balances are as of the server's today, so the inherited `period` is left alone.
  - `FrappeChartContainer` (`ChartContainer` from `frappe-ui/charts`, present in 1.0.0) with `title` "Account balances", `subtitle` from a computed (`as_of` set → `t\`As of ${fyo.format(asOf, 'Date')}\``, else `t\`As of today\``), `:loading="!isLoaded"`, `:error`, `:empty="!accounts.length"`.
  - Slots: `#loading` three `h-4 animate-pulse rounded bg-surface-gray-2` bars; `#empty` the copy in `text-p-sm text-ink-gray-5`; `#error` `<ChartLoadError @retry="loadData" />`.
  - Table: an `h-full overflow-y-auto` wrapper around `<table class="w-full border-separate border-spacing-0 text-p-sm">`; `thead` (Account, Balance) cells `sticky top-0 bg-surface-base`, `tfoot` (Total) cells `sticky bottom-0 bg-surface-base`. The name cell is `w-full max-w-0` with a `block truncate` link; amounts are `whitespace-nowrap text-end tabular-nums` (logical, RTL safe).
  - Each name is a `router-link` to `{ path: '/report/GeneralLedger', query: { account: row.account, toDate: asOf } }`, with `asOf` passed unchanged (the server's `YYYY-MM-DD` string). With `toDate` set and no `fromDate`, `GeneralLedger.setDefaultFilters` skips the fiscal year default, so the ledger runs from the first entry.
  - Amounts: `fyo.format(value, 'Currency')` only; `amountClass(value)` returns green, red or gray by sign.
  - Overrides `loadData` with a `loadId` counter: each call takes `++this.loadId` and awaits `getCashBalances()`. If its id is no longer the latest, it returns and writes nothing (no `console.error` either). Otherwise on success it sets `error = null`, `accounts`, `total`, `asOf`, `isLoaded = true`; on failure it sets `error` and logs. `isLoaded` is never reset, so a reload keeps the old rows on screen until it settles.
  - Translated strings, all through the `t` tag: `Account balances`, `As of ${date}`, `As of today`, `Account`, `Balance`, `Total`, `No cash or bank accounts`. `ChartLoadError` keeps its own strings.
- `Dashboard.vue`:
  - Add `accounts: fyo.can(ModelNameEnum.Account, 'read')` to `canRead`.
  - After the closing `</template>` of the `v-if="canRead.ledger"` block, add `<template v-if="canRead.ledger && canRead.accounts">` (feature 3 widens this to `|| canRead.sales`) holding the `max-md:hidden` divider and `<div class="grid gap-4 md:gap-8 lg:grid-cols-2">`. Inside: `<AccountBalances v-if="canRead.ledger && canRead.accounts" class="h-72 min-w-0 md:h-80" />`, with a one line comment that it takes no `period` because it is as of today. Best sellers (scope feature 3) adds the second column later.

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| get_cash_balances | which accounts are listed | `_dashboard_accounts()`: Books Account `account_type in (Cash, Bank)`, `is_group = 0`, through `get_list` (feature 4 later: the settings list, falling back to this) |
| get_cash_balances | row order | Books Account `lft` |
| get_cash_balances | `account` (link key and label) | Books Account `name`, which equals `account_name` on v16 |
| get_cash_balances | the cut off day and `as_of` | `frappe.utils.getdate()` (site timezone, as `get_period_dates`), returned so the client never computes a date |
| get_cash_balances | `balance` | `SUM(debit) - SUM(credit)` of Books Ledger Entry, `reverted = 0`, `posting_date <= as_of`, `rounded`, `0` when no entries |
| get_cash_balances | `total` | `sum_decimal` of the rounded row balances, then `rounded` |
| AccountBalances.vue | subtitle date | `as_of` from the response, `fyo.format(as_of, 'Date')` |
| AccountBalances.vue | formatted amounts and symbol | `fyo.format(value, 'Currency')` (base currency from SystemSettings) |
| AccountBalances.vue | amount color | sign of the server rounded value: `> 0` green-5, `< 0` red-6, `0` gray-8 |
| AccountBalances.vue | row link | `{ path: '/report/GeneralLedger', query: { account, toDate: as_of } }`, read by `Report.vue` `getRouteFilters` |
| AccountBalances.vue | which load may write | the component's `loadId` counter |
| Dashboard.vue | whether the row shows | the card's own gate for now; `\|\| canRead.sales` from feature 3 |
| Dashboard.vue | whether the card shows | `fyo.can(ModelNameEnum.AccountingLedgerEntry, 'read') && fyo.can(ModelNameEnum.Account, 'read')` |

**Key invariants**:
- `total` equals the sum of the returned row `balance` values, exactly.
- Only leaf accounts are listed, so no amount is counted twice through a parent.
- No entry with `posting_date > as_of` or `reverted = 1` affects any figure.
- The response never depends on the period selector (the method takes no arguments).
- No raw SQL and no `ignore_permissions`: both reads are `frappe.get_list` with dict fields.

**Security model**:
Read only. Only Books Manager and System Manager hold read on Books Ledger Entry and Books Account today, so only they see the card or get data. The server checks ledger read first, and `get_list` applies the caller's Account and ledger rights, including any user permission rules. The client gate mirrors both reads so no role is shown a card that would 403. Balances are business sensitive, not regulated data: no compliance scope, and no audit log (nothing is written).

**Configuration required**: none.

**Critical test scenarios**:
- Happy path (Python, `frappe_books/tests/test_dashboard.py`, new `IntegrationTestCashBalances`; `IntegrationTestAccountBalances` already exists and tests `get_account_balances`): with `make_account` create two Cash or Bank leaves, a group Bank account and an Expense account, post with `_post` and call under `self.freeze_time(TODAY)`. The seeded chart has its own Cash and Bank leaves, so assert on the created accounts (present, relative `lft` order, balances; group and expense absent), and that `total` equals the sum of all returned rows. Verifies **AC-1**, **AC-4**.
- Cut off (Python): an entry dated after `TODAY` and a reverted pair change nothing; `as_of` equals `TODAY`. Verifies **AC-2**, **AC-3**.
- Zero and negative (Python): an account with no entries returns `0`; an overdrawn bank returns a negative balance that lowers the Total. Verifies **AC-5**, **AC-6**.
- Permission (Python, `test_permissions.py`): add `get_cash_balances` to `test_books_user_gets_invoice_totals_but_no_ledger_totals`. Add a `CASHIER` user with the Books Cashier role to `setUpClass` (only Books User, Manager and System Manager users exist today) and assert it gets `frappe.PermissionError` too; a Books Manager succeeds. Verifies **AC-8**.
- UI (Playwright, new `frontend/tests/ui/dashboard-account-balances.spec.ts`): signed in as a Books Manager the card renders (this also proves `ModelNameEnum.Account` resolves to Books Account for `fyo.can`); it shows the dated subtitle, rows and Total; positive and negative amounts carry their ink classes, and a routed negative balance renders as the exact string `fyo.format` gives; changing the period sends no `get_cash_balances` request; clicking a row lands on the General Ledger with the account and to date set, and its closing balance equals the row. Verifies **AC-3**, **AC-6**, **AC-7**, **AC-2**.
- UI states (Playwright, routed responses): an empty list shows the empty copy; a 500 shows `ChartLoadError` and Try again recovers; 30 rows scroll with header and Total visible; a slow first response that resolves after a faster retry does not overwrite it. Verifies **AC-9**, **AC-10**, **AC-12**.
- UI layout (Playwright, `mobile-dashboard.spec.ts` plus desktop): add a `page.route` mock for `get_cash_balances` beside the existing `get_cashflow` and `get_top_expenses` mocks; on a phone the card is full width with its own border, on desktop it sits in the left half; dark mode uses no fixed colors. Verifies **AC-11**.

## Build plan

Tracer Bullet: one thin thread from the server to the screen first, then thicken it with states, links and tests. Best sellers starts only after this card works end to end.

1. Add `get_cash_balances` (ledger permission check first) and `_dashboard_accounts` to `frappe_books/reports/dashboard.py`, importing `sum_decimal`. Add the happy path, cut off and permission tests. Satisfies **AC-1**, **AC-2**, **AC-4**, **AC-8**.
2. Add `getCashBalances` and its interfaces to `frontend/src/utils/dashboard.ts`, a minimal `AccountBalances.vue` (title, dated subtitle, rows, Total), and the new shared row in `Dashboard.vue` with the `canRead.accounts` gate and no `period` prop. Mock it in `mobile-dashboard.spec.ts`. The thread now works end to end in the browser. Satisfies **AC-1**, **AC-3**, **AC-4**, **AC-8**, **AC-11**, **AC-12**.
3. Add the zero and negative Python tests. Satisfies **AC-5**, **AC-6**.
4. Add the amount colors, the General Ledger links, the scrolling wrapper with sticky header and Total, the loading, empty and error slots, and the `loadId` guard. Satisfies **AC-6**, **AC-7**, **AC-9**, **AC-10**, **AC-12**.
5. Polish the layout: left half on `lg`, phone card styling, RTL safe alignment, a dark mode check. Satisfies **AC-11**.
6. Add the Playwright tests (new desktop spec and the mobile dashboard spec) for content, colors, no reload on period change, the link, the states, the overlapping load and the layout. Satisfies **AC-2**, **AC-3**, **AC-6**, **AC-7**, **AC-9**, **AC-10**, **AC-11**, **AC-12**.

## Consequences

**Positive**:
- Cash on hand is on the dashboard with one grouped query, and the account rule has one seam for feature 4.
- No schema change, so nothing to migrate.
- Both reads follow the v16 reports rule (`get_list`, no bypass), so a future per user account restriction hides rows instead of leaking them.

**Negative / tradeoffs**:
- Two places compute account balances (`dashboard.get_cash_balances` and `financial_statements.get_account_balances`). Both must keep "balance" as debit minus credit for asset accounts.
- The card overrides the base `loadData` to add the stale load guard, so a later fix to the base's error handling must be copied into the card.
- Extending `BaseDashboardChart` without `period` relies on nobody passing `:period` to the card; the comment in `Dashboard.vue` guards that.
- The response shape drops develop's `account_name`, so feature 4's port and develop's tests need that field removed rather than copied.
- Dozens of accounts scroll inside a fixed height card until feature 4 lets users trim the list.
- If per user permissions ever hide an account, it drops from the rows and the Total, so the Total is the cash the user can see, not all cash.

**Neutral**:
- The new row's right column stays empty until Best sellers is built.
- A dashboard left open past midnight keeps its dated subtitle, so the stale day is visible rather than claimed as today.
- `frontend/node_modules` currently holds frappe-ui 1.0.2 while `yarn.lock` pins 1.0.0. `ChartContainer` and its `title`, `subtitle`, `loading`, `error`, `empty` props were checked against the 1.0.0 package, so the build is safe on either.

## Follow-up

- [ ] Feature 4 (choose dashboard accounts) replaces `_dashboard_accounts()` and keeps the Cash and Bank fallback.
- [ ] Feature 3 (best sellers) owns the right column of the new row and widens the row gate to `|| canRead.sales`; per the scope, it moves to the left half when the user can read sales but not the ledger.
- [ ] Check whether `frappe.get_list` on v16 applies a default page length when called from Python. If it does, the existing `get_top_expenses` and `_monthly_totals` (no `limit_page_length=0`) could silently cut rows. The new method sets `limit_page_length=0` either way.
- [ ] Run `yarn install --check-files` in `frontend/` so `node_modules` matches the locked frappe-ui 1.0.0 before building.
