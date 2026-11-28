# notifications (push notifications, spec 0026)

## Overview

Push notifications to phones and computers through Firebase Cloud Messaging (FCM) HTTP v1, with one Firebase project shared by every hosted site. Books Managers and System Managers get a push for a received payment (one per POS sale), an item dropping to its reorder level, and the subscription nearing or reaching its end. Governing spec: [docs/specs/0026-push-notifications/index.md](../../docs/specs/0026-push-notifications/index.md).

## Key files

| File | Owns |
|---|---|
| `fcm.py` | The only module that talks to Google: the service account JWT, the OAuth token exchange (cached per site in Redis), and `send` returning `sent`, `dead` or `failed` (an `Outcome` carrying the HTTP status and FCM error code) |
| `devices.py` | Books Push Device: `register_device` and `unregister_device` (whitelisted), the `books.push` boot block, the own row permission hooks, the 10 device cap, and the daily 90 day cleanup |
| `sending.py` | Recipients (enabled Books Manager and System Manager users, by language), `notify` (queues `send_job` after commit), `send_now` (inside a scheduled job), `send_job`, `event_enabled`, and `store_default_events` |
| `events.py` | The four event hooks (payment, POS sale, low stock, item save) behind `never_blocks_the_action`, and the hourly `notify_subscription_phase` job |
| `../pwa/service_worker.js` | Shows each push (`push`) and opens its link on a tap (`notificationclick`) |
| `../tests/test_push_notifications.py`, `../tests/push.py` | Python tests, and `turn_push_on` / `turn_push_off` for the browser tests |

## Conventions

- Only `fcm.py` talks to Google. Tests patch `fcm.send`, `fcm.access_token` or `fcm.requests.post`, never the network.
- `books_fcm_service_account` holds a private key. It is read only in `fcm.py`, and it never reaches a response, the boot, a log or the Error Log. Failures carry only the HTTP status and FCM's error code, and signing errors are raised `from None` so the error that saw the key is not chained.
- Every failure inside `fcm.py` becomes `FcmError`. `send_job` logs once per job and never raises; nothing is retried.
- Event hooks run inside the user's transaction under a savepoint (`never_blocks_the_action`): any error undoes only the push work and is logged once, so the payment, stock transaction, item save or POS sale still saves. A deadlock or lock timeout is re-raised, since the whole transaction is already gone.
- Payment and low stock pushes are queued with `enqueue_after_commit=True` on the `short` queue (timeout 120 s). Subscription pushes send inside the hourly scheduled job, because a locked site leaves only scheduled jobs writable.
- The low stock check locks the item row, then reads the ledger total with a locking read: MariaDB runs REPEATABLE READ, so a plain read could miss a sale another transaction just committed. Items with no reorder level and no flag set are skipped with a plain read and take no lock.
- `last_subscription_phase` and `low_stock_notified` are written with `set_single_value` / `set_value(..., update_modified=False)`, never through a document save.
- Frappe fills a single's defaults only while none of its values is stored. The hourly job stores `last_subscription_phase` on every site, so the three event switches are stored as on at install (`setup.bootstrap`) and by the migration patch (`store_default_events`).
- New user facing strings are `_()` with `{0}` placeholders, rendered per recipient with `lang=`; their English text is the translation key.

## Gotchas

- Push is off unless all three `books_fcm_*` keys are set (`fcm.is_configured`); without them nothing is queued, sent, or shown in the boot. Tests that need it off clear the keys themselves (`push_off()` in the tests), since a bench may hold real keys.
- Firebase delivers a data only message; the service worker reads `payload.data` (or the keys at the top level) and shows it. The page registers no Firebase `onMessage`, so a push never shows twice.
- The app usually sits at `/books`, outside the worker's `/books/` scope, so the worker does not control it: `client.navigate()` throws and `navigator.serviceWorker.ready` never resolves there. The worker posts the link to the tab instead (`books-push-open`), and the page routes itself.

## Agent skills

- No Agent Skill covers FCM yet (searched 2026-11-28; `firebase/agent-skills` has none for messaging).
- MCP servers: Firebase MCP `npx -y firebase-tools@latest mcp` (recommended; `messaging_send_message` sends a test push to a device token, `firebase_get_sdk_config` returns the web config)

_Drafted by /sync from the introducing change, worth a quick human pass._
