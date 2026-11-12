# 0004. Expenses: decision record

Build spec: [index.md](index.md).

## Context

The version-16 line has no way to record everyday spending such as rent, fuel or bank fees. Today you either raise a Purchase Invoice (built for supplier bills with items, stock, taxes, due amounts and settlement) or write a Journal Entry, which only Books Managers can make and which asks for balanced debit and credit rows by hand. Both are heavy for a petty cash receipt, so spending tends to go unrecorded, and the dashboard's Top Expenses and profit and loss under count costs.

The forces: every /books screen is Frappe backed (fieldnames end to end, rules in the controller, the `FrappeDoc` layer); reports read the ledger through `get_list` so the caller's rights apply; Top Expenses and profit and loss already read ledger rows on Expense accounts; the roles are Books User, Books Manager and Books Cashier; the link layer passes AND filters only to `search_widget`.

You chose: a posted document, paid at once, rows on Expense accounts, no tax, base currency, cancel and amend, an optional supplier, a receipt attachment, Books User and Manager rights (no Cashier), a duplicate warning, and the phone menu, search, linked entries, import, print and duplicate extras.

## Options considered

### Option 1: A plain expense record with no ledger effect

A list of what was spent, for tracking only.

**Pros**:
- Smallest build: no posting, no cancel logic.

**Cons**:
- The money never reaches the books, so the dashboard, profit and loss and balances disagree with the expense list.

### Option 2: A submittable Books Expense that posts on submit, paid at once (chosen)

A focused document: paid from one account, rows on Expense accounts, posted with `LedgerPosting`, reversed on cancel.

**Pros**:
- Reuses the ledger, the dashboard and the reports with no change.
- Follows the same lifecycle as journal entries and payments, so users and code already know it.

**Cons**:
- A new doctype and model to maintain; the paid from rule needs a new link layer hook.
- No pay later: a bill you pay later still needs a Purchase Invoice.

### Option 3: Paid now or later, with settlement

Like Option 2, but an expense can also be owed to a supplier and settled by a Purchase Payment.

**Pros**:
- One document for every kind of spend.

**Cons**:
- It needs due amounts, payment status and settlement, which rebuilds most of Purchase Invoice.

### Option 4: A journal entry template ("Expense" entry type)

Add an Expense entry type to Journal Entry with a simplified form.

**Pros**:
- No new doctype.

**Cons**:
- Journal Entry is Manager only, its balanced rows model stays visible, and an entry type that bends one form two ways tends to rot.

## Rationale

Option 2 matches what you said an expense is: money already paid, which should show in the books right away. Posting through the existing `LedgerPosting`, `reverse_entries` and `delete_entries` means the dashboard and reports need no change, and the cancel and amend lifecycle is already familiar from journal entries and payments. Option 3 duplicates Purchase Invoice, and Option 4 keeps the Manager only gate and the debit and credit form that make journal entries a poor fit for receipts.

The paid from rule (Cash or Bank, or a Liability with no account type) cannot be written as AND filters, and you chose a server query over narrowing to Cash or Bank or adding a "paid with" field. The runner up was Cash or Bank only, which needs no new pattern but pushes credit card spending back into journal entries. Liabilities with an account type (Payable, Tax, Stock Received But Not Billed) are excluded on purpose: an expense credited to Creditors Payable with no party, or to a tax or stock clearing account, would break payable, tax and stock reconciliation without any error.

Decisions made at write time:
- **Sidebar position**: after Purchase Payments, before Suppliers (documents first, then parties). Runner up: right after Purchase Invoices.
- **Duplicate keeps the date**: the existing generic Duplicate action copies every value; adding a date reset would be a model override for a field the user edits anyway. Runner up: reset `date` to today.
- **Status values**: the house `StatusMixin` values (Saved, Submitted, Cancelled) rather than a new "Draft" label, so the list badges match every other document.
- **Party off the ledger**: nothing is owed, so putting the party on the rows would make the supplier look settled in reports that read party balances. Runner up: put it on the debit rows for party reporting.
- **Total stored**: `total` is stored, as every Books document stores its totals for lists and print; it is recomputed on every preview and save, so it cannot go stale.

## Update 2026-11-12: no Amend action in /books (AC-6)

`/develop` found that /books has no Amend action on any document, so AC-6's amend step could not be built as written. You decided expenses mirror the other submittable doctypes exactly: no Amend action is added, for expenses or anything else. A cancelled expense stays as the record, and Duplicate (already shown on submitted and cancelled documents, `getDuplicateAction` in `frontend/src/utils/ui.ts`) starts the corrected draft. Options weighed: a shared Amend action for every submittable doctype, or an expense only one. Both were set aside to keep one correction path across the app; a shared action stays possible later as its own decision. The server keeps Frappe's `amended_from` field and amend right, and the existing amend naming test, because they come with every submittable doctype and cost nothing.

## Update 2026-11-12: who records expenses, and how a Books User picks accounts

`/check verify` on a v16 site found that a Books User could not fill an expense: Books User has no right on Books Account. That was a deliberate decision in commit `d0f7aa8` ("it has no access to accounts, journal entries or the ledger"), made before this spec, which gave Books User full expense rights without noticing that an expense needs two account picks. Payments avoid the clash because the server fills their accounts.

You decided Books User keeps recording expenses and keeps no account rights. Two narrow server searches (Paid From and the row account), gated on create or write on Books Expense, read accounts with `get_all` and return names only. The row picker offers every leaf Expense account, the same rule the save checks, with no new curation field. Account links that would end in a 403 stay hidden, which the existing `canLink` and `canOpenLedger` checks already do.

Options weighed: giving Books User read on Books Account (one permission row, but it reverses part of `d0f7aa8` and opens the whole chart), and making expenses a Books Manager only job (nothing to build, but a Books User could no longer log a receipt). A curated "use on expenses" flag on accounts was set aside as more fields and rules than the need warrants.

A cross check on another model then found that a list filter on an account column searches Books Account directly, so a Books User would get a 403 there too, on every list. You chose to hide a Link filter whose target the user cannot read, the same rule the open button uses, over passing the expense search into the filter picker (expense only) or leaving the 403. The same pass corrected the search shape to match Frappe 16 (rows as `frappe._dict`, and `search_widget` matching and paging translated names itself).
