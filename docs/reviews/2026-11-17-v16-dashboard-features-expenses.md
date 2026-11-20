# Review, v16-dashboard-features (Expenses), 2026-11-17

**Reviewed by**: Sonnet 5.5 (fresh reviewer; author model not stated)
**Scope**: 67 app and test files (vendored skill files and docs left out), branch vs origin/version-16
**Verdict**: Approve with nits

## Summary
This change adds the Books Expense doctype with its rows, the EXP- series and patch, a controller that rounds, validates and posts to the ledger, two name only account searches for Books User, the Vue models and wiring, linked entries, import, a print format, and one shared toast handler for server messages. It follows specs 0004 and 0006 closely. Business rules sit in the controller, the account searches check the expense rights on the server before they read, and the one place that reads accounts without account rights returns names only. I found no blockers or majors. The notes below are small edge cases and tidiness.

## Minor
### 🟡 Toast failures are not caught, `frontend/src/frappe/api.ts:202` and `frontend/src/web/api.ts:48`
**Problem**: Both callers use `void showServerMessages(...)`. The function loads `src/utils/interactive` on demand and calls `showToast`. If that import or the toast throws, the promise rejects with nobody listening.
**Why it matters**: A save that succeeded would log an unhandled rejection, and any global error reporter would count it as a failure of the save. The user also loses the warning, which is the whole point of AC-7.
**Suggested fix**: Catch inside `showServerMessages` (or at the two call sites) and log with `console.error`, so a display problem never looks like a request problem.

### 🟡 Account searches depend on Books Account staying a translated doctype, `frappe_books/accounting/accounts.py:104`
**Problem**: Both searches ignore `txt`, `start` and `page_len` on purpose, because `search_widget` filters and pages translated doctypes itself. `books_account.json` does set `translated_doctype: 1` today, and the Python tests call the searches with typed text.
**Why it matters**: If that flag is ever removed, the pickers would return every account on every keystroke with no paging and no text match, and nothing would fail loudly.
**Suggested fix**: Add a short test that asserts the Books Account meta is translated (or a comment on the searches naming the flag), so the dependency is visible.

## Nits
- ⚪ `frappe_books/frappe_books/doctype/books_expense/books_expense.py:59`, an empty row amount rounds to 0 and gets "amount must be greater than zero", where spec 0004 says Frappe's own required message. Harmless, but the spec text and the behavior differ.
- ⚪ `frappe_books/frappe_books/doctype/books_expense/books_expense.py:75`, `rounded(row.amount)` looks up the company currency once per row. A cached lookup, so cheap, but it could be read once.
- ⚪ `frappe_books/patches/add_expense_number_series.py:4`, imports the private `_insert_if_missing` from `setup.py`. Consider making it public if more patches will use it.
- ⚪ `frontend/src/utils/filterFields.ts:5`, a pure helper now imports the global `fyo` singleton for the read check. Passing `fyo` in as an argument would keep it testable without the app init.
- ⚪ `frontend/src/pages/CommonForm/LinkedEntries.vue:111`, the new `total` badge applies to any linked entry that has a positive `total`, not only expenses. Fine today, but it can surprise a later doctype.

## Strengths
- Every account rule has one source: `is_expense_payment_account` is used by both the save check and the picker, so the picker cannot offer what the save refuses, and a test proves it both ways.
- Rows are rounded before they are summed, so debits always equal the one credit, with tests for 0.004 plus 0.004 and for company currency units.
- The Books User gap is closed with care: the searches are gated on create or write of Books Expense, return `frappe._dict(name=...)` only, and are tested as a Books User (still 403 on Books Account) and as a Cashier (refused, 404 through `search_widget`).
- The duplicate warning goes through `get_list`, so it never names an expense the user cannot read, and a test covers that case.
- The toast handler is small, in one module, deduplicates by text, keeps warnings and errors until closed, and excludes the preview call. The node tests cover each request path.
- The series type is checked on the server in `SeriesNamingMixin.autoname`, so the client filter is only a convenience.

## Test coverage
Strong. Python has about 38 tests covering posting, rounding, cancel and reverse, amend naming, each validation rule, the pickers, permissions by role, the duplicate warning (submitted only, readable only), print, linked entries, and the patch. Node covers the models, the importer, link search with `linkQueries`, filter fields for a Books User, and every server message path. Playwright covers the expense flow and the phone layout. No new branching logic was found without a test. The one runtime gap, the setup wizard `call()` toast, is listed as open in `verify.md`.
