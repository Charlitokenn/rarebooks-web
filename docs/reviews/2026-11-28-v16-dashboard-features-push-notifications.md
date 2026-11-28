# Review, v16 push notifications (spec 0026), 2026-11-28

**Reviewed by**: Claude Sonnet 5.5 (author on a different model)
**Scope**: 43 files, branch vs 5aeb118 (feature commits only)
**Verdict**: Changes requested

## Summary
Adds FCM push for payments, low stock and subscription phases: a Books Push Device doctype with own-row permissions, a Notification Settings single, an `fcm.py` that is the only module touching Google, after-commit enqueue, an hourly phase job, a service worker handler and a lazy loaded Firebase client. Secret handling (AC-12) and the failure logging (AC-10) are careful and well tested. The headline problems are in the low stock path, which locks inside the submitting transaction and has no isolation or concurrency test, and in the sign out ordering, whose 2 second cap can skip the one server call that matters.

## Major
### 🟠 Low stock check can deadlock stock submits and adds a lock to every stock transaction, `frappe_books/notifications/events.py:84-117`
**Problem**: `_check_item` takes `SELECT ... FOR UPDATE` on the item row, then `_stock_on_hand` runs `SUM(quantity) ... FOR UPDATE` over every ledger row of the item. This runs in `on_submit` after `stock_posting.post` has already inserted the transaction's own (uncommitted, implicitly locked) ledger rows. Two submits of the same tracked item at once: A inserts its rows and takes the item lock; B inserts its rows and waits on the item lock; A's locking sum must wait on B's uncommitted rows. That is a lock cycle, so InnoDB rolls one submit back with a deadlock error. The item row is also locked for every tracked item in every stock transaction, including items with no reorder level (the early return comes after the lock), so two sales of one SKU serialize until the first commits. This only runs when push keys are set, so it hits exactly the hosted sites.
**Why it matters**: a feature meant to never fail the user's action (AC-10) can fail a POS sale or receipt under ordinary concurrent load. I have not reproduced it, so treat the interleaving as plausible rather than proven, but nothing in the tests rules it out.
**Suggested fix**: do not lock in the submit path at all if you can avoid it. Options: make the flag flip a single conditional UPDATE (`set low_stock_notified = 1 where name = X and low_stock_notified = 0`, push only if one row changed) and read the sum without FOR UPDATE; or move the whole check to an after-commit job that runs it in its own short transaction. At minimum read `reorder_level`/`track_item` without a lock and take the lock only when the level is above 0. Then add a real two-connection test (see Test coverage).

### 🟠 Notification code runs unguarded inside the submit transaction, `frappe_books/frappe_books/doctype/books_payment/books_payment.py:46`, `frappe_books/inventory/transaction.py:50-58`, `frappe_books/frappe_books/doctype/books_item/books_item.py:95`, `frappe_books/frappe_books/doctype/books_sales_invoice/books_sales_invoice.py:196`
**Problem**: Only the HTTP send is isolated. Everything before the enqueue (`recipients`, `fmt_money`, `company_currency`, `_()` for each language, `format_quantity`, the item locks, the ledger sum) runs inside the user's transaction with no try/except. Any exception there (a bad translation file for one recipient's language, a missing company currency, a lock wait timeout or deadlock from the finding above) aborts the payment submit, the stock transaction, the item save or the POS sale after the money was taken.
**Why it matters**: AC-10 says sending never blocks or fails the user's action, and the scope's done-when repeats it. Today a broken recipient language setting can block a payment.
**Suggested fix**: wrap the calls from the controllers in one guard that logs the error with `frappe.log_error` (sanitised, like `_log_failures`) and carries on, or move message building into the after-commit job so only a small payload is enqueued. Keep database errors that poison the transaction (deadlock) in mind: a guard cannot rescue those, which is another reason to fix the first finding.

### 🟠 Sign out can leave the server row, and the old user's pushes, behind, `frontend/src/utils/pushNotifications.ts:119-125, 173-186`
**Problem**: `stopPush` removes the browser subscription first (Firebase `deleteToken`, which needs a network call to FCM, then `pushManager` unsubscribe) and only then calls `unregister_device`. `stopPushForSignOut` races the whole sequence against a 2 second timeout. If `deleteToken` is slow (mobile network, FCM slow), the timeout wins, `logOut` goes on to `call('logout')`, and the later `unregister_device` either never runs or runs after the session is gone and fails. The row stays, the subscription may still exist, and the next person on that browser receives the previous user's payment and stock alerts, which is what AC-4 exists to prevent. The Playwright test passes because the stub answers instantly.
**Why it matters**: privacy leak of business data on shared devices, on the path the spec calls out.
**Suggested fix**: send `unregister_device` first or in parallel with the subscription removal (`Promise.all`), so the server stops sending as soon as possible; keep removing the subscription as well for the locked site case (AC-13). Consider a test where `deleteToken` never resolves and the unregister call still reaches the server before `logout`.

## Minor
### 🟡 Notification tap probably opens a second tab instead of moving the open one, `frappe_books/pwa/service_worker.js:93-105`
**Problem**: `openBooks` finds an open client at `/books` or `/books/...`, focuses it and calls `WindowClient.navigate`. The worker's own comment (and `getServiceWorker` in the client) says the page at `/books` is outside the `/books/` scope, so that tab is not controlled; `navigate()` rejects for an uncontrolled client, and the catch then calls `openWindow`. Result: the old tab is focused and a new window opens at the link, on every tap. AC-11 says the open tab moves to the link. Tap handling was not exercised for real (no Firebase project), so this is from reading, not observed.
**Suggested fix**: when `navigate` is not possible, `postMessage` the link to the client and let the page route to it (the app already has a router), or open only the new window and skip the focus.

