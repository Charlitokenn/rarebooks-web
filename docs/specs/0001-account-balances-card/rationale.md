# 0001. Account balances card: rationale

The decision record behind [index.md](index.md).

## Context

The version-16 dashboard shows flows over a period (cashflow, profit, expenses, invoices) but not the stock of money: how much is in each cash drawer and bank account right now. Develop already shipped this card (its spec 0001, then a fix in `4896007a`). The scope asks for a hand port, because develop is on Frappe 17 with three databases and renamed ledger fields.

Forces that shape the port:
- **v16 names.** The ledger is `Books Ledger Entry` and reversals are filtered with `reverted = 0` (a reversal marks the old row and its mirror reverted), not `is_cancelled`. The client model is `ModelNameEnum.AccountingLedgerEntry`.
- **v16 accounts are named by `account_name`** (`autoname: field:account_name`), so an account's `name` and label are the same value.
- **v16 roles.** Only Books Manager and System Manager can read Books Ledger Entry *and* Books Account. Books User and the new Books Cashier read neither.
- **v16 reports rule** (`frappe_books/AGENTS.md`): reports read through `frappe.get_list` so the caller's rights apply, with no raw SQL and no `ignore_permissions`.
- **MariaDB only.** `Sum` comes back as a Decimal; amounts go through `as_decimal`, `rounded` and `sum_decimal`.
- **frappe-ui 1.0.0** is pinned. Develop's card draws its header with `ChartContainer`, which had to exist in 1.0.0.
- **Features 3 and 4 follow.** Best sellers shares the new row (and must sit left for a sales only reader), and feature 4 swaps which accounts are listed.

## Options considered

### Option 1: Port develop's original spec 0001 as written

Same server method and card, with "As of today" as fixed text, `get_all` on accounts, and both `account` and `account_name` in each row.

**Pros**:
- Smallest diff from develop's spec, so its review history applies directly.

**Cons**:
- Carries two bugs develop found after verify: a card left open past midnight claims "today" for yesterday's figures, and an older reload can overwrite a newer one.
- `get_all` breaks the v16 reports rule, and its reason (roles with ledger but not account read) does not exist on v16.

### Option 2: Port develop's final shape, adapted to v16 rules (chosen)

Develop's code at `4896007a` (dated subtitle, stale load guard), with `get_list` on both doctypes, a client gate on both reads, a row shape of `account` and `balance` only, and the shared row built now.

**Pros**:
- Starts from the version develop verified and fixed.
- Follows the v16 permission rule and its real role model.
- No redundant field that looks like it could differ from the name.

**Cons**:
- Diverges from develop in three places (`get_list`, the gate, the row shape), so later develop fixes need a careful port, not a copy.

### Option 3: Reuse `financial_statements.get_account_balances`

Call the existing whitelisted helper and filter Cash and Bank in the client.

**Pros**:
- No new server code.

**Cons**:
- It returns every account and puts the account rule in the client, against "rules in Python", and leaves feature 4 nowhere to plug in.
- It has no cut off at today, so future dated entries would count.

## Rationale

Develop's final code is the best tested starting point: its two post verify fixes are real bugs, and porting the older text would bring them back. The v16 adaptations follow from forces that differ from develop. On v16 every ledger reader can also read accounts, so `get_all`'s only benefit is gone and only its cost (skipping the caller's rights, against the reports rule) remains. Because `get_list` makes Account read a real requirement, the client gate checks it too, so no custom role sees a card that would 403. With `name` equal to `account_name`, a second label field only invites someone to think they can differ. Building the shared row now settles the layout once, since Best sellers is the next slice. Its gate starts as the card's own and is widened by feature 3, so no reader sees an empty row in between.

Calls made while writing, each with its runner up:
- **The card extends `BaseDashboardChart` and overrides `loadData`** to add the `loadId` guard, as develop did. Runner up: putting the guard in the base for every card, which is a wider change than this feature.
- **The total is the sum of the rounded rows** (`sum_decimal`, then `rounded`), so the Total always equals what the rows add up to on screen. Runner up: rounding the raw sum, which can differ by a cent.
- **Balance is debit minus credit** for Cash and Bank (asset accounts), the same as `DEBIT_MINUS_CREDIT`, so an overdraft comes out negative.
- **`_dashboard_accounts()` returns names only** (`pluck="name"`), since the name is the label. Runner up: rows with fields, which feature 4 may want; it can widen the return then.
