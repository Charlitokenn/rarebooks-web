# Review, v16-dashboard-features, 2026-11-12

**Reviewed by**: Sonnet 5.5 (fresh reviewer; author model not stated)
**Scope**: 21 files (17 tracked, 4 untracked), uncommitted
**Verdict**: Approve with nits

## Summary
Adds a "Dashboard Accounts" child table to Books Accounting Settings, a controller validation for it, a read seam in `_dashboard_accounts()` that lists picked leaf Asset/Liability accounts with a silent Cash/Bank fallback, a Settings help line, a card gate on Settings read, and a "Choose accounts" button. It matches spec 0003 closely, keeps every read on `get_list` or an explicit permission check, and is well tested. No blockers or majors; only small edge cases.

## Minor
### 🟡 Duplicate check ignores accounts that merge-rename produced, `books_accounting_settings.py:~115`
**Problem**: The duplicate check is by exact account name over rows with a value. That is fine, but a stale duplicate already stored (spec notes rename-merge) makes every later settings save fail with "more than once" until the user opens the table, including saves of unrelated settings.
**Why it matters**: Contradicts the intent that a stale pick "does not block saving other settings"; the message does not say where to look.
**Suggested fix**: Accept as documented, or make the message name the Dashboard Accounts table so the user knows what to fix.

### 🟡 Hidden fallback can mislead the Total, `reports/dashboard.py:~150-175`
**Problem**: When every pick is stale the card silently switches to Cash and Bank, and the Total changes meaning (also net of liabilities once one is picked). Spec accepts this as a tradeoff.
**Why it matters**: A manager may read the Total as cash on hand. Already tracked in the spec follow-ups, so noted only.
**Suggested fix**: Keep the follow-up open; no change needed to merge.

### 🟡 Two reads of the same settings per card load, `reports/dashboard.py:_dashboard_accounts`
**Problem**: `has_permission` plus two `get_list` calls run on each card load before the ledger query.
**Why it matters**: Small, bounded cost (a handful of rows), but it is on the dashboard hot path.
**Suggested fix**: None required; consider only if the dashboard load time is measured to matter.

## Nits
- ⚪ `reports/dashboard.py` picked query: `filters` repeats `parenttype`, which `parent_doctype` already scopes; harmless, spec-mandated.
- ⚪ `tests/ui/helpers/session.ts`: `withoutBootRights` parses boot with `indexOf(';\n')`; brittle if the boot template changes, but isolated to tests.
- ⚪ `books_dashboard_account.json`: `sort_order` DESC on a child table has no effect since the card sorts by `lft`.

## Strengths
- Single source for allowed root types (`DASHBOARD_ROOT_TYPES`) used by the save rule and the read filter, with a Python test that keeps the picker `link_filters` in step.
- Stale-row handling is matched by row name, with tests for the "edited onto a removed row's stale account" case; reads never use `ignore_permissions`, and the 403 path is tested with a real restricted user.
- Frontend gates the card on Settings read and the button on write, and tests the loading/error states of the button.

## Test coverage
Strong: Python covers list order, liability sign and total, fallback, stale picks, equity move, delete block (LinkExistsError), permission gate, save rules, and the link_filters mirror. Node covers the row model (no Create). Playwright covers settings flow, button in every card state and mobile. Reported results: Python and node pass; Playwright 29/31 with 2 older unrelated failures. No untested new branching logic found.
