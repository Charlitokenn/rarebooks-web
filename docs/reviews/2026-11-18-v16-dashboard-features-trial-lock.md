# Review, v16 dashboard features (trial and read only lock, spec 0005), 2026-11-18

**Reviewed by**: reviewer model (author on a different model)
**Scope**: 37 files, branch vs origin/version-16 (subscription hunks only)
**Verdict**: Changes requested

## Summary
The change adds the 30 day clock, the Books Subscription single with a controller guard, a read only database transaction opened in before_request and before_job, a signed push and pull contract with the control site, and the banner, page and error mapping in the frontend. The design is sound: the database refuses the write, the allowlist is exact match and fails closed, the push check order is correct and the phase is derived, never stored. I found no way to write on a locked site outside the allowlist. The main concerns are a fail open default for a missing trial start, a pull path that skips the freshness and ordering protections the push has, and an unthrottled outbound call any user can trigger.

## Major
### 🟠 A missing `trial_started_on` silently means "day 1 today", so the site never locks, `frappe_books/subscription/clock.py:50`
**Problem**: `day_one` falls back to `self.today` when `trial_started_on` is empty. The field is required in the JSON, but the value can still be empty in practice: a site whose single row was never written (install hook skipped, a restore of a pre feature backup that then skips the post_model_sync patch, a failed patch), or a Singles row removed by hand.
**Why it matters**: This is a paywall. The failure direction is free access, forever, with no log and no banner, because day 1 moves forward every day. The spec says a managed site must start its clock at install or patch, so an empty value is a broken state that should not read as a healthy trial.
**Suggested fix**: On a managed, non exempt, unpaid site with no `trial_started_on`, treat it as broken: either start the trial lazily and persist it (through `state.start_trial`), or log an Error Log entry and treat the site as day 1 stored once, not as a rolling "today". Add a test for a managed site with an empty `trial_started_on`.

### 🟠 The pull path accepts a signed response with no freshness check and no binding to the request, `frappe_books/subscription/api.py:127`
**Problem**: `receive_state` enforces the 5 minute `issued_at` window (AC-11), but `pull_state` applies the response's `state.issued_at` through `apply_synced_state` with only the "newer than `last_synced_on`" rule. The response is signed over its body, but the body carries no echo of the request's `issued_at` or a nonce, and the response `issued_at` is never compared to now.
**Why it matters**: Any previously captured signed response that is newer than the last applied state can be replayed (for example over the plain http allowed in developer mode, or by a misbehaving proxy or cache in front of the control site), and a far future `issued_at` freezes `last_synced_on` ahead so later real pushes are ignored as stale. The same far future value is also reachable by clock skew on the control server. The window on pushes shows the spec already considers this a risk.
**Suggested fix**: In `pull_state`, require the response `state.issued_at` to pass `is_fresh`, and have the control site echo the request `issued_at` so the site can check it. Add a test where the stub returns a signed but old response.

### 🟠 Any logged in Books user can trigger an outbound control site call on every request, with a 10 second block, `frappe_books/subscription/api.py:46`
**Problem**: `get_subscription(refresh=True)` pulls for any caller with read on the single, including Books Cashier, and is on the lock allowlist. When the control site is down, the plans cache is empty and so every call from a manager also pulls again (`api.py:54`), since a failed pull caches nothing.
**Why it matters**: One user looping the call ties up web workers for up to 10 seconds each and sends repeated signed calls to the control site. This is a cheap denial of service on a hosted site and on the shared control site. It also means a down control site slows every Subscription page open by 10 seconds.
**Suggested fix**: Allow `refresh=True` only for `can_subscribe` callers, and add a short negative cache or a minimum interval (for example a 30 second cache key set on failure and after each pull). Add a test.

## Minor
### 🟡 Concurrent pushes can answer 400 and log a false "bad value", `frappe_books/subscription/api.py:122`
**Problem**: `apply_synced_state` reads the single without a lock, and `except frappe.ValidationError` also catches `TimestampMismatchError` from a concurrent save. The loser gets 400 and an Error Log entry, though the push was valid.
**Why it matters**: The control site may treat 400 as permanent and stop retrying, and a replay window race can let the older push win if both read before either saves.
**Suggested fix**: Read the single `for_update` (or take a short lock key) inside `apply_synced_state`, and catch only the validation errors that `_validated` raises.