### 🟡 Sequential sends can outlast the 120 second job timeout, `frappe_books/notifications/sending.py:92-103`, `frappe_books/notifications/fcm.py:20`
**Problem**: each send has a 10 second timeout and sends are sequential. During a Google slowdown, 12 or more devices exceed the 120 second `JOB_TIMEOUT`; the job is killed before `_delete_dead` and `_log_failures` run, so there is no Error Log entry and dead rows are not removed. The hourly `send_now` path has no cap at all and can hold the scheduler worker for (devices x 10 s).
**Suggested fix**: bound the work (stop after a total deadline and log what was left), or send in a small thread pool, and make sure the log line is written in a `finally`.

### 🟡 A failing subscription push retries and logs every hour with no limit, `frappe_books/notifications/events.py:158-165`
**Problem**: when every send fails (a revoked key, Google outage) the phase is not stored, so each hourly run builds messages, tries and writes an Error Log entry again, indefinitely. Spec says "nothing is retried", but the job is its own retry loop here by design (AC-7); there is no ceiling.
**Suggested fix**: cap retries (for example give up after 24 attempts or one day, store the phase, log once) so a permanently bad key does not produce a log row an hour forever.

### 🟡 First registration of a token can race into a duplicate entry error, `frappe_books/notifications/devices.py:49-67`
**Problem**: the read-then-insert is not atomic. Two tabs of one browser starting together (the start up register) both see no row and both insert; the unique `token_hash` makes one fail with `DuplicateEntryError`. The start up path only logs it, but "Turn on" would show an error dialog.
**Suggested fix**: catch `frappe.DuplicateEntryError` on insert and fall through to the update branch.

### 🟡 Low stock flag stays stale while push is off, `frappe_books/notifications/events.py:48-62, 68-76`
**Problem**: `check_low_stock` and `item_saved` return early when FCM is not configured, so `low_stock_notified` is not maintained. A site that turns push on later starts with stale flags: an item already low and never flagged alerts on its next transaction (fine), but an item flagged earlier and since restocked stays flagged and will not alert on its next drop.
**Suggested fix**: maintain the flag regardless of configuration (it is cheap once the lock is dropped) and only skip the enqueue.

### 🟡 Amount and date formats follow the submitter, not the recipient, `frappe_books/notifications/events.py:44, 64, 197`
**Problem**: `fmt_money`, `format_quantity` and `formatdate` are evaluated once in the submitter's context and then reused for each language group, so a Manager in another locale gets the submitter's separators and date format. The text is translated per recipient (AC-9) but the numbers are not.
**Suggested fix**: build the numbers inside `build(lang)` under the recipient's number and date format, or accept and document it.

## Nits
- ⚪ `frappe_books/frappe_books/doctype/books_item/books_item.py:30-60`, the auto generated type block was not regenerated for `reorder_level` and `low_stock_notified` (`export_python_type_annotations = True`); same for the two new doctype `.py` files.
- ⚪ `frappe_books/notifications/events.py:46`, the comment "The one who took the money already knows." is fine, but `exclude_user=frappe.session.user` also silently drops the only Manager's own alert on a one-Manager shop; worth a line in the spec's consequences.
- ⚪ `frappe_books/tests/push.py:30-40`, `turn_push_off` writes the string `"None"` to site config via `update_site_config`; confirm that really clears the key rather than setting a truthy string (the helper is only used by tests, but a stale truthy value would silently keep push on).

## Strengths
- Secret handling is thorough: the service account is read only in `fcm.py`, `raise ... from None` keeps the key out of tracebacks, logs carry only HTTP status and FCM code, the boot block never touches the key, and tests assert the Error Log and boot contain none of it.
- `has_permission` follows `user` rather than `owner`, plus a matching `permission_query_conditions`, plus tests that a user cannot list, edit or delete another user's row through the API.
- The hourly job is correct on a locked site: it sends inside the scheduled job, stores the phase only after a successful send, treats `locked` and `lapsed` as one tag, handles the PayPal `subscription_starts_on` case as a final skip, and `_delete_dead` / `_log_failures` tolerate `InReadOnlyMode`.
- The service worker's `bookLink` is sound: it resolves through `URL`, so `..` segments, protocol relative URLs and other origins are all rejected, and a push without title or valid link shows nothing.
- `register_device` and `unregister_device` check the server side right (push configured, real email rule, role, lock), are type annotated, and unregister only deletes the caller's own row.
- Firebase is loaded lazily with a stubbable loader, the sign out ordering is covered by a Playwright test, and strings use `t` / `_()` with `{0}` placeholders.

## Test coverage
Coverage is broad: 56 Python, 18 node and 9 Playwright tests cover the AC list, including FCM error mapping, per-language messages, POS split tender, the phase job's first run, PayPal skip and locked cases, stale device removal and permission checks.

Gaps:
- AC-6 "Two transactions at once send one push, not two" and the build plan's concurrency test are not tested. Every test in `IntegrationTestLowStockPushes` runs on one connection, so neither the flag race nor the deadlock risk in the first finding is exercised. Add a two-connection test (two threads or two DB connections) that submits stock for the same item at once.
- No test for an exception inside the notification code during a submit (second finding): assert the payment or stock submit still succeeds when `recipients` or `fmt_money` raises.
- The sign out Playwright test uses an instant stub; add a case where `deleteToken` hangs, so the 2 second cap is exercised (third finding).
- No test for a duplicate token insert race, and none for a job whose total send time exceeds `JOB_TIMEOUT`.
- Not covered by anyone, as stated in the brief: real FCM delivery and the notification tap, so the `notificationclick` finding is unverified.
