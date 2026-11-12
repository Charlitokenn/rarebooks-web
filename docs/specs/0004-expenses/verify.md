# Verify: Expenses · spec 0004 · updated 2026-11-12
_Steps derived from spec 0004 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._
_Milestone 1 (server thread) has landed. The screen steps arrive with milestones 2 to 5; until then, check these through the API, `bench console` or Desk._

## UI / manual (server, through Desk or the API)
- [ ] Insert a Books Expense with no `number_series`, paid from a Cash account, rows Rent 100 and Fuel 50 → it is named `EXP-1001` style (from Books Defaults `expense_number_series`), `total` is 150, status Saved → AC-3, AC-16
- [ ] Call `preview` on an unsaved expense with rows 4.5 and 5.5 → `number_series` and `total` 10 are filled and no record is saved → AC-3
- [ ] Submit that expense → Books Ledger Entry rows: Rent debit 100, Fuel debit 50, Cash credit 150, `voucher_type` Books Expense, `posting_date` equal to the expense `date`, `party` empty on every row → AC-5
- [ ] Two rows on the same account (Fuel 30 and 20) → one Fuel debit of 50 → AC-5
- [ ] Rows 10.004 and 10.004 → each stored as 10.00, `total` 20.00, ledger debits and credit both 20.00 → AC-5 (rounding before summing)
- [ ] Rows 0.004 and 0.004 → refused with "Row 1: amount must be greater than zero." → AC-4
- [ ] Open the dashboard for the month holding the expense `date` → Rent shows in Top Expenses and in profit and loss → AC-5
- [ ] Edit a Saved expense and save twice → no ledger rows exist → AC-6
- [ ] Try to change `paid_from` on a submitted expense → refused (update after submit) → AC-6
- [ ] Cancel the submitted expense → its ledger rows are marked reverted with reversing rows added, status Cancelled, Rent drops out of Top Expenses → AC-6
- [ ] Amend the cancelled expense → the new draft is named `<original>-1`, `amended_from` set, every value copied, status Saved → AC-6
- [ ] Save with no rows → "An expense needs at least one row." → AC-4
- [ ] Save with a 0 or negative amount → "Row 1: amount must be greater than zero." → AC-4
- [ ] Save with a group row account, then an Income row account → the group message, then "must be of type Expense" → AC-4
- [ ] Save `paid_from` = Payable, Tax (liability with a type), an Asset with no type, a Cash group → each refused naming the field and account; Cash, Bank and an untyped Liability (a loan) are accepted → AC-4
- [ ] Save with a Customer only party → "Supplier must be a Supplier, but ... is a Customer."; a Supplier or Both party saves → AC-4
- [ ] Two expenses for one supplier with reference R-77, the first submitted → the second saves and shows "EXP-.... already has reference R-77 for <supplier>." → AC-7
- [ ] As a Books User: create, submit, cancel and amend work; delete is refused (403) → AC-8
- [ ] As a Books Manager: delete a cancelled expense → it and its ledger rows are gone; deleting a submitted one is refused → AC-8
- [ ] As a Books Cashier: list, insert and `preview` on Books Expense all return 403 → AC-8
- [ ] Print an expense with the default format → "Business - Expense" shows the name, date, Paid From, reference, each row's account, description and amount, and the total → AC-13

## UI / manual (milestone 2, the thin screen at /books)
- [ ] Sign in as a Books User, open the sidebar's Purchases group → "Expenses" sits after "Purchase Payments" and before "Suppliers", and opens `/books/list/Expense` → AC-1
- [ ] Sign in as a Books Cashier → no Expenses item under Purchases; `/books/list/Expense` shows no rows (403 from the server) → AC-1, AC-8
- [ ] The Expenses list shows Expense No, Status, Date, Supplier, Paid From and Total, newest date first, with a Saved, Submitted or Cancelled badge → AC-2
- [ ] Filter the list by Submitted, then Cancelled → only those rows show → AC-2
- [ ] Click New → the form opens with Number Series `EXP-`, Date today, one empty row under Expenses, and Total read only → AC-3
- [ ] Fill Paid From with a Cash account, a row of Rent 25 and a row of another Expense account 10 → Total shows 35 after the preview → AC-3
- [ ] Save, then Submit → status Submitted, every field read only, and the form offers "Accounting entries" under View → AC-5, AC-6
- [ ] Open "Accounting entries" → the General Ledger opens on the expense date filtered to Ref Type "Expenses" and this expense: two debits and one credit of 35 → AC-5
- [ ] Open the General Ledger's Ref Type filter → "Expenses" is offered after "Journal Entries" → AC-5
- [ ] Open the dashboard for this month → Total spending in Top Expenses is 35 higher than before the submit → AC-5
- [ ] Cancel the expense → status Cancelled in the list, and Top Expenses drops back by 35 → AC-6
- [ ] Amend it → a new draft named `<original>-1` opens with the rows copied → AC-6