### 🟡 `checkout_url` may be plain `http://`, `frappe_books/subscription/api.py:93`
**Problem**: The link sent to the browser is accepted with an `http://` scheme. The spec says outgoing calls are HTTPS only.
**Why it matters**: A payment redirect over http outside developer mode.
**Suggested fix**: Require `https://`, allowing `http://` only when `developer_mode` is on, as `control_url` does.

### 🟡 An invalid System Settings time zone breaks every request on a managed site, including login, `frappe_books/subscription/clock.py:120`
**Problem**: `ZoneInfo(...)` raises when the name is unknown to the installed tz data, and `lock_request` runs before auth, so every request returns 500, login included.
**Why it matters**: A locked out site with no UI way back. Unlikely, but the failure is total.
**Suggested fix**: Catch the error, log it once and fall back to UTC.

### 🟡 A real Frappe maintenance mode is shown as "Subscribe to make changes again", `frontend/src/utils/subscription.ts:34`
**Problem**: `InReadOnlyMode` is also raised by Frappe's own maintenance mode, and the client maps it by type only. On an unlocked site the notice then tells users to subscribe.
**Why it matters**: A misleading message during maintenance. The spec says to map by type, so the fix is to word the fallback, not to change the mapping.
**Suggested fix**: When the stored status is not locked, after the refresh shows it is still not locked, show Frappe's own message instead of the subscribe text.

### 🟡 The lock notice for the first refused write can show the fallback text, `frontend/src/web/api.ts:107`
**Problem**: `getLockError` starts the status refresh without waiting, so a site that turned read only overnight shows the generic fallback wording for that first error (not the dated unpaid trial text).
**Why it matters**: AC-8 asks every refused write to show the banner's text for the current phase.
**Suggested fix**: Await the refresh (it is an allowlisted call) before building the notice.

### 🟡 Untested risk paths, `frappe_books/tests/test_subscription_control.py`
**Problem**: No test covers a stale or far future signed pull response, concurrent pushes, an empty `trial_started_on` on a managed site, an invalid time zone, or `refresh=True` by a non manager.
**Why it matters**: These are the branches where the findings above sit.
**Suggested fix**: Add one test each when fixing the items above.

## Nits
- ⚪ `frappe_books/subscription/state.py:40`, a push with `issued_at` a few minutes ahead moves `last_synced_on` into the future, which makes later pushes look stale; clamp it to now when storing.
- ⚪ `frappe_books/subscription/api.py:25`, `plans_error` and `pull_error` mix a message string with `None`; return a small typed object for clarity.
- ⚪ `frontend/src/utils/subscription.ts:31`, `LOCK_DAY` and `TRIAL_LAST_DAY` duplicate server constants; send `days_left` in the status dict so the client has one source.

## Strengths
- The lock rests on the database, not on a list of checks: every write path I traced (insert, rename, save, submit, delete, whitelisted `db.set_value`, upload, legacy `cmd=`, lookalike paths) is refused or fails closed, and the allowlist is exact match plus one reviewed prefix.
- `receive_state` is ordered correctly: raw body bytes, constant time HMAC compare, site check, timezone aware `issued_at` window, strictly newer replay rule, a rate limit, 401 with no detail, and values validated before anything is applied.
- The controller guard on the single refuses Administrator, and the sync flag is cleared in a `finally`, with a test for it.
- Phase is derived from facts and today, so the lock starts at local midnight with no job; the check adds no query once the cache is warm.
- The client maps lock errors by exception type before the status map, so a 403 never becomes `ForbiddenError`, and a 503 of another type stays a generic error.

## Test coverage
The Python suite is thorough on the clock boundaries, the bypass matrix by role, the allowlist, jobs, push security, the guard and the retry state, and the node and Playwright tests cover the banner texts and a refused save. Gaps are listed in the last minor finding: the pull path, concurrency, the empty trial start, an invalid time zone and the refresh permission.
