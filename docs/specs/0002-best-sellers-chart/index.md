# 0002. Best sellers chart on the version-16 dashboard

**Date**: 2026-11-10
**Status**: In Progress

Decision history: [rationale.md](rationale.md).

## Summary

The version-16 dashboard gets a donut chart, built like Top expenses, that ranks the five items that earned the most in the selected period, with the total sales of every item in its subtitle. It is a hand port of develop's spec 0002 in its final top five shape (no Others slice), rewritten for v16: the invoice `date` is a Datetime, the rate is `exchange_rate`, and the label is the item's own name. One new server method in `dashboard.py` reads the sales through a single `frappe.get_list` (so the caller's read rights apply), and a small Vue card shows them in the right half of the Account balances row. No new DocType, field or patch.

## Requirements

**User stories**:
- As a Books user, manager or cashier who can read sales invoices, I want to see which items earned the most in the period I picked, so I know what sells.
- As that user, I want the total sales of every item next to the chart, so I can see the top five next to my total sales.

**Acceptance criteria**:
- **AC-1**: The chart shows up to five items, ranked by sales amount in the selected period, largest first. An item's sales amount is the sum, over its Books Sales Invoice Item rows on counted invoices, of the row's net amount (after the row discount, before tax) times the invoice's `exchange_rate` (an empty or zero rate counts as `1`), so it is in base currency (the company's own currency). The row's net amount is `amount − row discount`, with the row discount worked out as `accounting/invoice.py` `row_discount` does. Each slice is labelled with the row's `item`, the Books Item `name` (v16 names items by prompt, so the name is the item's own name and is unique).
- **AC-2**: An invoice counts when `docstatus = 1` and its `date` (a Datetime) falls on or after the period's first day and before the day after its last day, so a sale made late on the period's last day counts. Draft and cancelled invoices never count.
- **AC-3**: Returns count on their own `date` and need no special handling: their quantities, amounts and discounts are already negative, so they lower that period's figure for the item.
- **AC-4**: Only the top five items are drawn. Items past the fifth are not shown as a slice or in the legend (there is no Others slice), but they still count in the total (AC-6). The chart draws the five in frappe-ui's own order, biggest first.
- **AC-5**: An item whose rounded sales amount for the period is zero or below is left out entirely: it is neither a slice nor part of the total.
- **AC-6**: The subtitle reads "Total sales: <amount>", where the amount is the server `total`: the sum of every item's rounded amount that is above zero, the five shown and every item past them. The centre shows the sum of the visible slices with the label "Top N", where N is the number of items returned ("Top 5", or "Top 3" when only three sold), and each legend percent is that item's share of the visible slices. Hiding legend entries recomputes the centre and the percents over the slices still shown (frappe-ui's own behaviour). So when more than five items sold, the subtitle is larger than the centre.
- **AC-7**: The chart follows the period selector: changing the period reloads it for the new period, the same as Top expenses.
- **AC-8**: The card renders only for users who can read Books Sales Invoice (`canRead.sales`): Books User, Books Manager, Books Cashier and System Manager. On the server, `get_best_sellers` throws `frappe.PermissionError` for a user without that read, and reads through `frappe.get_list`, so a Books User and a Books Cashier get the same figures as a manager.
- **AC-9**: The card has the same legend, loading, empty and error states as Top expenses: while loading the donut's loading state shows, with no sales it shows "No sales in this period", and when the request fails `ChartLoadError` shows and Try again reloads it.
- **AC-10**: The card sits in the right column of the Account balances row (`lg:grid-cols-2`, `md:h-80`). The row (and its divider) shows when `(canRead.ledger && canRead.accounts) || canRead.sales`. When Account balances is hidden (a user who can read sales but not the ledger), Best sellers takes the left column instead. On phones it stacks full width on its own bordered card (`cardClass`) at `h-96`, like Top expenses. It reads correctly in dark mode through frappe-ui tokens only.
- **AC-11**: Clicking a slice or a legend entry does nothing beyond the chart's own tooltip and legend toggle, the same as Top expenses.

## Decision

**Chosen option**: Option 1: one permission aware `frappe.get_list`, grouped by item, exchange rate and discount mode, finished in Python.

Add a whitelisted `get_best_sellers(period)` to `frappe_books/reports/dashboard.py` that checks sales invoice read, reads the period's item sums with one `frappe.get_list` on Books Sales Invoice (table qualified child fields), converts and ranks them in Python with `Decimal`, and returns `{items, total}`; render it in a `BestSellers.vue` donut that copies `Expenses.vue`.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `tailwindcss` (`hairyf/skills`, `.agents/skills/tailwindcss/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:
No new DocType, field, index or patch. Read only use of:

| DocType | Fields read | Role |
|---|---|---|
| Books Sales Invoice | `name` (PK), `docstatus`, `date` (Datetime, required), `exchange_rate` (Float, empty or `0` treated as `1`), `discount_after_tax` (Check) | Picks the period's submitted invoices (returns included), converts to base currency, and says how the row discount was taken |
| Books Sales Invoice Item | `parent` (FK → Books Sales Invoice.name), `parenttype`, `item` (Link → Books Item.name, required), `amount` (rate × quantity, before discount), `item_discounted_total`, `item_taxed_total` | The sold amount per row and its discount; return rows carry negative values |

Relationships: Books Sales Invoice 1:N Books Sales Invoice Item; Books Item 1:N Books Sales Invoice Item. Books Item itself is not read: its `name` is already on each row as `item`. Books Sales Invoice has one child table of Books Sales Invoice Item (`items`), so `parenttype` alone picks the right rows.

**State transitions**: none (read only). Only `docstatus = 1` invoices count; a cancel (`docstatus = 2`) drops an invoice out of every figure on the next load.

**API surface**:
| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `frappe_books.reports.dashboard.get_best_sellers` | POST via `call()` | `period: str` (req, `This Year` · `This Quarter` · `This Month` · `YTD`) | `items: [{item: str, amount: number}]` (at most 5, largest first), `total: number` (every item above zero, not only the five) | logged in, Books Sales Invoice read | `frappe.PermissionError` (403) without sales read; `ValidationError` for an unknown period (from `get_period_dates`) |

Server shape (in `dashboard.py`, after `get_top_expenses`):
- Constants: `SALES_INVOICE = "Books Sales Invoice"`, `SALES_ITEM = "tabBooks Sales Invoice Item"` and `TOP_COUNT = 5`. Give `SALES_ITEM` a one line comment: it is the database table name (with the `tab` prefix), not a DocType name, because `get_list` needs it to qualify child fields. Leave `get_top_expenses` as it is (this port keeps its diff small).
- `get_best_sellers(period: str) -> dict`, whitelisted and type annotated, docstring "Return the five items with the most sales in the period, and the total sales of every item."
- First line: `frappe.has_permission(SALES_INVOICE, "read", throw=True)`. Then `from_date, to_date = get_period_dates(period)`.
- `_item_sales(from_date, to_date) -> dict[str, Decimal]`: one `frappe.get_list` call (the probed shape, plus `discount_after_tax` and the two extra sums in the same form):
  ```python
  rows = frappe.get_list(
  	SALES_INVOICE,
  	filters=[["docstatus", "=", 1], *datetime_conditions("date", from_date, to_date)],
  	fields=[
  		f"`{SALES_ITEM}`.item",
  		"exchange_rate",
  		"discount_after_tax",
  		{"SUM": f"`{SALES_ITEM}`.amount", "as": "amount"},
  		{"SUM": f"`{SALES_ITEM}`.item_discounted_total", "as": "discounted"},
  		{"SUM": f"`{SALES_ITEM}`.item_taxed_total", "as": "taxed"},
  	],
  	group_by=f"`{SALES_ITEM}`.item, exchange_rate, discount_after_tax",
  	order_by=None,
  	limit_page_length=0,
  )
  ```
  - Frappe 16 builds this as a `LEFT JOIN` of the item rows on `parent` and `parenttype` (probed on v16.55.2). The bare `items.amount` form and a `SUM` over a nested `MUL` are both refused by v16's field validator, which is why the fields are table qualified and the multiply happens in Python.
  - In Python, for each row with an `item` (skip `None`, from an invoice with no rows): `net = amount − (taxed − discounted)` when `discount_after_tax`, else `net = discounted`; `rate = as_decimal(row.exchange_rate) or 1` (`as_decimal` turns `None` into `Decimal(0)`, so empty and `0` both fall to `1`, as intended); add `as_decimal(net) * rate` to that item's running `Decimal` sum. Never sort or compare the raw database values. Free item rows and zero amount rows add `0` and need no special case (AC-5 drops an item left at zero).
  - Returns need no code: a credit note's quantities are negative (`returns.set_quantity_signs`), so `_calculate_row` makes its `amount`, discount and totals negative too, and `map_return` copies the original invoice's `exchange_rate` (it is not in `field_no_map`, and `_populate_currency` keeps an existing rate). So a return made in a later period subtracts at the original rate.
- Rank: pass each item's sum through `rounded(...)` once (base currency unit), keep items with a rounded amount `> 0`, sort by amount descending then `item` ascending (plain string order, a stable tie break), take the first `TOP_COUNT`.
- Each slice: `{"item": item, "amount": rounded_amount}`. No Others row, no label lookup.
- `total = rounded(sum_decimal(amount for every kept item))`: all items above zero, not only the five. Return `{"items": items, "total": total}`. The `Decimal` values reach the client as JSON numbers through Frappe's response encoder, as in `get_top_expenses`.
- **Fallback, only if the build's permission test (Build plan task 1) fails for any one role** (Books User or Cashier gets an error, empty items, or figures that differ from the Manager's): switch the whole of `_item_sales`, for every role, to Option 2 in [rationale.md](rationale.md) (an unrun `get_list` of invoice names as an `IN` subquery inside a `frappe.qb` join, also probed on v16), keep everything else, and note the switch in this spec. Do not fall back to `ignore_permissions` or raw SQL.

Client shape:
- `frontend/src/utils/dashboard.ts`: add `BestSeller` (`item: string`, `amount: number`) and `BestSellers` (`items: BestSeller[]`, `total: number`) interfaces, and `getBestSellers(period: PeriodKey): Promise<BestSellers>` calling `call<BestSellers>('frappe_books.reports.dashboard.get_best_sellers', { period })`, shaped like `getInvoiceSummary`. Leave `getDashboardData`'s method union as is.
- `frontend/src/pages/Dashboard/BestSellers.vue`: a copy of `Expenses.vue` with these differences only: name `BestSellers`; title `t\`Best sellers\``; data `items: [] as BestSeller[]` and `total: 0` (replacing `expenses`); `:data="items"`, `category="item"`, `value="amount"`; the computed `totalSpending` becomes `totalSales`, returning `t\`Total sales: ${fyo.format(total, 'Currency')}\`` (the server `total`, not a client sum) when `items.length`, else `undefined`; `:center-label="t\`Top ${items.length}\`"` (translators see `Top {0}`; N is the count returned, so the label stays as is when a legend entry is hidden, while the centre value and percents recompute); empty copy `t\`No sales in this period\``; `setData` awaits `getBestSellers(this.period)` and stores `items` and `total`. Keep the `#center` slot and its frappe-ui#1259 comment (compact currency, percent), `phoneChartListeners`, `cardClass`, the `dir` rule and `#error` with `ChartLoadError @retry="loadData"`. No click handler.
- `Dashboard.vue`: change the row gate to `<template v-if="(canRead.ledger && canRead.accounts) || canRead.sales">` and drop the "Best sellers will share this row" comment. Keep the inner `v-if="canRead.ledger && canRead.accounts"` on `AccountBalances`: once the row also opens for sales readers, it is what keeps a sales only user from getting that card. After `AccountBalances`, add `<BestSellers v-if="canRead.sales" class="h-96 min-w-0 md:h-80" :period="period" />`. Grid auto placement puts it in the left column when `AccountBalances` is not rendered (AC-10); no extra class. Register the component.

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| get_best_sellers | period bounds | `get_period_dates(period)` (site timezone, ends today), the same as every period card |
| get_best_sellers | which invoices count | `docstatus = 1` and `datetime_conditions("date", from_date, to_date)` (`date >= from`, `date < to + 1 day`); returns included by the same rule |
| get_best_sellers | `item` (slice key and label) | Books Sales Invoice Item `item` (the Books Item `name`) |
| get_best_sellers | row net amount | `item_discounted_total` when `discount_after_tax = 0`; `amount − (item_taxed_total − item_discounted_total)` when it is `1` (`row_discount` in `accounting/invoice.py`), summed per group in SQL |
| get_best_sellers | base currency amount per item | net × `exchange_rate` (empty or `0` → `1`), summed as `Decimal` in Python, then `accounting.money.rounded` (company currency unit) |
| get_best_sellers | which items are slices | rounded amount `> 0`, sorted by amount desc then `item`, first `TOP_COUNT` (5) |
| get_best_sellers | `total` | `rounded(sum_decimal(...))` of every item's rounded amount that is `> 0` in the period |
| BestSellers.vue | formatted amounts, currency symbol | `fyo.format(value, 'Currency')` and `compactCurrency` (base currency from SystemSettings) |
| BestSellers.vue | subtitle total | the server `total` |
| BestSellers.vue | centre value and slice percent | frappe-ui `DonutChart` from the visible slice values (as in `Expenses.vue`); the label is `t\`Top ${items.length}\`` |
| BestSellers.vue | loading and error state | `isLoaded` and `error` from `BaseDashboardChart.loadData` |
| BestSellers.vue | period | the `period` prop from `Dashboard.vue`, via `BaseDashboardChart`'s watch |
| Dashboard.vue | whether the card shows | `fyo.can(ModelNameEnum.SalesInvoice, 'read')` (`canRead.sales`, already defined) |
| Dashboard.vue | whether the row shows | `(canRead.ledger && canRead.accounts) \|\| canRead.sales` |

**Key invariants**:
- `total` is at least the sum of the returned slice `amount` values, and equals it exactly when five or fewer items sold.
- Every returned `amount` is greater than zero, and `total > 0` exactly when `items` is not empty.
- At most five slices, largest first, each a distinct `item`. No Others slice.
- No draft or cancelled invoice affects any figure; a return counts in the period of its own `date`.
- Amounts are in base currency, after the row discount and before tax.
- No raw SQL and no `ignore_permissions`: the sales read is one `frappe.get_list`.

**Security model**:
Read only. Any logged in user with read on Books Sales Invoice may call it (Books User, Books Manager, Books Cashier, System Manager on v16); the server checks this first with `frappe.has_permission(SALES_INVOICE, "read", throw=True)`, and `get_list` then applies the caller's invoice read rights, including any user permission rules, so a future per user restriction hides invoices instead of leaking them. Item names need no Books Item read: they come from the invoice rows the user can already open. The client hides the card for anyone without sales read, so they never trigger the 403. Sales figures are business sensitive but not regulated data: no compliance scope, and no audit log (nothing is written).

**Configuration required**: none.

**Critical test scenarios**:
- Test fixture: add `insert_sales_invoice(date, rows, **values)` to `frappe_books/tests/accounting.py` (the shared helper module), so `test_dashboard.py` and `test_permissions.py` both import it. `rows` is a list of dicts with `item` and `amount`, plus optional `discounted` and `taxed` (both default to `amount`). The helper builds the parent with `name=frappe.generate_hash()`, `docstatus=1`, `exchange_rate=1` and `discount_after_tax=0`, all overridable through `values` (pass `docstatus=0` or `2`, `exchange_rate`, `discount_after_tax`), and writes it with `db_insert()`. `rows` is never passed to `get_doc`. Since `db_insert()` on the parent writes no child rows, the helper then inserts each row as `frappe.get_doc({"doctype": "Books Sales Invoice Item", "name": frappe.generate_hash(), "parent": <the parent name>, "parenttype": "Books Sales Invoice", "parentfield": "items", "idx": n, "item": ..., "amount": ..., "item_discounted_total": ..., "item_taxed_total": ...}).db_insert()`. It returns the parent name. The existing `_invoice` helper stays as it is. Use item names unique to the test (seeded data may hold other sales).
- Happy path (Python, `frappe_books/tests/test_dashboard.py`, new `IntegrationTestBestSellers`): under `self.freeze_time(TODAY)`, insert submitted sales invoices with rows for seven items. Assert the five largest come back in order, the last two are not returned, and `total` equals the sum of all seven. Verifies **AC-1**, **AC-4**, **AC-6**.
- Discount and currency (Python): a row with a discount before tax counts at `item_discounted_total`; a row on a `discount_after_tax` invoice counts at `amount − (taxed − discounted)`; an invoice with `exchange_rate = 2` counts double; one with an empty or `0` rate counts at face value. Verifies **AC-1**.
- Period edge (Python): an invoice dated at `23:30` on the period's last day counts; one at `00:00` the next day and one before the first day do not. Verifies **AC-2**.
- Returns and status (Python): a return in the period lowers its item; a return that takes an item to zero or below drops it from the slices and the total; draft (`docstatus = 0`) and cancelled (`docstatus = 2`) invoices change nothing. Verifies **AC-3**, **AC-5**.
- Ties and few items (Python): equal amounts at fifth and sixth place come back in `item` order and only the first is returned; with three items all three come back and `total` equals their sum; with none, or all at zero or below, the result is `{"items": [], "total": 0}`. Verifies **AC-4**, **AC-9**.
- Permission (Python, `test_permissions.py`, a new test in the existing class, reusing its `setUpClass` users `BOOKS_USER`, `CASHIER` and `MANAGER`): with rows inserted for the period through `insert_sales_invoice`, `get_best_sellers` called as `BOOKS_USER` and as `CASHIER` returns `items` that are not empty and equal the `MANAGER` result, `total` included (this proves `get_list` reads the child rows for those roles, not only that it does not throw). Called as `Guest` (the user with no Books role; a direct call still runs `has_permission`, as `test_reports.py` already does) it raises `frappe.PermissionError`. Verifies **AC-8**.
- UI (Playwright, new `frontend/tests/ui/dashboard-best-sellers.spec.ts`, routed responses): the card shows the title, the "Total sales" subtitle with the server total, the "Top N" centre ("Top 5" with five items, "Top 3" with three), and the legend with the item names and no Others; changing the period sends a new `get_best_sellers` request with the new `period`; an empty response shows "No sales in this period"; a 500 shows `ChartLoadError` whose Try again recovers; clicking a slice does not navigate. Verifies **AC-6**, **AC-7**, **AC-9**, **AC-11**.
- UI layout (Playwright): on desktop the card is in the right half next to Account balances; with ledger read denied (a Books User session, or a mocked `fyo.can`) it is in the left half; on a phone it is full width on its own bordered card. Add a `page.route` mock for `get_best_sellers` to `mobile-dashboard.spec.ts` beside the `get_top_expenses` and `get_cash_balances` mocks, so those tests don't depend on site data. It returns five filled in items and a `total` above their sum, so the phone checks see a real chart, not the empty state. Verifies **AC-8**, **AC-10**.

## Build plan

Tracer Bullet: one thin thread from the server to the screen first, proving the permission aware read for every sales role, then thicken it with the edge rules, states and tests. Account balances (feature 2) should be working end to end before this starts.

1. Add `get_best_sellers` (permission check first), `_item_sales` and the constants to `frappe_books/reports/dashboard.py`. Add `insert_sales_invoice` to `frappe_books/tests/accounting.py`, then the happy path test and the permission test for Books User, Cashier, Manager and Guest. If the permission test fails for any role, apply the fallback in Server shape. Satisfies **AC-1**, **AC-4**, **AC-6**, **AC-8**.
2. Add `getBestSellers` and its interfaces to `frontend/src/utils/dashboard.ts`, a minimal `BestSellers.vue` (copy of `Expenses.vue`) after `AccountBalances` behind `canRead.sales` with `:period`, and widen the row gate in `Dashboard.vue`. Mock it in `mobile-dashboard.spec.ts`. The thread now works end to end in the browser. Satisfies **AC-6**, **AC-7**, **AC-8**, **AC-10**.
3. Add the Python tests for discounts and currency, the period edge, returns, draft and cancelled invoices, the zero or below rule, ties, few items and no sales. Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-9**.
4. Finish the card: empty copy, error state with retry, centre slot and `Top N` label, phone card styling and `h-96`, the left column fallback when Account balances is hidden, a dark mode check. Satisfies **AC-6**, **AC-9**, **AC-10**, **AC-11**.
5. Add `dashboard-best-sellers.spec.ts` (desktop) and the mobile layout checks for content, period reload, states, layout and no navigation on click. Satisfies **AC-6**, **AC-7**, **AC-9**, **AC-10**, **AC-11**.

## Consequences

**Positive**:
- What sells is on the dashboard from one grouped query, with every rule (period, returns, discounts, currency, top five, total) in one Python function.
- The read follows the v16 reports rule (`get_list`, no bypass), so a future per user invoice restriction hides sales instead of leaking them, unlike develop's first shape.
- v16 records every discount per row, so the ranking is exact after discounts; develop's "after tax discount overstates items" caveat does not apply here.
- No schema change, so nothing to migrate and no patch. The card is a near copy of Top expenses.

**Negative / tradeoffs**:
- The card shows two totals once more than five items sold: the subtitle (every item) and the centre (the five, labelled "Top N"). Chosen over an Others slice because frappe-ui 1.0.0 sorts slices biggest first (`donutChartOptions.ts`) and would draw Others first whenever the tail outweighs an item, and its own Others label is not translatable.
- The query groups by item, exchange rate and discount mode, so it returns one row per distinct combination, not per item, and Python finishes the sum. Many distinct rates (a foreign currency business with daily rates) mean more rows, still far fewer than invoice rows.
- The table qualified field strings (`` `tabBooks Sales Invoice Item`.amount ``) are a new `get_list` form in `dashboard.py`, tied to Frappe 16's field parser. A Frappe upgrade that changes it breaks this method first; the Python tests will show it.
- Each item total is rounded once, while `base_grand_total` rounds once per invoice, so on foreign currency invoices the sum of the best sellers can differ from Paid plus Unpaid sales by a cent or so. Accepted: the chart shows shares, not a reconciled figure.
- A return counts in the period of its own date, so a March sale returned in April lowers April. This matches the paid and unpaid sales cards.
- On a `discount_after_tax` invoice, v16 works out the row discount on the total with tax included (`_calculate_row`), so that row's figure is its pre tax amount less a discount that carries a tax share. "After discount, before tax" is exact on every other invoice and close on these. Accepted: it is still the closest per row figure v16 stores.
- On a phone the Account balances card (`h-72`) and Best sellers (`h-96`) stack at different heights, as each matches its own content.
- Books Cashier sees the sales mix on the dashboard, since it reads every sales invoice.

**Neutral**:
- With a single item sold, frappe-ui draws one full ring and no legend, the same as Top expenses.
- Loyalty point redemptions and invoice level charges are not item rows, so they do not affect the ranking.
- An item renamed later shows under its new name for past sales (Frappe updates the link on rename).
- The dashboard ignores `company`, as every other card does (single company).
- Books Sales Invoice `date` has no index, so the query scans the period's invoices; fine at small business volumes.

## Follow-up

- [ ] If the dashboard gets slow on a large site, measure `get_best_sellers` and consider an index on Books Sales Invoice `date` (see `mariadb-query-optimization`).
- [ ] If frappe-ui's `DonutChart` gains an option to keep the data order or a translatable Others label, decide whether to bring back an Others slice here (and fix the same ordering in Top expenses).
- [ ] Run `yarn install --check-files` in `frontend/` so `node_modules` (frappe-ui 1.0.2) matches the locked 1.0.0 before building (carried from spec 0001). The `DonutChart` props and slots used here were checked against the 1.0.0 package.