## Commands (milestone 2)
- [ ] `cd frontend && node --test tests/expense-model.test.mjs tests/permissions.test.mjs` → all pass → AC-1, AC-2, AC-3, AC-5
- [ ] `cd frontend && npx playwright test tests/ui/expense.spec.ts` against a v16 site → 3 pass → AC-1, AC-3, AC-5, AC-6
- [ ] `cd frontend && node --test tests/settings-readers.test.mjs tests/settings-models.test.mjs tests/link-create.test.mjs` → guards pass

## Commands
- [ ] `bench --site <v16 site> migrate` → Books Expense and Books Expense Account tables exist, Books Defaults has `expense_number_series` = `EXP-` (unless one was set), the default print format for Books Expense is "Business - Expense", and the patch `frappe_books.patches.add_expense_number_series` is in the Patch Log → AC-16
- [ ] `bench --site <v16 site> run-tests --app frappe_books --module frappe_books.frappe_books.doctype.books_expense.test_books_expense` → 22 tests OK → AC-4, AC-5, AC-6, AC-7, AC-8, AC-13, AC-16
- [ ] `bench --site <v16 site> run-tests --app frappe_books --module frappe_books.tests.test_printing` → OK → AC-13
- [ ] `uvx ruff@0.14.10 check frappe_books && uvx ruff@0.14.10 format --check frappe_books` → clean

## Value sourcing checks
- [ ] `number_series`: set Books Defaults `expense_number_series` to another Expense series, open a new expense → it uses that series; clear it → it falls back to `EXP-`
- [ ] `date`: a new expense defaults to today; change the date to last month and submit → ledger `posting_date` is last month and it shows under last month's Top Expenses, not this month's
- [ ] `total`: change a row amount on a draft and preview → `total` follows the rounded sum
- [ ] Duplicate warning source: the matching expense is a draft, or cancelled → no warning (only submitted ones count); a user who cannot read the other expense → no warning
- [ ] Credit currency: on a site whose company currency is not INR, submit → ledger rows are in the company currency, rounded to its smallest unit
- [ ] Reversing rows come from the posted rows: cancel → reversing rows mirror the original amounts exactly
- [ ] Amend name: amend twice (`-1`, then cancel and amend again) → `-2`
- [ ] Status badge source: `status` column reads Saved, Submitted, Cancelled through the lifecycle
- [ ] Top Expenses and profit and loss read the posted ledger rows: a Saved expense never shows there

## UI / manual (milestone 3, pickers and rules)
- [ ] As a Books User, open a new expense and the Paid From picker → it offers Cash, Bank and untyped Liability leaf accounts (a loan), and no Payable, Tax, plain Asset, group or Expense account, and no Create → AC-3
- [ ] Type part of a loan account's name in Paid From → the list narrows to it → AC-3
- [ ] Pick each offered Paid From account in turn and save → every one saves (the picker never offers what the save refuses) → AC-3, AC-4
- [ ] Open the Supplier picker → only Supplier and Both parties; Create opens a new party with role Supplier → AC-3
- [ ] Submit an expense for a supplier with reference R-1, then save a second with the same supplier and reference → the message "{first} already has reference R-1 for {supplier}." shows and the second still saves → AC-7
- [ ] As a Books Cashier, call `frappe.desk.search.search_widget` for Books Account with `query` set to `frappe_books.accounting.accounts.search_expense_payment_accounts` → refused (403, or the "Method not found" page outside developer mode) → AC-8

