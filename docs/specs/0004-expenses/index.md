# 0004. Expenses

**Date**: 2026-11-12
**Status**: In Progress

Decision history: [rationale.md](rationale.md).

## Summary

Expenses become their own submittable document, Books Expense, listed under Purchases → Expenses in the sidebar. An expense is money already paid out (rent, fuel, bank fees): you pick the account it was paid from and add one or more rows, each with an Expense account and an amount. Submitting posts it to the ledger (each row debits its account, the total credits the paid from account), so it shows up in Top Expenses, profit and loss and the General Ledger with no extra work. To change a submitted expense you cancel it, which reverses its ledger rows, and use Duplicate to start a corrected draft, the same as every other submitted document in /books today. /books has no Amend action, for expenses or any other document.

## Requirements

**User stories**:
- As a Books User, I want to record a paid expense with its receipt in a few fields, so the books show what the business spent without me writing a journal entry.
- As a Books User, I want to split one receipt across several expense accounts, so fuel and parking on one slip land in the right places.
- As a Books Manager, I want a submitted expense to be fixed and only changed by cancelling it and recording a corrected copy, so the ledger keeps an audit trail.
- As a Books User on a phone, I want to log an expense from the dashboard's create menu, so I can record a receipt when I get it.
- As a Books Manager, I want to bring past expenses in through the importer and print an expense voucher, so the feature fits how I already work.

