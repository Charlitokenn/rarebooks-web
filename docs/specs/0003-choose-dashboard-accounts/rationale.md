# 0003. Choose the accounts the dashboard lists: rationale

The decision record behind [index.md](index.md).

## Context

The Account balances card (spec 0001) lists every leaf Cash and Bank account. A business that watches a petty cash box filed under another account type, a loan, or a credit card has no way to put it on the card, and a business with many bank accounts cannot trim the list. Develop solved this in its spec 0003 by adding a picked list to Accounting Settings. The scope asks for a hand port, because v16's Accounting Settings model and controller differ from develop's.

Forces that shape the port:
- **v16 reports rule** (`frappe_books/AGENTS.md`): reports read through `frappe.get_list` so the caller's rights apply, with no raw SQL and no `ignore_permissions`. Spec 0001 on v16 follows it for both its reads; develop's spec 0003 read the picked rows with `get_all`, which skips permissions.
- **v16 Accounting Settings** already checks its three single account fields with `validate_changed_accounts(self, ACCOUNT_TYPES)`, which relies on `has_value_changed` per field. A table of accounts has no single value to compare, so it needs its own per row check.
- **v16 roles.** Books Manager and System Manager write Accounting Settings; all four Books roles read it. Only Books Manager and System Manager read both Books Ledger Entry and Books Account, so only they see the card today.
- **v16 response shape.** `get_cash_balances` returns `account` and `balance` only (an account's `name` is its `account_name` on v16), so develop's `account_name` does not come across.
- **MariaDB only**, and frappe-ui pinned at 1.0.0. Develop's three database criterion does not apply, and every frappe-ui slot and prop used must exist in 1.0.0.
- **The scope's Done when**: picked accounts show in chart order; a duplicate or a non qualifying pick is refused on save; a pick that later stops qualifying is skipped and does not block saving other settings; the "Choose accounts" button shows only to users who can write Accounting Settings.

If nothing is decided, the card keeps listing only Cash and Bank accounts, and businesses that track cash in other accounts read a misleading total.

## Options considered

### Option 1: Port develop's spec 0003 as written

A child table on Accounting Settings, a per row save check, and `_dashboard_accounts()` reading the picked rows and accounts with `frappe.get_all`, so any ledger reader sees the picks without needing Settings or Account read.

**Pros**:
- Smallest diff from develop's spec, so its review history applies directly.
- A custom role with ledger read but no Settings read still sees its picks.

**Cons**:
- `get_all` breaks the v16 reports rule that spec 0001 on v16 already follows, so one card would read some data with the caller's rights and some without.
- Develop's reason (ledger readers without Account read) does not exist on v16: the v16 card is already gated on Account read.

### Option 2: Port develop's design onto v16, with every read through `get_list` (chosen)

The same child table, save rules, fallback and button, but the picked rows are read with `get_list` and `parent_doctype` after an explicit Settings read check, the picked accounts with `get_list` on Books Account, and the card gate gains Settings read.

**Pros**:
- Follows the v16 reports rule end to end, matching spec 0001.
- No existing role loses anything: all four Books roles read Accounting Settings.
- A deterministic 403 for a caller without Settings read, whatever `get_list` does with a child of a single.

**Cons**:
- A third permission on the card's path, mirrored in the client gate.
- A custom role with ledger and Account read but no Settings read loses the card.

### Option 3: A plain text field of account names on Accounting Settings

One Small Text field holding the picked names, parsed on read.

**Pros**:
- No new doctype, no child table read, no Settings UI change beyond one field.

**Cons**:
- No real links, so Frappe neither blocks deleting a picked account nor follows a rename; the picker has no filters, and every rule moves into string parsing.

### Option 4: Table MultiSelect on Accounting Settings

A Table MultiSelect field over the same child doctype, shown as chips.

**Pros**:
- A compact chip picker in Desk.

**Cons**:
- The /books Settings screen has no Table MultiSelect control, so this needs a new control before the feature, for the same stored data as Option 2.

## Rationale

Option 2 keeps develop's tested design (child table, per row save rule matched by row `name`, silent Cash and Bank fallback, header button) and changes only what v16's own rules force. The deciding force is the v16 reports rule: spec 0001 on v16 already reads both the ledger and accounts through `get_list`, and a card that read its picks through `get_all` would be the one bypass in the reports layer, with no v16 role that needs it. Because all four Books roles read Accounting Settings, adding that read to the path costs no real user anything, and the client gate mirrors it so nobody sees a card that would 403.

Within Option 2, a few smaller calls were settled while writing:
- **An explicit `has_permission` on Settings before the child `get_list`.** The 403 then does not depend on how Frappe 16 treats a child of a single. Runner up: rely on `get_list` with `parent_doctype` alone.
- **A controller method, not a new shared helper.** `validate_dashboard_accounts()` lives in the Accounting Settings controller and reuses `validate_account` from `accounting/accounts.py`; only `DASHBOARD_ROOT_TYPES` goes into the shared module, because both the controller and the report need it. Runner up: a generic `validate_changed_rows` helper beside `validate_changed_accounts`, which has one caller today.
- **`link_filters` on the DocField for the picker**, so Desk and /books offer the same accounts (Books Defaults already does this), with a test keeping them in step with `DASHBOARD_ROOT_TYPES`. Runner up: a `static filters` entry on the row model, which Desk would not see.
- **The button copies `InvoiceCards.vue`**: a frappe-ui `Button` with `icon`, `tooltip` and `route` in the `#actions` slot, all of which exist in frappe-ui 1.0.0. Runner up: `router.push` from a click handler, as develop wrote it.

The silent fallback, chart order, follow the reload prompt and no row limit choices come straight from the scope and develop's spec; the tradeoffs they carry (a Total that may net out debt, stale rows that sit unnoticed) are accepted and listed in the spec's Consequences, with the "Net" label left as a follow up.
