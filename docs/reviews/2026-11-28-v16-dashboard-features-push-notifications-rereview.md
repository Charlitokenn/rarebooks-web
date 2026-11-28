# Re-review, v16 push notifications (spec 0026), 2026-11-28

**Reviewed by**: Claude Sonnet 5.5 (author on a different model)
**Scope**: 43 files, branch vs 5aeb118 (feature commits only); re-review of commits 54f4b0d, 3ceff38, 67c6e90 against [the first review](2026-11-28-v16-dashboard-features-push-notifications.md)
**Verdict**: Changes requested

## Summary
Two of the three Majors are fixed well: the sign out ordering (the row delete now starts first and runs beside the subscription removal, with a test where `deleteToken` never answers) and the "notification code can fail the user's action" problem (a savepoint guard on all four hooks, which correctly lets deadlock and lock timeout through). The third is only partly fixed. The prefilter removes the item lock for items with no reorder level, but every item that does have a level still takes the item row lock and then a locking ledger SUM after the transaction has inserted its own ledger rows, which is the lock cycle described in the first review. The stress run (2 deadlocks in 2400 with push on, 0 in the next 2400) does not show it is gone, because the cause was never proven. All six Minors and two of three Nits from the first review are unchanged, as the fix commits did not touch them.

## Status of the first review's findings

| # | Finding | Status | Evidence |
|---|---|---|---|
| M1 | Low stock lock can deadlock stock submits | **Partly resolved** | `events.py:102-110` prefilters with a plain `get_all` (`track_item=1` and `reorder_level>0 or low_stock_notified=1`), sorted by name, so items without a level take no lock (the test `test_an_item_without_a_level_takes_no_lock` pins it). `_check_item` (`events.py:125-131`) and `_stock_on_hand` (`events.py:155`) are unchanged: for an item with a level, the item `FOR UPDATE` and then the ledger `SUM ... FOR UPDATE` still run in `on_submit` after `stock_posting.post` inserted this transaction's ledger rows. See the Major below. |
| M2 | Notification code unguarded in the submit transaction | **Resolved** (one caveat, see N2) | `never_blocks_the_action` (`events.py:28-47`) wraps `payment_submitted`, `pos_sale_paid`, `check_low_stock` and `item_saved`: `SAVEPOINT`, run, on a non deadlock/timeout `Exception` `ROLLBACK TO SAVEPOINT` then `log_error`. `QueryDeadlockError` and `QueryTimeoutError` exist in `frappe/exceptions.py:256,260` and are re-raised, which is right: a deadlock already rolled back the whole transaction, and a lock timeout means the user's own write is stuck. Tests: payment (`test_a_failure_while_building_the_push_never_fails_the_payment`) and stock (`test_a_failing_low_stock_check_never_fails_...`, which also asserts the flag write was undone). |
| M3 | Sign out can leave the row behind | **Resolved** | `pushNotifications.ts:188-208`: `Promise.allSettled([unregister(token), removeSubscription()])`. `unregister` calls `call(...)` synchronously (before its first await), so the request is on the wire before `deleteToken` is touched. Node test `sign out deletes the row even when Firebase never answers` asserts exactly one `unregister_device` call with a hung `deleteToken`. Residual: see Nit on a slow unregister. |
| m1 | Notification tap opens a second tab | **Open** | `service_worker.js:86-102` unchanged; still `focus()` + `navigate()` with an `openWindow` fallback. Still unobserved. |
| m2 | Sequential sends can outlast `JOB_TIMEOUT` | **Open** | `sending.py:113-151` unchanged (sequential, no total deadline, `_log_failures` not in a `finally`). |
| m3 | Failing subscription push retries and logs hourly forever | **Open** | `events.py:195-200` unchanged. |
| m4 | Duplicate token insert race | **Open** | no `DuplicateEntryError` handling anywhere in `notifications/`. |
| m5 | Low stock flag stale while push is off | **Open** | `check_low_stock` (`events.py:97`) and `item_saved` (`events.py:118`) still return before touching the flag when FCM is unconfigured. The prefilter adds one more shape of it: an item with `track_item=0` and a set flag is now skipped by transactions (it used to be cleared by `_check_item`); only `item_saved` clears it, and only while configured. |
| m6 | Amount and date format follow the submitter | **Open** | `events.py:73, 166` unchanged. |
| n1 | Generated type block not regenerated | **Open** | `books_item.py` has no `reorder_level` / `low_stock_notified`; the two new doctype classes are plain `Document` subclasses. |
| n2 | One Manager shop never gets its own alert | **Open** | unchanged, undocumented in the spec's Consequences. |
| n3 | `turn_push_off` writes `"None"` | **Resolved (not a bug)** | `frappe/installer.py:717-719` treats the string `"None"` as "delete the key". |