**Acceptance criteria**:
- **AC-1**: The sidebar's Purchases group has an "Expenses" item after "Purchase Payments" and before "Suppliers", routing to `/list/Expense`. It shows only to users who can read Books Expense.
- **AC-2**: The Expenses list shows the name, `date`, `party`, `paid_from`, `total` and a status badge (Saved, Submitted, Cancelled, the values `StatusMixin` stores), newest `date` first. It filters by Submitted and Cancelled like the other submittable lists, and offers Create to users who can create Books Expense.
- **AC-3**: A new expense opens with `number_series` set to the Books Defaults `expense_number_series` (`EXP-` on a fresh site), `date` set to today, and one empty row. The `paid_from` picker offers only leaf accounts that are Cash or Bank, or that have root type Liability and no account type (loans, an overdraft, a credit card account you add), with no Create. A row's `account` picker offers only leaf accounts with root type Expense, with no Create. The `party` picker offers only parties whose role is Supplier or Both, and Create makes a supplier. The form shows `total`, filled by the server preview from the rows.
- **AC-4**: Saving is refused by the controller, with a message naming the field or account, when: there are no rows; a row has no account or an amount of zero or below; a row account is a group account or not root type Expense; `paid_from` is a group account or is neither Cash, Bank nor a Liability with no account type; or `party` is a Customer only party. The client only mirrors these checks to place a message at the field.
- **AC-5**: Submitting posts balanced Books Ledger Entry rows with `voucher_type` Books Expense and `posting_date` equal to the expense `date`: one debit per distinct row account (rows on the same account are summed), and one credit to `paid_from` for `total`. No ledger row carries the party. After submit, the expense appears in the General Ledger (with "Expenses" offered in its Ref Type filter), and in the dashboard's Top Expenses and profit and loss for the period holding its `date`.
- **AC-6**: A draft (Saved) expense can be edited and saved any number of times with no ledger effect. A submitted expense is read only. Cancelling it marks its ledger rows reverted and adds the reversing rows (`reverse_entries`), so it drops out of Top Expenses, profit and loss and the General Ledger, and its status becomes Cancelled. A cancelled expense stays read only as the record. /books offers no Amend action on it, the same as every other submittable document; you correct it with Duplicate (AC-14). The form adds no expense specific amend action, button or route.
- **AC-7**: On save, when `party` and `reference_number` are both filled and another submitted expense has the same party and reference number, the server shows the message "{0} already has reference {1} for {2}." naming that expense, and the save still succeeds.
- **AC-8**: Books Manager and Books User (and System Manager) can read, create, write, submit and cancel expenses (they also hold Frappe's amend right, as on every submittable doctype, though /books offers no Amend action). Only Books Manager and System Manager can delete, and only a draft or a cancelled expense (Frappe refuses a submitted one). Deleting removes its ledger rows (`delete_entries`). A Books Cashier, or any user without read on Books Expense, gets `frappe.PermissionError` (403) from every expense API call, including the `paid_from` search, and sees no sidebar item, list, create menu entry or linked entries for expenses.
- **AC-9**: The dashboard's phone create menu (`MobileCreateMenu.vue`) has an "Expense" entry that opens a new expense form. It shows only to users who can create Books Expense.
- **AC-10**: The search palette finds an expense by its name, its party and its reference number, once saved, for users who can read Books Expense.
- **AC-11**: A party's and an account's Linked Entries panel lists the expenses that link them, showing the name, `date`, `party` and `total`.
- **AC-12**: The Import Wizard offers Expense with its rows. An imported expense goes through the same controller rules (AC-4) and is saved as a draft, ready to submit.
- **AC-13**: A built in print format "Business - Expense" prints the expense header, its rows and the total, and is the default print format for Books Expense on new and existing sites.
- **AC-14**: The form's existing Duplicate action works on a submitted or a cancelled expense: it opens a new draft with every value copied, including `date` and the rows, but with a new name, no `amended_from` and status Saved.
- **AC-15**: The Expenses list and the expense form work at phone width (no sideways page scroll, rows editable), as the other purchase screens do.
- **AC-16**: `bench migrate` on an existing v16 site adds both doctypes and the new fields. A patch creates the `EXP-` number series, sets Books Defaults `expense_number_series` to it when empty, and sets the default print format when none is chosen. A new site gets the same through `setup.bootstrap` and the setup wizard defaults.

## Decision

**Chosen option**: Option 2: a submittable Books Expense document with expense rows that posts straight to the ledger, paid at once from one account.

Add the Books Expense doctype and its Books Expense Account child table, a controller that validates and posts through `LedgerPosting`, a v16 `/books` model and sidebar item, and one new link layer hook (`linkQueries`) so the `paid_from` picker runs the same rule the controller checks.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:

| DocType | Field | Type | Required | Notes |
|---|---|---|---|---|
| Books Expense (new, `is_submittable: 1`, module Frappe Books) | `number_series` | Link → Books Number Series | yes | `set_only_once`; filtered to `reference_type = Expense`; copied by Duplicate |
| | `date` | Date | yes | default `Today`; becomes the ledger `posting_date` |
| | `paid_from` | Link → Books Account | yes | label "Paid From"; rule in Key invariants |
| | `party` | Link → Books Party | no | label "Supplier"; role Supplier or Both |
| | `reference_number` | Data | no | receipt, cheque or transfer reference |
| | `accounts` | Table → Books Expense Account | yes | label "Expenses" |
| | `total` | Currency | | `read_only`; filled by the server |
| | `user_remark` | Text | no | label "Remark" |
| | `attachment` | Attach | no | the receipt; `no_copy` (a receipt belongs to one expense) |
| | `status` | Select `Saved\nSubmitted\nCancelled` | | `read_only`, `no_copy`, stored by `StatusMixin`; DocType `states` give the badge colours |
| | `amended_from` | Link → Books Expense | | `read_only`, `no_copy`; Frappe's standard field on a submittable doctype, kept so the doctype matches the others. /books never sets it |
| Books Expense Account (new child, `istable: 1`, `editable_grid: 1`) | `account` | Link → Books Account | yes | `in_list_view`; `link_filters` `is_group = 0`, `root_type = Expense` |
| | `description` | Data | no | `in_list_view` |
| | `amount` | Currency | yes | `in_list_view` |
| Books Number Series (existing) | `reference_type` | Select | | add the option `Expense` |
| Books Defaults (existing single) | `expense_number_series` | Link → Books Number Series | no | after `sales_quote_number_series` in the number series section |

Books Expense sets `search_fields: "party,reference_number"`, `sort_field: "date"`, `sort_order: "DESC"`, `track_changes: 1`. The child JSON copies the doctype keys of `books_journal_entry_account.json`.

Relationships: Books Expense 1:N Books Expense Account. Each row N:1 Books Account. Books Expense N:1 Books Account (`paid_from`), N:0..1 Books Party (`party`), N:1 Books Number Series. On submit, Books Expense 1:N Books Ledger Entry (`voucher_type` / `voucher_no`). No database unique constraint; the duplicate check (AC-7) is a warning only.

Migration: both doctypes and the two existing doctype changes arrive through `bench migrate`. One `post_model_sync` patch `frappe_books.patches.add_expense_number_series` for existing sites (AC-16).

**State transitions**:
Saved (docstatus 0, editable, no ledger rows) → Submitted (docstatus 1, read only, ledger rows posted) → Cancelled (docstatus 2, ledger rows reversed). A Cancelled expense stays as the record; Duplicate starts a new Saved expense from it. There is no Amend transition in /books. Delete is allowed from Saved or Cancelled only.

**API surface**:
| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `/api/v2/document/Books Expense` (existing layer: insert, save, load, list, count) | POST, PUT, GET | the document with `accounts` rows | the saved document | Frappe doctype perms (AC-8) | 403 no right; 417 `ValidationError` (AC-4); 417 `TimestampMismatchError` on a stale copy |
| `BooksExpense.preview` (doc method via `run_doc_method`) | POST | the unsaved client copy | `number_series`, `total` filled; no save | `check_preview_permission` | 403 |
| submit, cancel, delete (existing document methods) | POST / DELETE | name, `modified` | new docstatus | submit, cancel, delete rights | 403; 417 for a stale copy |
| `frappe_books.accounting.accounts.search_expense_payment_accounts` (new, whitelisted, called by `search_widget` as its `query`) | POST via `searchFrappeLink` | `doctype`, `txt`, `searchfield`, `start`, `page_len`, `filters` | rows of `name` (and `account_name`) | read on Books Account and on Books Expense | 403 without either |

Server shape:
- `frappe_books/frappe_books/doctype/books_expense/`: `books_expense.json`, `books_expense.py` with `BooksExpense(StatusMixin, SeriesNamingMixin, Document)`, `_DOCTYPE_NAME = "Books Expense"`, and `test_books_expense.py`.
  - `preview()`: `check_preview_permission(self)`, `self.set_number_series()`, then the same row rounding and `total` as `validate`.
  - `validate()`, in this order:
    1. No rows: throw `_("An expense needs at least one row.")`. A row with an empty `account` or `amount` gets Frappe's own required field message.
    2. Per row, round first: `row.amount = rounded(as_decimal(row.amount))` (`accounting/money.py`, the currency precision). Then a rounded amount of zero or below throws `_("Row {0}: amount must be greater than zero.").format(row.idx)`. Rounding each row before summing keeps the debits equal to the credit, so rows like 0.004 + 0.004 can never post unbalanced.
    3. Per row `validate_account(row, "account", root_types=("Expense",))`, which already names the field and the account.
    4. `validate_expense_payment_account(self, "paid_from")`.
    5. `validate_party_role(self, is_purchase=True)`.
    6. `self.total = sum of the rounded row amounts`.
    7. The duplicate warning: when `party` and `reference_number` are both set, `frappe.get_list("Books Expense", filters={"party": ..., "reference_number": ..., "docstatus": 1, "name": ["!=", self.name]}, pluck="name", limit=1)`. Through `get_list`, it only names an expense the user can read. On a hit, `frappe.msgprint(_("{0} already has reference {1} for {2}.").format(other, self.reference_number, self.party))`, never `throw`. It also runs during import, where the message shows in the import log.
  - `on_submit()`: `posting = LedgerPosting(self)`, `posting.debit(row.account, row.amount)` per row, `posting.credit(self.paid_from, self.total)`, `posting.post()`.
  - `on_cancel()`: `reverse_entries(self)`. `on_trash()`: `delete_entries(self)`.
- `frappe_books/frappe_books/doctype/books_expense_account/`: JSON, an empty `BooksExpenseAccount(Document)` with its typing block.
- `frappe_books/accounting/accounts.py`:
  - `is_expense_payment_account(values)`, the one rule, over an account's `is_group`, `account_type` and `root_type`: `not is_group and (account_type in ("Cash", "Bank") or (root_type == "Liability" and not account_type))`. An empty `account_type` is either NULL or "" (both count as no type).
  - `validate_expense_payment_account(doc, fieldname)` reads those three values with `frappe.db.get_value`, as `validate_account` does. A group account throws `validate_account`'s message (`"{0} cannot be the group account {1}."`). Any other miss throws `_("{0} must be a Cash or Bank account, or a liability with no account type, but {1} is not.")` with the field label and account.
  - `search_expense_payment_accounts(doctype, txt, searchfield, start, page_len, filters, **kwargs)`, `@frappe.whitelist()` and type annotated:
    1. `frappe.has_permission("Books Expense", "read", throw=True)` first (403 for a Cashier).
    2. Then `frappe.get_list("Books Account", filters=[["is_group", "=", 0], ["name", "like", f"%{txt}%"]], or_filters=[["account_type", "in", ["Cash", "Bank"]], ["root_type", "=", "Liability"]], fields=["name", "is_group", "account_type", "root_type"], order_by="lft", limit_start=start, limit_page_length=page_len)`. That needs read on Books Account and applies the caller's rights.
    3. It keeps only the rows `is_expense_payment_account` accepts, so a Liability with a type is dropped. The or_filters only narrow the read, and the Python rule is what decides, the same function the save uses.
    4. It returns `[{"name": row.name} ...]` (`link.ts` reads `record.label || record.name`), and ignores the client `filters` argument on purpose. The model therefore declares no `filters` entry for `paid_from`.
    5. `txt` comes from `link.ts` already joined with `%` between letters, so a plain `like` matches as other pickers do.
    6. `**kwargs` absorbs `as_dict`, `reference_doctype`, `ignore_user_permissions` and `link_fieldname`, whose passing differs between Frappe 16 and `develop` (the WSL bench is on `develop`). Confirm the call on a v16 bench.
- `frappe_books/series.py`: `"Books Expense": ("EXP-", "Expense", "expense_number_series")` in `NUMBER_SERIES`. `setup.bootstrap` and `setup_service` then pick it up with no other change.
- `frappe_books/setup.py`: `DEFAULT_PRINT_FORMATS["Books Expense"] = "Business - Expense"`.
- `frappe_books/frappe_books/print_format/business___expense/`: the Jinja print format, copied from `business___payment` (its page CSS, company header and `get_print_settings`). It shows the name, `date`, `party` (when set), `paid_from`, `reference_number`, a table of each row's `account`, `description` and `amount`, `total`, and `user_remark`.
- `frappe_books/patches/add_expense_number_series.py` listed under `[post_model_sync]`. It is idempotent: it inserts `EXP-` only if missing (as `setup._insert_if_missing` does, leaving any existing series alone), sets Books Defaults `expense_number_series` only when empty, and calls `set_default_print_formats()`, which only fills a doctype with no default.

Client shape:
- `frontend/models/baseModels/Expense/Expense.ts`: `Expense extends FrappeDoc`, `doctype = 'Books Expense'`, `previewMethod = 'preview'`, `rowModels = { accounts: ExpenseAccount }`, `filters` (`number_series` reference type, `party` role in Supplier, Both), `createFilters` (`party` role Supplier), `linkQueries` (`paid_from` → the new search method), `presentation` (no Create on `paid_from`), `getListViewSettings` (AC-2), `getActions` (the ledger link action, as Journal Entry has).
- `frontend/models/baseModels/ExpenseAccount/ExpenseAccount.ts`: row model, no Create on `account`.
- `frontend/src/frappe/link.ts`: `searchFrappeLink` passes the model's `linkQueries[fieldname]` as `search_widget`'s `query` when one is set. This is the one new link layer pattern; add a line for it to the "Where each part goes" table in `docs/framework-backed-doctypes.md`.
- Importer: `ModelNameEnum.Expense` in `getImportableSchemaNames`. The template leaves out `status`, `total` and `amended_from` (read only or no copy), and maps rows to `accounts` columns as Journal Entry's `accounts` are.
- The Number Series model labels the new `Expense` reference type (translated), as it labels the others.
- Linked Entries needs no server change: `frappe_books/linked_entries.py` already follows every Link on a Books doctype and its child tables, so `party`, `paid_from` and the row `account` are found. Only the client sequence and display fields change.
- `ModelNameEnum.Expense = 'Expense'` (the schema name and route key; the model names the doctype `Books Expense`), the `frappeModels` entry, `sidebarConfig.ts` (AC-1), `MobileCreateMenu.vue` (AC-9), `LinkedEntries.vue` sequence and display fields (AC-11), `importer.ts` (AC-12), `search.ts` searchables (AC-10), and `GeneralLedger.ts` Ref Type option `{ label: t\`Expenses\`, value: 'Books Expense' }` (AC-5).

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| New form | `number_series` | Books Defaults `expense_number_series`, via `set_number_series` in `preview` |
| New form | `date` | DocType default `Today` |
| Preview, save | `total` | derived: sum of `accounts[].amount`, `rounded` to the currency precision |
| Save | duplicate warning's other expense | `frappe.get_list("Books Expense", filters party, reference_number, docstatus 1, name != self.name, limit 1)` |
| Submit | each debit | `accounts[].account`, `accounts[].amount` (summed per account by `LedgerPosting`) |
| Submit | the credit | `paid_from`, `total` |
| Submit | `posting_date` | the expense `date` (`ledger._posting_date` reads `date`) |
| Submit | currency | the company base currency; there is no currency field on the expense (base only) |
| Cancel | reversing rows | `reverse_entries(self)` from its posted rows |
| List | status badge | `status`, stored by `StatusMixin.on_change` |
| Paid from picker | options | `search_expense_payment_accounts`, from `Books Account` `is_group`, `account_type`, `root_type` |
| Top Expenses, P&L | the expense amounts | the posted ledger rows, read by the existing dashboard and report queries (no change) |
| Print | header, rows, total | the document fields; company details from the existing print helpers (`get_print_settings`) |

**Key invariants**:
- Each row amount is rounded to the currency precision before anything else, `total` equals the sum of those rounded amounts, and every rounded row amount is above zero.
- The Paid From picker and the save use one rule (`is_expense_payment_account`), so the picker never offers an account the save refuses.
- Duplicate never copies `status`, `attachment` or `amended_from`.
- /books has one way to correct a submitted document, cancel then Duplicate, the same for expenses as for every other submittable doctype. No expense only lifecycle action exists.
- A submitted expense's ledger rows balance: total debits equal the one credit (`LedgerPosting._validate`).
- `paid_from` is a leaf account that is Cash or Bank, or root type Liability with an empty account type. Payable, Tax and Stock Received But Not Billed accounts are never allowed.
- Every row account is a leaf account of root type Expense.
- The party never appears on the expense's ledger rows (nothing is owed).
- Business rules live in the controller. The client mirrors only to place messages.

**Security model**:
DocType permissions: System Manager and Books Manager get every right (including delete, import, export, share); Books User gets read, create, write, submit, cancel, amend, print, email, export, report (no delete, no import); Books Cashier gets nothing. The Import Wizard checks import rights, so only Managers import (AC-12). The new whitelisted search method checks read on Books Expense and on Books Account itself and reads through `get_list`. `preview` keeps `check_preview_permission`. No regulated data; amounts are business records, with the change history kept by `track_changes` and the cancelled record staying in place.

**Configuration required**: none (no environment variables or credentials).

**Critical test scenarios**:
- Happy path: create an expense with two rows on two Expense accounts paid from Cash, submit, and see two debits and one credit in the General Ledger and the amounts in Top Expenses for that month, verifies **AC-3**, **AC-5**
- Failure case: save with a Customer only party, a Payable `paid_from`, a group row account and a zero amount, each refused with its message; then cancel a submitted expense and see Top Expenses drop back, verifies **AC-4**, **AC-6**
- Duplicate: two expenses for one supplier with one reference number save with the warning, verifies **AC-7**
- Auth/permission: a Books Cashier gets 403 on list, insert and the `paid_from` search, and sees no sidebar item; a Books User cannot delete, verifies **AC-8**

## Build plan

Ordered as tracer bullets (the project default): a thin thread through server, client and tests first, then thicker slices.

1. Server thread: both doctype JSONs, the `Expense` number series option, the Books Defaults field, the `series.py` entry, the `BooksExpense` controller (preview, validate without the duplicate warning, submit, cancel, trash) with `is_expense_payment_account` and `validate_expense_payment_account`, the patch, and Python tests for posting, row rounding (0.004 + 0.004 posts balanced), cancel, server side amend naming (`EXP-0001-1`, despite `SeriesNamingMixin.autoname`; this only guards Frappe's own amend path, /books has no Amend action), delete, each AC-4 rule and the role permissions, satisfies **AC-4**, **AC-5**, **AC-6**, **AC-8**, **AC-16**
2. Thin screen end to end: `Expense` and `ExpenseAccount` models, `ModelNameEnum`, `frappeModels`, the sidebar item, list settings, General Ledger Ref Type option, node tests for the model and form layout, a Playwright happy path (create, submit, see it in the General Ledger and Top Expenses), then the guard tests, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-5**, **AC-6**
3. Pickers and rules: `search_expense_payment_accounts` with the shared rule, the `linkQueries` hook in `link.ts` (and its line in `docs/framework-backed-doctypes.md`), party filters and Create, the duplicate warning, Python plus node tests (the picker offers exactly what the save accepts; a Cashier gets 403 from the search), then the guard tests again, satisfies **AC-3**, **AC-4**, **AC-7**, **AC-8**
4. Entry points and extras: phone create menu, search fields and searchables, Linked Entries, importer, the "Business - Expense" print format and its default, and a check of the Duplicate action, with node and Python tests, satisfies **AC-9**, **AC-10**, **AC-11**, **AC-12**, **AC-13**, **AC-14**
5. Phone layout and the full Playwright suite, desktop and phone: list, form, rows, cancel and Duplicate of a cancelled expense, the Cashier gate, then run the guard tests (`settings-readers`, `settings-models`, `link-create`), satisfies **AC-8**, **AC-15**

## Consequences

**Positive**:
- Everyday spending reaches the ledger in a few fields, so Top Expenses and profit and loss reflect real costs with no report change.
- One reusable `linkQueries` hook lets later pickers run a server rule the AND filters cannot express.
- Cancel then Duplicate keeps the same audit trail and the same steps as every other posted document.

**Negative / tradeoffs**:
- A supplier bill you pay later is still a Purchase Invoice; users must learn which to use (expense = paid now).
- No tax and base currency only: input tax on an expense can't be claimed back through it, and a foreign bill needs converting by hand.
- A new link layer pattern to maintain, plus one more doctype for the guards and importer.
- Party is stored but off the ledger, so a supplier's ledger view does not show their expenses (Linked Entries does).

**Neutral**:
- One patch for existing sites (number series, default series, print format).
- The status badge uses the house values (Saved, Submitted, Cancelled), so "Draft" shows as Saved like every other document.

## Follow-up

- [ ] Tax on expenses (Books Tax per row, posting to tax accounts), if input tax needs claiming back.
- [ ] Foreign currency expenses with an exchange rate, if foreign bills become common.
- [ ] Set up a Frappe 16 bench for `/develop` and `/check verify`; the WSL bench at `~/books-bench` runs Frappe `develop`.
- [ ] Pull `origin/version-16` (one commit ahead) before building.
- [ ] Widen the scope title past the dashboard port (from `/scope`).
- [ ] If an Amend action is ever wanted in /books, design it once for every submittable doctype (its own `/architect`), never for expenses alone.
