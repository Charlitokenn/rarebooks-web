# Review, v16-dashboard-features, 2026-11-11

**Reviewed by**: Sonnet 5.5 (fresh review pass; author model not stated)
**Scope**: 15 code/test files, committed in 10e2f369 (diffed against 980e90c8 / HEAD~1) plus 2 small uncommitted edits (test_dashboard.py, scope.md)
**Verdict**: Approve with nits

Note: the brief said the feature was uncommitted, but git shows it already committed as 10e2f369 on top of 980e90c8. I reviewed `git diff HEAD~1` plus the working tree. Specs 0003 ignored.

## Summary
Adds a permission-aware `get_best_sellers` (one `frappe.get_list`, Decimal finish in Python, top five plus all-items total), a `BestSellers.vue` donut copied from Expenses, widened row gate in Dashboard.vue, and Python, node and Playwright tests. The implementation matches spec 0002 closely and I found no correctness, security or contract defects. The remaining points are test fragility and a few uncovered branches.

## Minor
### 🟡 Tests share Dec 2031 data across classes, `frappe_books/tests/test_permissions.py:159`
**Problem**: The permission test inserts a 140 sale for "Rights Seller" on 2031-12-05/06, the same month the happy-path test in test_dashboard.py (`TODAY = 2031-12-15`, "This Month") asserts an exact top five (70..30) and total 280. They stay isolated only because IntegrationTestCase rolls back per class.
**Why it matters**: If either test is ever run with a commit between them (or the rollback behaviour changes), the happy-path test fails with a confusing diff.
**Suggested fix**: Give the permission test its own month (as the other BestSellers tests do) and note the one-month-per-test rule in the helper docstring.

### 🟡 Unknown period and YTD paths of `get_best_sellers` untested, `frappe_books/reports/dashboard.py:88`
**Problem**: The spec lists `ValidationError` for an unknown period, and `YTD` is a distinct branch of `get_period_dates`; neither is exercised for this method.
**Why it matters**: Low risk (shared helper), but it is the only new error path on a whitelisted method.
**Suggested fix**: Add one test asserting `ValidationError` for a bad period and one YTD case.

### 🟡 UI tests do not cover the card being hidden without sales read, `frontend/tests/ui/dashboard-best-sellers.spec.ts:186`
**Problem**: AC-8's client side (no `canRead.sales` hides the card, and the row and divider when ledger is also denied) has no test; only the ledger-denied case exists.
**Why it matters**: The gate expression in Dashboard.vue is the part most likely to regress when spec 0003 touches the same row.
**Suggested fix**: Add a `denyRead(page, 'Books Sales Invoice')` test asserting no Best sellers card, and one denying both for no row.

### 🟡 Slice-click test can pass without hitting a slice, `frontend/tests/ui/dashboard-best-sellers.spec.ts:150`
**Problem**: The click is at a guessed coordinate (`box.y + 10% height`); if it misses the ring the assertion (URL unchanged) still passes.
**Why it matters**: AC-11 is then only proven by the legend click.
**Suggested fix**: Target the ring element or assert the tooltip appears before checking the URL.

## Nits
- ⚪ `frontend/tests/ui/dashboard-best-sellers.spec.ts:96`, relative xpath `../../div[1]` couples the test to the centre slot markup; a test id or role would be steadier.
- ⚪ `frontend/src/pages/Dashboard/BestSellers.vue:58`, a rapid period change can let a slow earlier response overwrite a newer one; inherited from `BaseDashboardChart.loadData`, same as the sibling cards, so fix there if at all.
- ⚪ `docs/specs/0002-best-sellers-chart/verify.md`, several value-sourcing steps remain unchecked while scope.md marks Verify done; reconcile.

## Strengths
- Server method follows the v16 reports rule exactly: permission check first, `get_list` (no `ignore_permissions`, no raw SQL), Decimal arithmetic, rounding once, deterministic tie break, and `total` independent of the top-five cut.
- Python tests cover discounts both modes, currency (rate 2, 0, NULL), period edge at 23:30, returns, drafts/cancelled, ties, few/none; the permission test compares Books User and Cashier to Manager figures, which proves child rows are readable and not only that nothing throws.
- Card is a faithful, minimal copy of Expenses (translated strings, tokens only, shared states and retry), with an honest comment on the two-totals tradeoff.

## Test coverage
Python: `IntegrationTestBestSellers` (7 tests) and the permission test cover every spec rule except unknown period and YTD. Node: wrapper contract for `getBestSellers`. Playwright: 10 tests for content, period reload, empty, error/retry, layout left and right, phone card. Gaps are the minors above; no new logic is untested in a risky way.
