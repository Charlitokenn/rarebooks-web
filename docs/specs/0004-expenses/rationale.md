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