## Major
### 🟠 Low stock lock cycle remains for every item that has a reorder level, `frappe_books/notifications/events.py:125-131, 155`
**Problem**: the prefilter only shrinks who is exposed. For an item with `reorder_level > 0`, each stock submit still does, inside `on_submit` and after its own ledger rows are inserted: lock the item row, then `SELECT SUM(quantity) ... WHERE item = X FOR UPDATE`. Two concurrent submits of such an item can still form the cycle: A holds the item lock and its scan needs B's uncommitted ledger rows; B holds those rows and waits on the item lock. InnoDB picks a victim and the sale or receipt fails. The change in 67c6e90 now re-raises that error on purpose, so the user's action fails, which is what AC-10 forbids ("never fails the user's action") and what the first review flagged.
**Why it matters**: the stress numbers do not close it. Two deadlocks in 2400 is a rare event, so 0 in the next 1800 and 600 is also what an unchanged cause would give with decent probability, and the cause was not proven. If the stress items had no reorder level, the later runs would be clean only because the prefilter skipped them, which says nothing about items that do have one. The shops that set levels are exactly the ones this feature is for.
**Suggested fix**: remove the cycle by design rather than by exposure. Either (a) run the check in an after-commit job in its own short transaction: a plain `SUM` there sees committed data under REPEATABLE READ because the snapshot is fresh, and the flag flip becomes one conditional `UPDATE ... SET low_stock_notified = 1 WHERE name = X AND low_stock_notified = 0`, pushing only when one row changed (this also removes the stale snapshot issue in N3); or (b) take the item locks in `before_submit`/before `stock_posting.post`, in sorted order, so every transaction locks item rows before it inserts ledger rows. Then add the two-connection test the first review asked for, with the item given a reorder level above its stock, and run the stress test with levels set.

