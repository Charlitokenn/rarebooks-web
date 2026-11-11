# 0002. Best sellers chart: rationale

The decision record behind [index.md](index.md).

## Context

The dashboard tells you how much you sold (the paid and unpaid sales cards) but not what you sold. Develop shipped a Best sellers donut (its spec 0002, final shape top five with no Others slice). The scope asks for a hand port to version-16, because develop is on Frappe 17 with three databases and renamed invoice fields.

Forces that shape the port:
- **The data is split across two tables.** The sold amount and discount are on the Books Sales Invoice Item row, in the invoice's currency. The date, the submitted status, the exchange rate and the discount mode are on the Books Sales Invoice. The ledger cannot answer this: it posts by income account, not by item.
- **v16 names.** The invoice `date` is a Datetime (bounded with `reports/filters.py` `datetime_conditions`), the rate is `exchange_rate`, and the row's item link is `item`. Books Item is named by prompt, so its `name` is the item's own name and is unique.
- **v16 row amounts mean something else.** `amount` is rate × quantity before the row discount (`accounting/invoice.py` `_calculate_row`); develop's `amount` was after it. Every v16 discount is per row (`row_discount`), even with `discount_after_tax`.
- **v16 reports rule** (`frappe_books/AGENTS.md`): reports read through `frappe.get_list` with dict aggregate fields so the caller's rights apply. No raw SQL, no `ignore_permissions`.
- **v16 roles.** Books User, Books Manager and Books Cashier all read Books Sales Invoice; only managers read the ledger. So this card is the one most dashboard users can see, and must sit left when Account balances is hidden.
- **MariaDB only.** `SUM` returns `Decimal`; amounts go through `as_decimal`, `rounded` and `sum_decimal`.
- **frappe-ui 1.0.0** is pinned (the local `node_modules` holds 1.0.2).

### What was checked on the v16 bench (Frappe 16.55.2, read only probes)

- `frappe.get_list(..., run=False, order_by=None, limit_page_length=0)` returns the built query with no `LIMIT` and no `ORDER BY`, and works as an `IN (...)` subquery inside a `frappe.qb` join on MariaDB.
- One `get_list` on Books Sales Invoice with table qualified child fields (`` `tabBooks Sales Invoice Item`.amount ``), `SUM` dict fields and a `group_by` over a child and parent column builds a `LEFT JOIN ... ON parent = name AND parenttype = 'Books Sales Invoice'` and runs.
- Refused by v16's field validator: the short `items.amount` form inside `SUM`, and `SUM` over a nested `MUL` expression.
- The probes ran as Administrator, so they do not prove the child rows are readable for a Books User or Cashier; Build plan task 1 tests that with data.
- frappe-ui 1.0.0 `DonutChart` has `title`, `subtitle`, `loading`, `error`, `dir`, `data`, `category`, `value`, `centerLabel`, `format` and the `center`, `empty`, `error` slots, and still sorts slices biggest first.

## Options considered

### Option 1: One `get_list`, grouped by item, rate and discount mode (chosen)

One `frappe.get_list` on Books Sales Invoice with table qualified item fields, summing `amount`, `item_discounted_total` and `item_taxed_total` per item, exchange rate and discount mode; Python works out the net, multiplies by the rate and ranks.

**Pros**:
- Fits the v16 reports rule exactly: one `get_list`, the caller's read rights and user permissions apply.
- One query, whatever the number of invoices.

**Cons**:
- The multiply cannot run in SQL on v16 (`SUM` over `MUL` is refused), so the result has one row per distinct rate, and Python finishes the sum.
- Relies on the table qualified field form in v16's parser, and on child rows being readable for non managers (untested until the build).

### Option 2: Unrun `get_list` subquery inside a `frappe.qb` join (develop's final shape)

An unrun `get_list` of the period's invoice names as an `IN` subquery, joined in `frappe.qb` to the item rows, with `SUM(net × COALESCE(NULLIF(rate, 0), 1))` per item.

**Pros**:
- Probed on v16; the database does the whole sum, one row per item.
- Invoice read rights still apply through the subquery, and the child rows are read without a child permission check.

**Cons**:
- A second query style (`frappe.qb`) in reports, which the v16 rule does not use.
- The discount mode logic must be written as a SQL `CASE` in `frappe.qb`.

### Option 3: `has_permission` once, then a plain `frappe.qb` join (develop's first shape)

**Pros**:
- Simplest query.

**Cons**:
- Skips row level read rights, breaking the v16 reports rule; a future per user restriction would leak sales.

## Rationale

The v16 reports rule exists so a future per user restriction hides data instead of leaking it, and this card is the one Books Users and Cashiers see, so the read must be permission aware: that rules out Option 3. Between the two permission aware shapes, Option 1 stays inside the one query style the v16 reports already use, at the cost of finishing the sum in Python over a few rows per item. Option 2 is kept as the named fallback, already probed, so the build can switch without a new decision if task 1 shows the child rows are not readable for every sales role.

Calls made in the design conversation (the engineer's picks):
- **Query**: Option 1. Runner up: Option 2.
- **Measure**: after the row discount, before tax, in base currency, which is what the item earned and what develop measured. Runner up: the raw row `amount` (simpler, one `SUM`, but overstates discounted items).
- **Who sees it**: anyone with sales invoice read, cashiers included, since they can already open every invoice. Runner up: managers only.
- **Totals**: develop's final shape, subtitle over every item and centre "Top N" over the visible slices. Runner up: every figure covers only the five.
- **Click**: nothing, like Top expenses. Runner up: open the sales invoice list for that item, which needs its own child field filter design.

Calls made while writing, each with its runner up:
- **Label from the row's `item`**, with no Books Item lookup, since v16 item names are the unique names. Runner up: read `item_code` from Books Item, which needs Item read and develop's duplicate label rule.
- **Group by `discount_after_tax` too** and compute the net per group with the same formula as `row_discount`. Runner up: always use `item_discounted_total`, which includes tax on `discount_after_tax` invoices.
- **Round each item once, before the zero or below filter**, so dust left after a return never becomes a slice. Runner up: filter the raw sum, which can show a 0.00 slice.
- **Tie break on `item`**, for a stable order between loads. Runner up: database order.
- **A new `getBestSellers` helper** shaped like `getInvoiceSummary`, since the return shape differs from the other period charts. Runner up: widen `getDashboardData`'s union.
- **The permission test asserts figures for Books User and Cashier**, not only that no error is thrown, because a child permission gap would silently return empty rows. Runner up: assert no error only.
