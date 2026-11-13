# Review of the account balances card, version-16, 2026-11-12

**Reviewed by**: Sonnet 5.5 (author on Opus)
**Scope**: 11 files plus docs, commit range efbe395 and 980e90c on version-16 (already merged). Files read at HEAD; findings focus on code those two commits introduced. Spec 0003 changes (fd61928, 33eb4fb) were not re-reviewed.
**Verdict**: Changes requested

## Summary

Adds a whitelisted `get_cash_balances` (ledger-read check first, `get_list` for both doctypes, grouped query, rounded balances and Total computed server side), an `AccountBalances.vue` table card with a `loadId` stale-load guard, and a new dashboard row, with thorough Python, node and Playwright tests. The server side matches the spec closely and is clean. The headline issue is that 980e90c replaced the spec'd `fyo.format(asOf, 'Date')` subtitle with a hard-coded Luxon format, which contradicts AC-3 and bypasses the user's date format setting, and the test added alongside cannot catch it.

## Major

### 🟠 Subtitle date ignores the app date format, contradicts AC-3, `frontend/src/pages/Dashboard/AccountBalances.vue:163`
**Problem**: 980e90c changed the subtitle from `fyo.format(this.asOf, 'Date')` to `DateTime.fromISO(this.asOf).toLocaleString(DateTime.DATE_MED)`. AC-3 and the spec's value-sourcing table require `fyo.format(as_of, 'Date')`. The Luxon call uses the browser locale and a fixed medium style, so it ignores the Books date format setting. Every other date on the dashboard and in the General Ledger the row links to uses `fyo.format`. It also adds a Luxon import to a card that had no use for it.
**Why it matters**: A user who configured, for example, `dd/MM/yyyy` sees "Dec 15, 2031" on this card and a different format everywhere else. The card is the cash-on-hand figure, where the date's meaning matters. The change was not recorded as a spec deviation. The commit message calls it "improved date formatting", so it looks deliberate but undocumented.
**Suggested fix**: Restore `fyo.format(this.asOf, 'Date')`. If the Luxon format was chosen on purpose (for example because `fyo.format` misrendered the ISO string), record that in the spec and fix the root cause instead. Add a test that fixes the date format setting and asserts the exact subtitle text.

## Minor

### 🟡 Subtitle test cannot detect a wrong or invalid date, `frontend/tests/ui/dashboard-account-balances.spec.ts:79`
**Problem**: The only check is `getByText(/^As of /)` and `not.toHaveText('As of today')`. That passes for "As of Invalid DateTime" and for any format, so it let the AC-3 deviation above through. The "covers: AC-3" skeleton test only checks the "As of today" placeholder.
**Why it matters**: AC-3 has no real assertion of the formatted date.
**Suggested fix**: Assert the exact string produced for the mocked `as_of` of 2031-12-15, derived from `fyo.format` in the page or from a fixed date format setting.

### 🟡 Retry gives no feedback and keeps the error showing, `frontend/src/pages/Dashboard/AccountBalances.vue:174`
**Problem**: `loadData` clears `error` only on success, and `isLoaded` is never reset. Clicking "Try again" while the server is slow leaves `ChartLoadError` on screen with no loading state. A second failure looks identical, as if the click did nothing. The base class `loadData` sets `error = null` first. The spec prescribes this behaviour (success sets `error = null`), but the consequence is not covered by AC-10.
**Why it matters**: Users may click Try again repeatedly. Each click starts a new load that cancels the previous one through `loadId`, so repeated clicks can keep discarding a response that is about to arrive.
**Suggested fix**: Decide the retry UX explicitly. Options are to show the skeleton while retrying from an error, or to disable the retry button while a load is pending. Update AC-10 to match.

### 🟡 AC-8 account-read branch is untested, `frappe_books/tests/test_permissions.py:149`
**Problem**: The tests cover Cashier (no ledger read, so denied) and Manager (allowed). The spec claims a user with ledger read but no Account read also gets `PermissionError` through `get_list`, but no test creates that case.
**Why it matters**: That claim is the stated reason the method has no explicit Account check. A future change to `_dashboard_accounts` (feature 4 replaces it) could silently drop the guarantee.
**Suggested fix**: Add a case with a role or user that has ledger read and no Account read, asserting `PermissionError`. Alternatively, check Account read explicitly beside the ledger check.

### 🟡 Fixed sleeps in the overlap tests, `frontend/tests/ui/dashboard-account-balances.spec.ts:168`
**Problem**: "A slow older load does not overwrite a newer one" delays the first response with `setTimeout(1500)` and then `waitForTimeout(2000)`. The later stale-failure test also uses `waitForTimeout(500)`. The same file defines a `gate()` helper that does this deterministically.
**Why it matters**: Slower CI makes the test either flaky or vacuous, and it adds about 2 s per run.
**Suggested fix**: Convert the older test to `gate()` and wait on the response, as the newer tests do.

### 🟡 Dark-mode and RTL checks from the plan have no test, `frontend/tests/ui/dashboard-account-balances.spec.ts`
**Problem**: The spec's layout scenario lists "dark mode uses no fixed colors" under AC-11. Only the left-half and phone-card cases exist.
**Why it matters**: Low risk, since the classes are tokens, but the plan item is silently dropped.
**Suggested fix**: Add a small token-only assertion, or note the manual check in verify.md.

## Nits
- ⚪ `frontend/src/pages/Dashboard/Dashboard.vue:57`, the inner `v-if="canRead.ledger && canRead.accounts"` repeats the wrapping template's condition (spec-prescribed). It will not be removable once Best sellers widens the outer gate, so it is fine, but a one-line comment would say why.

## Strengths
- `get_cash_balances` follows the spec exactly: permission check first, `get_list` for both doctypes with no raw SQL or `ignore_permissions`, `limit_page_length=0`, an empty-list short circuit, rounded rows, and a Total summed from the rounded rows so the invariant holds.
- The `loadId` guard is correct on both the success and failure paths (a stale failure does not log), and is covered by dedicated gated Playwright tests.
- Python tests cover the leaf/group/expense filter, chart order, the future-dated and reverted cutoff, an empty account and an overdrawn account. The permission test adds a real Books Cashier user.
- Translated strings use the `t` tag. The styling is RTL-safe and token-only. The layout handles mobile and desktop.

## Test coverage
Test signal is configured. Server logic is well covered (happy path, cutoff, zero and negative, permissions). The node test covers the client call shape. Playwright covers content, colors, period independence, link, empty, error and retry, scrolling, overlapping loads, skeleton, reload-keeps-rows, failed reload and layout. Gaps: the formatted subtitle date (AC-3), the Account-read-only denial (AC-8), dark mode (AC-11), and the fixed-sleep timing noted above.