## Commands (milestone 3)
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.frappe_books.doctype.books_expense.test_books_expense` → passes, including the Paid From search tests → AC-3, AC-4, AC-8
- [ ] `cd frontend && node --test tests/expense-model.test.mjs tests/link-search.test.mjs` → passes (party filters, Create values, `linkQueries` sent as `query`) → AC-3

## Value sourcing checks (milestone 3)
- [ ] Paid From options come from `search_expense_payment_accounts` and `is_expense_payment_account`: change an untyped Liability to account type Tax in Desk, reopen the picker → it drops out → Value sourcing row "Paid from picker"
- [ ] Duplicate warning names only an expense the user can read: as a user with read on Books Expense restricted by User Permission, repeat a reference held by an expense they can't read → no message → Value sourcing row "duplicate warning's other expense"

## UI / manual (milestone 4, entry points and extras)
- [ ] As a Books User at phone width, open the dashboard and tap Create → the menu lists "Expense" after "Make payment"; tap it → a new expense form opens at `/books/edit/Expense/...` → AC-9
- [ ] As a Books Cashier at phone width, tap Create → no "Expense" entry → AC-9, AC-8
- [ ] Save an expense for a supplier with reference RCPT-77, then open the search palette and search its name, the supplier's name, and RCPT-77 → each finds the expense → AC-10
- [ ] As a Books Cashier, search RCPT-77 → no expense, and no Expense filter chip → AC-10, AC-8
- [ ] Open that supplier, its Paid From account and a row's Expense account, then Linked Entries on each → an "Expense" group lists the expense with its name, date, supplier and total → AC-11
- [ ] Cancel the expense and reopen Linked Entries → it drops out (cancelled documents are left out) → AC-11
- [ ] As a Books Manager, open Import Wizard → Expense is offered; its template has Paid From, Date, Supplier, Reference Number, Remark and the Account, Description and Amount columns for Expenses, and no Status, Total or Amended From → AC-12
- [ ] Import two expenses (one with two rows, one with an amount of 0), answer No to "submit after syncing" → the first saves as a Saved draft named `EXP-...` with total equal to its rows; the second is refused with "Row 1: amount must be greater than zero." → AC-12, AC-4
- [ ] As a Books User, open Import Wizard → Expense is not offered (only Managers import) → AC-12, AC-8
- [ ] Open a submitted expense and Print → "Business - Expense" is the chosen format and shows the name, date, supplier, Paid From, reference, each row's account, description and amount, the total and the remark → AC-13
- [ ] On a submitted (or amended) expense with a receipt attached, use Duplicate → a new unsaved form with the same series, date, Paid From, supplier, reference, remark and rows, but no receipt, no Amended From and status Saved; save it → a new `EXP-` name → AC-14

## Commands (milestone 4)
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.frappe_books.doctype.books_expense.test_books_expense` → passes, including the linked entries test → AC-11, AC-13
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_search` → passes, including finding an expense by name, supplier and reference, and nothing for a Cashier → AC-10
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_data_import` → passes, including the draft expense import with one refused row → AC-12
- [ ] `cd frontend && node --test tests/expense-model.test.mjs tests/importer.test.mjs tests/permissions.test.mjs tests/search.test.mjs` → passes → AC-10, AC-12, AC-14
- [ ] `cd frontend && yarn test:ui tests/ui/mobile-dashboard.spec.ts --trace off` → passes, including "the create menu opens a new expense" → AC-9

## Value sourcing checks (milestone 4)
- [ ] Print header and company details come from `get_print_settings`: change the company name and colour in Print Settings, reprint → the expense voucher follows → Value sourcing row "Print"
- [ ] Duplicate copies only what Duplicate may copy: `attachment`, `status` and `amended_from` are `no_copy` in the DocType, so a copy never carries them, whatever the source's state → Key invariant on Duplicate

## UI / manual (milestone 5, phone layout and the full suite)
- [ ] As a Books User on desktop, click New on Expenses, pick a Cash account in Paid From, an Expense account and 42 in the first row → Total shows 42.00; Save, then Submit → status Submitted, no Save button, Paid From shows as disabled text → AC-3, AC-6
- [ ] On that submitted expense, Actions → Cancel → "Cancel Expense" → status Cancelled → AC-6
- [ ] As a Books User, delete a draft expense through the API → 403 → AC-8
- [ ] As a Books Cashier, open /books → no Expenses link; list and insert on Books Expense return 403; the `paid_from` search returns 403 (or 404 outside developer mode) → AC-1, AC-8
- [ ] At phone width (390px), open Expenses and search an expense with a supplier → one two line row: the supplier and the total, then the name, Paid From and date, with the Submitted badge; the page has no sideways scroll, and tapping the row opens the form with no sideways scroll → AC-2, AC-15
- [ ] At phone width, open a new expense → "1 row"; tap Row 1 → a sheet with Account, Description and Amount; Done, then Add row → "2 rows", no sideways scroll → AC-3, AC-15
- [ ] At phone width, open a submitted expense, More actions → Cancel → "Cancel Expense" → Cancelled → AC-6, AC-15
- [ ] Amend from the /books form: not built. The app has no Amend action on any document; spec 0004 needs `/architect` to settle it (AC-6) → AC-6

## Commands (milestone 5)
- [ ] `cd frontend && yarn test:ui tests/ui/expense.spec.ts --trace off` against a v16 site → 9 pass → AC-1, AC-2, AC-3, AC-5, AC-6, AC-8, AC-15
- [ ] `cd frontend && node --test tests/settings-readers.test.mjs tests/settings-models.test.mjs tests/link-create.test.mjs` → guards pass

## Acceptance-criteria coverage
- AC-1, AC-2: the milestone 2 sidebar, Cashier and list steps
- AC-9, AC-10, AC-11, AC-12, AC-14: the milestone 4 steps (create menu, search, linked entries, import, Duplicate)
- AC-15: the milestone 5 phone steps (list, form, rows, cancel)
- AC-6 amend through /books: not built, owed to `/architect` (no Amend action exists in the app)
- AC-3: new expense series and `preview` steps (server half; pickers come in milestone 3)
- AC-4: the refusal steps for rows, row accounts, `paid_from` and party
- AC-5: posting, summing, rounding and Top Expenses steps (General Ledger Ref Type comes in milestone 2)
- AC-6: draft edit, read only after submit, cancel and amend steps
- AC-7: the duplicate reference step (the client message comes in milestone 3)
- AC-8: Books User, Books Manager and Books Cashier steps (the `paid_from` search 403 comes in milestone 3)
- AC-13: the print step, and the milestone 4 Print step on the form
- AC-16: the migrate command step
