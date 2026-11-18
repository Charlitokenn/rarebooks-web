# 0007. Lock hardening

**Date**: 2026-11-18
**Status**: Proposed

Decision history: [rationale.md](rationale.md). Refines spec [0005](../0005-trial-read-only-lock/index.md), which stays the record of how the trial clock and the read only lock work.

## Summary

This closes the minor findings from the fresh model review of the trial and read only lock (spec 0005). Two pushes from billing at the same moment no longer fail, a payment link must be https, a broken time zone setting falls back to UTC instead of breaking every page, and a refused save always shows the right words: the subscription text when the site is locked, a short maintenance text when Frappe itself is read only for an update. It also makes the lock tests independent of what the test site was left in. No new data is stored.

## Requirements

**User stories**:
- As the operator, I want billing's updates applied correctly even when two arrive together, so a paid site is never left locked by a timing accident.
- As a customer, I want a refused save to tell me the real reason (my subscription or a short maintenance window), so I know whether to pay or just wait.
- As the operator, I want a bad time zone setting to degrade to UTC and tell me once, not take the whole site down.
- As a developer, I want the lock tests to pass no matter what state the test site is in.

**Acceptance criteria**:
- **AC-1**: Two valid signed pushes for the same site that arrive at the same moment both answer 200 (`applied` or `ignored`). Afterwards the stored facts equal the push with the newer `issued_at`, and no "Books billing: receive_state refused a bad value" Error Log row is written for either.
- **AC-2**: A signed push that carries a bad value still answers 400 and writes one "refused a bad value" Error Log row. A push that fails for any other reason (a database error, say) answers a server error (500), writes no "bad value" row, and changes nothing, so the control site retries it. A pull follows the same split: a bad value logs "get_state sent a bad value" and gives the Retry state; any other failure is not logged as a bad value.
- **AC-3**: A checkout started while a push is applied never fails with a server error: `mark_checkout_started` takes the same row lock. Outside developer mode, `start_checkout` refuses a `checkout_url` from the control site that doesn't start with `https://`: it throws "Couldn't reach billing. Try again.", writes one Error Log row "Books billing: create_checkout sent a link that isn't https", and leaves `checkout_started_on` unchanged. With `developer_mode` on, an `http://` link is accepted, as `control_url` already allows.
- **AC-4**: When System Settings `time_zone` names a zone the server doesn't know, the clock uses UTC. Every request keeps working (login included), the lock still applies by UTC days, and at most one Error Log row "Books subscription: unknown time zone {0}, using UTC" is written per hour.
- **AC-5**: When a write is refused with `InReadOnlyMode` and the fresh status says the site is not locked (Frappe's own maintenance mode with `allow_reads_during_maintenance` on), the notice reads "This site is being updated and is read only for a few minutes. Try again shortly." It never asks to subscribe. In full maintenance (reads not allowed) Frappe stops every request before this app runs, with `SessionStopped` (503); the status call fails too, and the generic error shows. That case is out of scope.
- **AC-6**: When a write is refused with `InReadOnlyMode`, or with `SiteLockedError` while the browser's stored status says the site is open, the client waits for a fresh status (AC-7) before it builds the notice, so the first notice already shows the current phase's text from spec 0005 AC-8. If that status call fails, the notice falls back to "This site is read only. Subscribe to make changes again.". `SiteLockedError` always shows the lock notice.
- **AC-7**: `get_subscription(with_plans=False)` returns the status dict without `plans` or `plans_error` and never calls the control site, for every role that can read it. It is allowed on a locked site, like every `get_subscription` call.
- **AC-8**: The suite covers concurrent pushes (AC-1), the push error split (AC-2), the https rule (AC-3) and an unknown time zone (AC-4). `test_is_locked_reads_nothing_on_an_unmanaged_site` and `test_a_bad_value_answers_400_and_changes_nothing` pass whatever the test site's `books_control_url` and `auto_renews` were. A `clear_trial_start()` helper empties `trial_started_on`, and spec 0005's verify.md Milestone 6 setup uses it.

## Decision

**Chosen option**: fix each finding in place, inside the existing `frappe_books/subscription/` modules and `src/utils/subscription.ts`, with no new storage and no new infrastructure.

- Pushes and pulls are serialized by a database row lock on the single's rows, taken in the same transaction as the save.
- Only validation errors from checking a push's values answer 400; anything else is a 500.
- A non https checkout link is treated like an unreachable control site.
- An unknown time zone falls back to UTC with an hourly Error Log row.
- The client awaits a status only `get_subscription` call before building the first lock notice, and shows its own maintenance text when the fresh status says the site is not locked.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**: no change. Books Subscription keeps its fields from spec 0005. No new site_config key.

**State transitions**: no change to spec 0005's phase table. The only new client state is "maintenance": a refused `InReadOnlyMode` write while the fresh status has `locked: false`. It is shown, not stored.

**API surface** (changes only; everything else is as in spec 0005):

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `frappe_books.subscription.get_subscription` | GET, POST | `refresh: bool = False`, new `with_plans: bool = True`. With `with_plans=False` it never pulls and never reads plans, whatever `refresh` says | the status dict; `plans` and `plans_error` only when `with_plans` and the caller can subscribe | logged in, read on Books Subscription (allowlisted on a locked site) | 403 without read |
| `frappe_books.subscription.receive_state` | POST | unchanged | `{"result": "applied"}` or `{"result": "ignored"}` | unchanged | 401 as before; 400 only for a bad value (`InvalidPushError`, raised by the value checks in `state.py`); 500 for any other failure, rolled back |
| `frappe_books.subscription.start_checkout` | POST | unchanged | `checkout_url`, now always `https://` outside developer mode | unchanged | 417 "Couldn't reach billing. Try again." also when the link isn't https |

**Server internals**:
- `state.apply_synced_state` reads the single with `frappe.get_doc(DOCTYPE, DOCTYPE, for_update=True)` (Frappe's `get_singles_dict(for_update=True)`: a locking read of the latest committed `tabSingles` rows, not the cache and not the transaction's older snapshot), compares `issued_at` with `last_synced_on`, and saves. A second push in another worker waits on that read until the first commits, then sees its result and applies or answers `ignored`. A plain `frappe.get_single` followed by a separate lock is not enough: under MariaDB's repeatable read it can still return the old row, and the save then fails Frappe's timestamp check. The save rewrites the single's rows (`update_single` deletes and inserts them), which is fine because every writer takes the locking read first.
- `state.mark_checkout_started` uses the same locking read, so a checkout and a push never collide.
- The lock is taken after any control site call has returned (the pull calls billing first, then applies), so it is held only through the apply and the commit, never across a network wait.
- `InvalidPushError(frappe.ValidationError)` with `http_status_code = 400` moves from `api.py` to `state.py`. `_date_or_none`, `_choice` and `_check` raise it (with the same messages, through `frappe.throw(..., InvalidPushError)`). `receive_state` catches only `InvalidPushError` around the apply, logs it and answers 400; every other exception propagates, so Frappe rolls back and answers 500. `pull_state` likewise catches only `InvalidPushError` for its "bad value" log; any other error propagates to `_pull_and_report`, which still turns a `ControlSiteUnreachable` into the Retry state and lets anything else be a server error.
- `_request_checkout` uses the same https rule as `control_url`: `https://` always, `http://` only with `developer_mode`. A refused link writes the Error Log row of AC-3 (with `defer_insert=True`) and throws the unreachable message, before `mark_checkout_started`.
- `clock.site_zone()` catches any exception from `ZoneInfo(name)` (an unknown name, a directory name like "America", a malformed one) and returns UTC. It logs once per hour: it claims the cache key `books_subscription_bad_time_zone` with Redis SET NX and a 3600 second expiry (as `_claim_pull_window` does), and writes the Error Log row with `defer_insert=True` only when it won the claim, since a locked request is already read only. Every caller (the lock hooks, boot, `get_subscription`, the clock) goes through `site_zone()`, so all of them are covered. The lock hooks call it before login, so it must never raise.

**Client internals**:
- `refreshSubscriptionStatus({ pull = false, withPlans = true } = {})` replaces the boolean argument. `pull` sends `refresh: true`; `withPlans: false` sends `with_plans: false`. A status fetched without plans keeps the `plans` and `plans_error` already in `subscriptionStatus`, so the Subscription page doesn't lose them. Every caller and test of the old `refreshSubscriptionStatus(true)` moves to `{ pull: true }`.
- `getServerError` is used only by `toBooksError` (in `call`, `src/web/api.ts`) and by `request` (`src/frappe/api.ts`). Both run inside async functions, so `toBooksError` becomes async and both callers await a fresh status before building a lock type error: always for `InReadOnlyMode`, and for `SiteLockedError` only when the stored status is not locked. `getServerError` itself stays synchronous and takes the status to use.
- The status call is made with a flag that skips this wait (so a lock type error on the status call itself can't start another one), and refusals that arrive together share one in flight status fetch.
- `getLockNotice` gets a maintenance branch: error type `InReadOnlyMode` and a fresh status with `locked: false` gives the AC-5 text. `SiteLockedError` keeps the lock notice for whatever phase the status shows, falling back to the generic text. If the status call fails, the stored status is used.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| push or pull apply | which push wins | the row lock order, then `issued_at` compared with `last_synced_on` read after the lock |
| `receive_state` | 400 vs 500 | the exception type: `InvalidPushError` from `_validated` → 400; anything else → 500 |
| `start_checkout` | whether the link is accepted | `checkout_url` starts with `https://`, or with `http://` and `frappe.conf.developer_mode` is set |
| clock, every request | the zone | System Settings `time_zone` if `ZoneInfo` knows it, else UTC (also UTC while empty, as before) |
| Error Log, bad zone | whether to log now | this call won the Redis SET NX claim on `books_subscription_bad_time_zone` (kept 3600 seconds) |
| lock notice | lock, maintenance or fallback text | the error type plus the fresh status from `get_subscription(with_plans=False)` (always for `InReadOnlyMode`; for `SiteLockedError` only when the stored status is open); the stored status if that call fails |
| `subscriptionStatus` after a status only fetch | `plans`, `plans_error` | kept from the previous value, since the fetch carries none |
| maintenance text | the words | fixed, translated with `t` (AC-5) |
| `get_subscription` | plans or not | the `with_plans` input, then the caller's roles as before |

**Key invariants**:
- Every change to Books Subscription from a push or a pull happens while holding the row lock, so the forward only `last_synced_on` rule (spec 0005) can't be beaten by timing.
- Building a lock notice never waits on the control site.
- The lock check never raises because of a setting; a bad zone degrades to UTC.

**Security model**: unchanged from spec 0005. `with_plans` only narrows what `get_subscription` returns. The https rule closes a payment redirect over plain http.

**Configuration required**: none.

**Critical test scenarios**:
- Two pushes at once: two threads each send a signed push through the existing `push` helper, with `issued_at` set through `signed_push`'s state (one older, one newer). A `threading.Barrier` releases them together, and a patched `set_facts` sleeps briefly inside the apply, so the pushes truly overlap. Both answer 200, the facts equal the newer one, the second push's apply started only after the first committed (recorded times), and there's no "bad value" row. Without the locking read the test fails with a 400. Verifies **AC-1**.
- Push errors: a bad provider gives 400 and one log row. Patching `frappe_books.subscription.state.save_facts` to raise `frappe.QueryDeadlockError` gives a 500 response from the test client, no "bad value" row (Error Log rows flushed with `frappe.deferred_insert.save_to_db()` before counting), and no change. The same patched error in a pull is not logged as a bad value. Verifies **AC-2**.
- Checkout during a push: `mark_checkout_started` while a push holds the lock waits and then saves; neither fails. Verifies **AC-3**.
- Checkout link: a stub answering `http://pay.example.com` with `developer_mode` off throws the Retry message, writes one log row, and leaves `checkout_started_on` empty. With `developer_mode` on, the same link is returned. Verifies **AC-3**.
- Unknown zone: set `time_zone` to "Mars/Olympus" and then to "America" with `frappe.db.set_single_value("System Settings", ...)` and `frappe.clear_cache()` (a normal save rejects the name). Each gives UTC days; on a locked site an insert over HTTP is still refused while a real HTTP login (`/api/method/login`) answers 200; three requests write one log row after flushing. Verifies **AC-4**.
- Client notice (node, faking `get_subscription` by URL as `tests/subscription.test.mjs` already does): a 503 `InReadOnlyMode` with a fresh status of `locked: false` gives the maintenance text, even when the stored status said locked. A first refusal with a stale open status fetches `with_plans: false` and shows the dated lock text. A failed status call gives the fallback. A 403 `SiteLockedError` always gives the lock notice. Two refusals at once make one status call. A status only fetch keeps the stored plans. The two existing tests that assume fire and forget ("a 503 InReadOnlyMode gives the lock notice", "a lock refusal while the browser thinks the site is open fetches the status") are updated to the awaited behavior. Verifies **AC-5**, **AC-6**.
- Status only: `get_subscription(with_plans=False)` as a manager with no cached plans makes no control site call and returns no `plans` key. Verifies **AC-7**.
- Isolation: the two named tests pass after the site was left hosted with `auto_renews = 1`. Verifies **AC-8**.

## Build plan

Tracer Bullet: each slice runs end to end with its tests before the next one starts.

**Milestone 1: Server hardening**
1. The locking read in `apply_synced_state` and `mark_checkout_started`; move `InvalidPushError` to `state.py` and raise it from the value checks; narrow the catches in `receive_state` and `pull_state`. Tests: concurrent pushes, a checkout during a push, the error split for push and pull. Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-8**.
2. The https rule for `checkout_url` in `_request_checkout`, with tests for both developer mode settings. Satisfies **AC-3**, **AC-8**.
3. UTC fallback and the hourly log in `site_zone`, with the unknown zone tests (clock and real HTTP). Satisfies **AC-4**, **AC-8**.

**Milestone 2: The right notice on the first refused write**
4. `with_plans` on `get_subscription`, with a Python test that it never pulls. Satisfies **AC-7**.
5. `refreshSubscriptionStatus({ pull, withPlans })` with plans kept on a status only fetch, and its callers moved over; async `toBooksError`; await the fresh status in `call` and `request` (with the no wait flag and the shared in flight fetch); the maintenance branch and the fallback in `getLockNotice`; node tests for each case, and the two existing tests updated. Satisfies **AC-5**, **AC-6**.

**Milestone 3: Tests that don't depend on the site**
6. `clear_trial_start()` in `frappe_books/tests/subscription.py`. The two order sensitive tests set `books_control_url` (through `managed_site`) and `auto_renews` themselves. Fix spec 0005 verify.md's Milestone 6 setup line to use the helper. Satisfies **AC-8**.

## Consequences

**Positive**:
- A paid site can't stay locked because two billing updates crossed, and a control site outage or database hiccup is retried instead of dropped as "bad value".
- A customer sees the true reason for a refused save, even on the first try after midnight, and is never told to pay during maintenance.
- A typo in the time zone setting can't lock everyone out of the site.

**Negative / tradeoffs**:
- A push waits for any other push, pull or checkout holding the row lock. The lock is taken only after billing has answered, so the wait is the length of another apply and commit, a few milliseconds, never a network call.
- Every `InReadOnlyMode` refusal, and the first `SiteLockedError` after the browser's status went stale, costs one extra request before the notice shows. It is a cached read, so it is quick, but it isn't free.
- With an unknown zone, day boundaries follow UTC, so the lock can start a few hours off local midnight until someone fixes the setting. The hourly log row is the only signal.
- `get_subscription` gains a second flag, so callers have to know which one they want.

**Neutral**:
- No schema change, no patch, no new site_config key.
- Spec 0005 keeps its content; this spec only refines it. `frappe_books/subscription/AGENTS.md` should note the row lock and the new flag (for `/sync`).

## Follow-up

- [ ] When the control site is built (feature 8), have it treat a 500 from `receive_state` as retryable and a 400 as final, matching AC-2.
- [ ] The three nits from the same review stay in the scope's Deferred list (clamp a future `issued_at`, a typed `plans_error`, send `days_left`).