## Minor
### 🟡 N2: the guard reuses one savepoint name and never releases it, `frappe_books/notifications/events.py:37-44`
**Problem**: every guarded call issues `SAVEPOINT books_push_event`. In MariaDB a savepoint with an existing name replaces the old one. Today the hooks run one after another, never inside each other (I traced a POS sale: each counter payment's `payment_submitted` returns early and finishes, then `pos_sale_paid`, then the stock transfer's `check_low_stock`; `_check_item` and `_set_notified` use `db.set_value`, not a document save, so `item_saved` is not reached from inside another hook), so sequential reuse is fine. If a hook ever nests (for example a low stock check that saves an Item, which fires `item_saved`), the inner guard silently moves the outer savepoint forward and an outer failure then rolls back only part of its writes. Also the savepoint is never released after a success, so each call leaves one behind until commit.
**Why it matters**: latent only, but the failure mode is a half undone push write with no error. Cheap to rule out.
**Suggested fix**: use a name unique per call (as Frappe's own `frappe.database.savepoint` context manager does) and `release_savepoint` on success.

### 🟡 N3: the prefilter reads a REPEATABLE READ snapshot and can skip an item, delaying an alert, `frappe_books/notifications/events.py:102-108`
**Problem**: the plain `get_all` is a consistent read from the snapshot of the first read in this transaction, which can be old in a long request (a POS sale with many steps). If another user commits `reorder_level = 5` (or the flag change) after that snapshot, this transaction sees `reorder_level = 0, flag = 0`, skips the item, and never checks it. That other user's own `item_saved` checked stock before this transaction's rows were committed, so neither side alerts for this drop. The reverse direction is safe: when the snapshot says the flag is set or a level exists, `_check_item` re-reads with `FOR UPDATE`, which reads the latest committed row.
**Why it matters**: a missed or late low stock alert, not wrong data. The next stock transaction on that item re-checks (the flag is still 0 and the total is still at or below the level), so it self heals on the next movement; for a rarely moved item that could be long. The window is small, so Minor.
**Suggested fix**: it disappears with the after-commit design in the Major above. If the check stays in the transaction, do the prefilter read with `for_update` only on the item rows that pass, or accept and note it in the spec's Consequences.

### 🟡 N4: a persistent fault logs one Error Log row per transaction, and the flag write is rolled back with it, `frappe_books/notifications/events.py:44-45`
**Problem**: when the push work fails the same way each time (a bad translation for one recipient's language, a missing company currency), the savepoint rollback also undoes `_set_notified(item, 1)`, so every later stock transaction on that item tries again and writes another Error Log entry. Every payment writes one too. The title is the same each time, so Frappe groups them, but a busy POS site can fill the log with duplicates before anyone looks.
**Suggested fix**: fine to leave as is for a first release; if wanted, log at most once per hour per event (a cache key) and keep logging the first occurrence.

## Nits
- ⚪ `frontend/src/utils/pushNotifications.ts:190-194`, the 2 second cap still applies to `unregister_device` itself: on a very slow connection `logout` can be sent while the unregister is in flight and may be processed first, leaving the row. The request is now always sent first, so this is much narrower than before; just be aware the guarantee is "sent first", not "completed first".
- ⚪ `frappe_books/notifications/events.py:23-25`, the comment on `TRANSACTION_ERRORS` is good; consider noting that `QueryTimeoutError` leaves the transaction open (InnoDB rolls back only the statement) and the action fails by design, since a reader may wonder why it is not swallowed.
- ⚪ Carried over, unchanged: the type block in `books_item.py` and the two new doctype classes (first review n1), and the one Manager shop note (first review n2).

## Savepoint guard: points checked, no issue found
- **Logging inside a rolled back savepoint**: no. `rollback(save_point=...)` runs first, then `frappe.log_error`, so the log row is written after the rollback point and survives. If the whole user transaction later rolls back, the log goes with it, which is the same as any other Error Log entry written in that request.
- **Secrets in the log**: no. The hooks call only `fcm.is_configured()` (a `frappe.conf.get` of three keys, no service account object is built), and Frappe's traceback with context is off unless developer mode and then sanitises names containing `key`, `secret` and `token`. The Firebase key is read only on the job path, outside the guard.
- **Rolled back work that should not be**: the guard rolls back DB writes only (Frappe documents that rollback watchers do not run for savepoints). `notify` is the last call in each hook, so no after-commit enqueue is registered before a failure that is then rolled back.
- **Swallowing hiding real bugs**: it swallows any `Exception`, including a coding error in the hooks. The Error Log row is the only signal, and the tests do prove that row is written once. That is the intended AC-10 trade, but it makes the test gaps below matter more.
- **Locked sites**: a read only transaction accepts `SAVEPOINT`, and the lock blocks the writes before these hooks run, so no new failure there.
- **Lock order across items**: both the prefilter (`order_by name asc`) and `sorted(...)` give a stable item order, so two transactions on different items cannot cycle on item rows. The Major above is about item row against ledger rows, a different cycle.
- **`or_filters` semantics**: `filters AND (reorder_level > 0 OR low_stock_notified = 1)` as intended; `track_item = 0` items are no longer visited, which is only a problem in the flag cleanup case in m5.

## Strengths
- The guard separates "my push work failed" (undo and log) from "the transaction is gone" (re-raise), with the reason written next to the constant. That is the correct line, and the first fix attempt could easily have swallowed a deadlock and reported a save that was not there.
- The sign out fix keeps the AC-13 behaviour (a locked site still removes the browser subscription) and the new node test fails on the old ordering.
- The prefilter test asserts on `for_update` calls rather than on private helpers, so it pins the behaviour the spec cares about.
- The unreadable key fix (54f4b0d) fails the send cleanly into `FcmError`, and 3ceff38 adds the token exchange timeout and no-token cases; both stay inside AC-12 (no key or token in logs).

## Test coverage
Python 59, node 19 and Playwright 8 of 9 (the service worker push test is a known flake, tracked separately and unrelated). New tests cover the payment guard, the stock guard (including the undone flag), the no lock prefilter and the hung `deleteToken` sign out.

Still not covered:
- Two connections submitting stock for the same item with a reorder level at once. This is the AC-6 "two transactions at once send one push" test and the build plan's concurrency test, open since the first review, and it is the only thing that can show whether the Major above is real. A thread based test with `reorder_level` above the post transaction stock, repeated a few hundred times, would do.
- A deadlock or lock timeout inside a guarded hook propagating (a patch that raises `frappe.QueryDeadlockError` from `_stock_on_hand`, asserting the submit fails and nothing is logged as a push failure).
- The guard on `pos_sale_paid` and `item_saved` (only the payment and stock hooks have a failure test), and a sale that runs two counter payments plus a stock transfer in one transaction with a failure in the middle one, to pin the savepoint reuse behaviour.
- Carried over: duplicate token race, total send time over `JOB_TIMEOUT`, and the real notification tap.
