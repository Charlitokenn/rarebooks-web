# 0026. Push notifications through Firebase Cloud Messaging

**Date**: 2026-11-28
**Status**: In Progress

Decision history (context, options and reasoning) lives in [rationale.md](rationale.md).

## Summary

/books can send push notifications (short alerts that pop up on a phone or computer even when the app is closed) for three events: a payment received, an item running low on stock, and the subscription nearing or reaching its end. Each user turns them on per device from the app menu, and Books Managers get them. The server sends them straight to Firebase Cloud Messaging (Google's free push service, FCM for short) with one Firebase project shared by every hosted site, so there is no relay server to run. The feature stays off on any site whose config has no Firebase keys.

## Requirements

**User stories**:
- As a shop owner (Books Manager) away from the shop, I want a push when a customer pays, so I know money came in without opening /books.
- As a Books Manager, I want a push when a tracked item drops to its reorder level, so I can restock before it runs out.
- As a Books Manager, I want a push before and when the subscription ends, so the site never turns read only by surprise.
- As any /books user, I want to turn notifications on or off for the device I am on, so I only get them where I want them.
- As a Books Manager, I want to switch a whole event off for the shop, so a busy till does not flood everyone's phone.

**Acceptance criteria**:
- **AC-1**: Push is on only when `books_fcm_service_account`, `books_fcm_web_config` and `books_fcm_vapid_key` are all set in the site's config. Otherwise the boot carries `books.push: null`, no menu entry shows, no event sends anything, and no request goes to Google.
- **AC-2**: A signed in user with a real email (not Administrator or Guest, and not an email ending in `@example.com`, the same rule as spec 0009 AC-2) on a browser that supports push sees "Turn on notifications" in the app menu's Help group, on desktop and phone. Picking it asks the browser for permission (the browser's own prompt, shown only after this click), registers the device, and shows the toast "Notifications are on for this device." The entry then reads "Turn off notifications". If the user blocks the prompt, an orange toast that stays until closed says "Notifications are blocked. Allow them for this site in your browser settings." On an iPhone or iPad where /books is not opened from the Home Screen, the entry shows and picking it gives the toast "Add RareBooks to your Home Screen first, then turn on notifications from there." On a browser with no push support at all, no entry shows.
- **AC-3**: Each registered device is one Books Push Device row holding the user, the FCM token, a device label (for example "Chrome on Android") and when it was last seen. A token belongs to one user only: registering a token another user holds moves the row to the current user. Every /books start on a device whose permission is granted and that was turned on registers again, sending the token it stored last time; when FCM has rotated the token, the old token's row is deleted and the new one stored. That start up register is skipped on a locked site, and it writes nothing when the row's `last_seen` is under an hour old. A user holds at most 10 devices: registering an eleventh deletes the one with the oldest `last_seen`. A user reads and deletes only rows whose `user` is them.
- **AC-4**: "Turn off notifications" removes the browser's push subscription on this device and deletes this device's row, then shows the toast "Notifications are off for this device." Signing out from the app menu does the same before the Frappe logout runs, so the next person on that browser never gets the previous user's notifications.
- **AC-5**: When Books Notification Settings `payment_received` is on, every device of every enabled user with the Books Manager or System Manager role, except the user who submitted, gets a push titled "Payment received" with the body "{party} paid {amount}", in the company currency:
  - A Books Payment with `payment_type` Receive submitted outside a POS sale pushes once, with its `amount`, and tapping opens that payment.
  - A POS sale (`is_pos` Sales Invoice whose counter payments `make_counter_payment` submits) pushes once per sale, not once per tendered row, with the sum of those payments' `amount`, and tapping opens the invoice.
  A cancel, an amend, or a Pay payment sends nothing.
- **AC-6**: Books Item has a "Reorder level" field (0 means no alert), shown only when `track_item` is on. After a stock transaction is submitted or cancelled, each tracked item in it with a reorder level above 0 is checked against its total stock across all locations. When the total is at or below the level and `low_stock_notified` is off, it is set on and, if `low_stock` is on in Books Notification Settings, the same recipients as AC-5 get "Low stock: {item}" with the body "{quantity} {unit} left (reorder level {level})". Tapping it opens the item. While the flag is on no further push is sent; when the total rises above the level the flag is cleared, so the next drop alerts again. Two transactions at once send one push, not two. Saving an item whose `reorder_level` or `track_item` changed clears the flag and checks the item again at once (so a level set above current stock alerts on that save); a level of 0 or tracking turned off leaves the flag clear and sends nothing.
- **AC-7**: An hourly scheduled job compares the site's subscription phase (spec 0005 `current_clock().phase`) with the last phase it saw. On a change into one of these phases it pushes once to the same recipients, when `subscription` is on in Books Notification Settings, and tapping opens /books/subscription:
  - `prompt`: "Your books turn read only soon", body "Subscribe before {lock date} to keep making changes." The lock date is the first read only day (`lock_starts_on`, day 26), the same moment the `prompt` banner counts down to (spec 0005 AC-4). The trial itself already ended the day before `prompt` starts, so its end date is never named. `lock_starts_on` is never empty in `prompt` (it is empty only without a trial start, and such a site is `locked`), so it is always a future date and needs no fallback. A site whose PayPal subscription is already set to start after the trial (`subscription_starts_on` set, which the clock does only on day 22, the charge day; spec 0008 AC-21) gets no `prompt` push, the same as the banner's day 22 rule. That skip is final: the phase is stored as `prompt` exactly as when the Subscription switch is off (never the retry path), so no `prompt` push follows on day 23 when the first charge turns overdue either; Subscribe is hidden then anyway while PayPal retries.
  - `renew_soon`: "Renewal due", body "Your subscription ends on {paid until date}. Renew to keep making changes."
  - `grace`: "Payment overdue", body "Your subscription ended. Pay by {grace end date} to keep making changes."
  - `locked` or `lapsed`: "RareBooks is now read only", body "Subscribe to make changes again."
  Any other change is stored without a push; `locked` after `lapsed` or the reverse pushes nothing new (one tag, `subscription:read-only`, for both). The first run on a site (no last phase stored) stores the phase and sends nothing. An unmanaged or exempt site never gets a subscription push, and leaving `unmanaged` or `exempt` counts as a first run. A job that skipped days pushes only the phase it finds. The push is sent before the new phase is stored, in the same run, so a failed run tries again the next hour. Dates come from `current_clock().status()` (`lock_starts_on`, `paid_until`, `grace_ends_on`), are in the site's time zone, and are written with `formatdate` in the Books date format.
- **AC-8**: Books Notification Settings has three checkboxes, "Payment received", "Low stock" and "Subscription", all on for a new or migrated site (an unset value counts as on). It is a "Notifications" tab of the /books Settings dialog, shown only when push is on (AC-1). Only Books Manager and System Manager can read or change it. A checkbox that is off stops that event for the whole shop; turning it back on does not resend anything missed.
- **AC-9**: Each push is written in its recipient's language (the user's Frappe language, else the site language). Every new user facing string is translated at runtime (`t` tags in TS and Vue, `_()` with `{0}` placeholders in Python).
- **AC-10**: Sending never blocks or fails the user's action. Pushes are sent by a background job that runs only after the submit commits. Payment and low stock pushes go through a background job queued after the commit (job timeout 120 seconds); subscription pushes are sent inside the scheduled job itself, since on a locked site only scheduled jobs may write. An FCM error, a timeout (10 seconds per request) or missing permission is written to the Error Log once per job with only the HTTP status and FCM's error code (never the token, the request or any key), and the payment or stock transaction stays submitted. A token FCM answers 404 `UNREGISTERED` for, or 400 with an error naming the token, deletes its Books Push Device row; a 403 `SENDER_ID_MISMATCH` is logged and the rows are kept. Nothing is retried.
- **AC-11**: Tapping a notification focuses an open /books tab and moves it to the push's link, or opens a new /books window at that link when none is open. While /books is open and visible on that device, the push still shows as a system notification (the same text, no in app duplicate; the page registers no Firebase `onMessage` handler). The worker opens only a same origin path under `/books/`, and a push with no title or a bad link shows nothing.
- **AC-12**: `books_fcm_service_account` (it holds a private key) never appears in any response, boot, log or Error Log. Only `books_fcm_web_config` and `books_fcm_vapid_key`, which Firebase treats as public, reach the browser.
- **AC-13**: On a locked site (spec 0005) the `locked` or `lapsed` push of AC-7 is still sent. "Turn on notifications" shows the usual lock notice and registers nothing. "Turn off notifications" and signing out still stop pushes on that device (the browser subscription is removed even though the row cannot be deleted); the leftover row is deleted when FCM later reports its token unregistered. A browser whose session expired without a sign out keeps getting the previous user's pushes until another user registers there or the row ages out; this is an accepted risk.
- **AC-14**: A Books Push Device row not seen for 90 days is deleted by the daily job.

## Decision

**Chosen option**: Option 1: FCM HTTP v1 called directly from `frappe_books`, with one shared Firebase project.

The server signs its own Google access token from a service account in the site config and sends each push to FCM's HTTP v1 API from a background job; the browser gets an FCM token with the Firebase JS SDK through /books' own service worker, which shows the notification itself.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:

| Entity | Field | Type | Required | Notes |
|---|---|---|---|---|
| **Books Push Device** (new, not submittable, `autoname: hash`) | `user` | Link User | yes | indexed; the user the device belongs to (permissions follow this field, not `owner`) |
| | `token` | Small Text | yes | the FCM registration token (often over 150 characters) |
| | `token_hash` | Data | yes | lowercase hex SHA256 of `token`; `unique: 1` (MariaDB cannot put a unique index on long text) |
| | `device_label` | Data | no | from the browser, for example "Chrome on Android"; shown only in the row |
| | `last_seen` | Datetime | yes | set on every register |
| **Books Item** (2 new fields) | `reorder_level` | Float | no | default 0; `depends_on: track_item`; must be 0 or more |
| | `low_stock_notified` | Check | no | hidden, read only, default 0, `no_copy: 1` |
| **Books Notification Settings** (new single) | `payment_received` | Check | no | default 1 |
| | `low_stock` | Check | no | default 1 |
| | `subscription` | Check | no | default 1 |
| | `last_subscription_phase` | Data | no | hidden, read only; written only by the daily job |

Relationships: User 1:N Books Push Device. No other links. Rows are deleted outright (no soft delete).

**State transitions**:
- Device on a browser: not supported → (no entry) · off → on (permission granted, row registered) · on → off (turn off or sign out) · on → blocked (permission revoked in the browser; the next register fails silently and the entry reads "Turn on notifications").
- Item low stock flag: clear → set (total at or below level; the push is sent at this transition only) → clear (total above level).
- Last subscription phase: any → any; a push only on entry into `prompt`, `renew_soon`, `grace`, or the read only pair `locked`/`lapsed` (moving between the two is silent), and never from an empty value, `unmanaged` or `exempt`.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `frappe_books.notifications.register_device` | POST | `token`: str (req), `previous_token`: str (opt), `device_label`: str (opt) | `{ "name": str }` | signed in, any Books role or System Manager; checks AC-2's real email rule | 403 when push is off (AC-1) or the user may not; `SiteLockedError` / `InReadOnlyMode` on a locked site (shown by `src/web/api.ts`) |
| `frappe_books.notifications.unregister_device` | POST | `token`: str (req) | `{ "deleted": bool }` | signed in; deletes only a row whose `user` is the caller | 403 when push is off |
| Boot `books.push` block (`extend_bootinfo` in `boot.py`) | n/a | session user | `{ "web_config": dict, "vapid_key": str }` or `null` | per AC-1 and AC-2 | never raises; any config problem gives `null` |
| `frappe_books.notifications.notify_subscription_phase` | scheduler `hourly` | none | none | scheduled job | errors go to the Error Log |
| `frappe_books.notifications.delete_stale_devices` | scheduler `daily` | none | none | scheduled job | none |
| `frappe_books.notifications.fcm.send` (internal, not whitelisted) | n/a | `token`, `title`, `body`, `link`, `tag` | `"sent"`, `"dead"` or `"failed"` | server only | n/a |
| `frappe_books.notifications.send_job` (internal, queued `short`, timeout 120 s) | n/a | `messages`: list of {`device`, `title`, `body`, `link`, `tag`} | none | background job | deletes dead rows; logs failures once |
| FCM HTTP v1 (outgoing) | POST `https://fcm.googleapis.com/v1/projects/{project_id}/messages:send` | `message.token`, `message.data` {`title`, `body`, `link`, `tag`}, `message.webpush.headers` {`Urgency: high`, `TTL: 86400`} | message name | `Authorization: Bearer <access token>` | 404 `UNREGISTERED`, or 400 `INVALID_ARGUMENT` whose details name `message.token` → dead; any other 400, 401, 403 (`SENDER_ID_MISMATCH` included), 429, 5xx, timeout → failed |
| Google OAuth token (outgoing) | POST `https://oauth2.googleapis.com/token` | `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, `assertion` = RS256 JWT signed with the service account's `private_key` (scope `https://www.googleapis.com/auth/firebase.messaging`) | `access_token`, `expires_in` | the service account | any error → the job logs once and sends nothing |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Boot | `web_config`, `vapid_key` | site config `books_fcm_web_config` (JSON object) and `books_fcm_vapid_key` |
| Boot | whether the entry shows | AC-2 email rule on `frappe.session.user` plus all three config keys present |
| Menu entry | "on" or "off" for this device | `Notification.permission === 'granted'` and the local key `books_push_token:<user>` (localStorage, read in try/catch) holding the token this device registered |
| Menu entry | iPhone not installed | the browser lacks `PushManager` while `navigator.standalone` is false on an iOS user agent |
| `register_device` | `token` | `getToken(messaging, { vapidKey, serviceWorkerRegistration })` from `firebase/messaging`, with the existing `/books/sw.js` registration |
| `register_device` | `device_label` | the browser's user agent, reduced on the client to "{browser} on {OS}" (for example "Safari on iOS"), cut to 140 characters |
| `register_device` | `token_hash`, `last_seen`, `user` | SHA256 of `token`; `frappe.utils.now_datetime()`; `frappe.session.user` |
| Payment push | `party`, `amount`, link | the submitted Books Payment `party` and `amount`; link `/books/edit/Payment/{name}` |
| POS sale push | `party`, `amount`, link | the Sales Invoice `party`; sum of `amount` of the payments `make_counter_payment` returned; link `/books/edit/SalesInvoice/{name}`; sent from the invoice after `pay_at_counter`, and the counter payments themselves push nothing (flag `books_counter_payment` set on them) |
| Payment and POS push | currency and format | Books Payment has no currency field, so amounts are company currency: `frappe_books.accounting.money.company_currency()`, formatted with `frappe.utils.fmt_money(amount, currency=...)` |
| Payment and POS push | the submitter to skip | `frappe.session.user` at submit, passed to the job |
| Low stock push | total stock | `SUM(quantity)` of Books Stock Ledger Entry for the item, every location and date, read with `frappe.get_all` inside the job's server code |
| Low stock push | `{unit}`, `{level}`, `{item}`, link | Books Item `unit`, `reorder_level`, `name` (the item name); quantity formatted with `frappe_books.inventory.stock.format_quantity`; link `/books/edit/Item/{name}` |
| Subscription push | phase and dates | `frappe_books.subscription.clock.current_clock()` status: `phase`, `lock_starts_on` (the `prompt` push), `paid_until`, `grace_ends_on`, formatted with `frappe.utils.formatdate` (site date format, site time zone) |
| Subscription push | whether `prompt` pushes at all | `current_clock().subscription_starts_on`, read on the run that enters `prompt`: set (day 22 only) means a PayPal subscription already starts after the trial, so no push and the phase is stored; a later overdue charge (`first_payment_overdue`) sends nothing either, since the phase is already stored |
| Every push | recipients | enabled users (`User.enabled = 1`) having the role Books Manager or System Manager (`Has Role`), then their Books Push Device rows |
| Every push | language | `User.language`, else System Settings `language`; passed as `_(text, lang=...)` |
| Every push | `tag` | `payment:{name}` (the payment or POS invoice), `low-stock:{item}`, `subscription:{phase}` with `subscription:read-only` for both `locked` and `lapsed` (a repeat with the same tag replaces the shown notification, silently) |
| Worker | `icon` | the PWA icon the worker already inlines (`__ICON__` in `pwa/service_worker.js`) |
| Every push | text keys | the English strings in AC-2, AC-4, AC-5, AC-6 and AC-7 with `{0}` style placeholders are the translation keys; changing their wording drops existing translations |
| FCM call | `project_id`, client email, private key | fields of the `books_fcm_service_account` JSON |
| FCM call | access token | the OAuth exchange above (JWT `iat` now, `exp` now plus 3600), cached with `frappe.cache.set_value("books_fcm_access_token", ..., expires_in_sec=expires_in - 300)`; the cache is per site, so each site mints its own token, and two jobs that miss at once both exchange, which is harmless |
| `register_device` | old row to delete | `previous_token`, the token the browser stored under `books_push_token:<user>` |

**Key invariants**:
- No event sends anything unless AC-1's three keys are set; a site without them behaves exactly as today.
- Payment and low stock pushes are enqueued with `frappe.enqueue("frappe_books.notifications.send_job", queue="short", timeout=120, enqueue_after_commit=True, ...)`, so a submit that rolls back sends nothing and a send never runs inside the user's request. Subscription pushes call `fcm.send` directly inside the scheduled job, because `lock_job` (`subscription/lock.py:66`) leaves only scheduled jobs writable on a locked site.
- Deleting a dead row tolerates `InReadOnlyMode` (it is skipped, the next send retries the delete).
- `token_hash` is unique: one row per token across all users.
- The low stock check runs in this order, inside the submitting transaction: lock the item row (`frappe.db.get_value("Books Item", item, ["low_stock_notified", "reorder_level", "track_item"], for_update=True)`), then sum its stock, compare, set or clear the flag, and queue the push only when the flag went from clear to set. Concurrent transactions therefore cannot both see it clear. Only the transaction's own items are checked; a repost changes values, not quantities, and needs no check.
- Stock ledger `quantity` is signed (out is negative), so the sum is the stock on hand; it can be negative, which counts as at or below any level.
- `last_subscription_phase` and `low_stock_notified` are written with `frappe.db.set_single_value` / `frappe.db.set_value(..., update_modified=False)`, never through a document save, so no controller, timestamp or lock guard runs.
- The service account JSON is read in `notifications/fcm.py` only and never logged, returned or put in the boot.
- Only `notifications/fcm.py` talks to Google; tests patch `fcm.send` and `fcm.access_token`.

**Security model**:
- Recipients are fixed by role: Books Manager and System Manager, who already read payments, items and the subscription. A Books User or Cashier may register a device (for later events) but receives none of these three events.
- Books Push Device permissions: Books User, Books Manager, Books Cashier and System Manager have read and delete in the doctype, narrowed to rows whose `user` is the session user by a `permission_query_conditions` and `has_permission` hook in `hooks.py` (not `if_owner`, since a reassigned row keeps its old `owner`); nobody creates or writes through the generic API. `register_device` and `unregister_device` write with `ignore_permissions=True` after their own checks, so a user can only ever touch rows for their own session. A System Manager sees only their own rows too.
- Books Notification Settings: read and write for Books Manager and System Manager only.
- The push body carries a party name and an amount. It shows on a lock screen, which is the point; this is business data, not regulated data (no compliance scope). A Manager who does not want that switches the event off (AC-8).
- No new guest endpoint. `register_device` is bounded by the 10 device cap and the one hour `last_seen` skip, so no extra rate limit is needed.

**Configuration required**:
- `books_fcm_service_account`: the Firebase service account key JSON (one line), with permission to send FCM messages. Secret; set it only where the tawk.to keys of spec 0009 are set, never in the repo or the database.
- `books_fcm_web_config`: the Firebase web app config JSON (`apiKey`, `projectId`, `messagingSenderId`, `appId`). Public.
- `books_fcm_vapid_key`: the Web Push certificate public key from the Firebase console (Cloud Messaging settings). Public.
- Prerequisite before coding: create one Firebase project for RareBooks, add a web app to it, generate the Web Push key pair, and create the service account key. A local test site uses a separate test project.

**Critical test scenarios**:
- Happy path: with keys set and FCM patched, submitting a Receive payment enqueues one job after commit that sends "Payment received" with the party and formatted amount to each Manager device and none to a Cashier device, verifies **AC-5**, **AC-10**.
- Failure case: two stock transactions that both take an item from 12 to below its level of 10 send exactly one low stock push; restocking to 15 and selling to 8 sends a second, verifies **AC-6**.
- Failure case: FCM answers 404 `UNREGISTERED` for one token and times out for another; the payment stays submitted, the dead row is deleted, the other row stays, and one Error Log entry without any token or key is written, verifies **AC-10**, **AC-12**.
- Auth/permission: a Books User calling `unregister_device` with another user's token gets `{ "deleted": false }` and the row stays; a Books User cannot read Books Notification Settings (403), verifies **AC-3**, **AC-8**.
- Prompt date: a site entering `prompt` on day 22 gets "Your books turn read only soon" naming day 26 (`lock_starts_on`), never a past date; a first run that only sees `prompt` on day 25 still names day 26, verifies **AC-7**.
- PayPal set to start: day 22 with `subscription_starts_on` set sends nothing and stores `prompt`; the day 23 run (`first_payment_overdue`) sends nothing either, verifies **AC-7**.
- Locked site: the hourly job on a site that just became `locked` sends "RareBooks is now read only" once, and a second run the same day sends nothing, verifies **AC-7**, **AC-13**.
- Failure case: a POS sale paid by cash and card sends one push with the total, and a Manager who submits a Receive payment gets no push for it while another Manager does, verifies **AC-5**.
- Browser: Playwright with notification permission granted and `firebase/messaging` stubbed shows "Turn on notifications", registers, flips the label, and sign out calls `unregister_device` before `logout`, verifies **AC-2**, **AC-4**.

## Build plan

Ordered as tracer bullets (the project's build approach): the first slice carries one real push from a submitted payment to a phone through every layer; later slices add an event each.

1. Slice 1, the thread. Add `notifications/fcm.py` (service account parsing, signed JWT with PyJWT, token exchange and Redis cache, `send` with the 10 second timeout and the sent/dead/failed result) with unit tests that patch `requests`, satisfies **AC-10**, **AC-12**
2. Add the Books Push Device doctype with its `user` based permission hooks, `register_device` (previous token, one hour skip, 10 device cap) and `unregister_device`, and the `books.push` boot block in `boot.py` with the AC-1 and AC-2 rules; Python tests for ownership, reassignment, rotation, the cap and the off state, satisfies **AC-1**, **AC-3**, **AC-12**
3. Add the Books Notification Settings single with its three checkboxes defaulting on (code reads an unset value as on), its permissions, a patch `patches/add_notification_settings.py` in `patches.txt` that sets them on for existing sites, and the "Notifications" tab in `frontend/src/pages/Settings/useSettings.ts`, satisfies **AC-8**
4. Add `notifications/__init__.py` with `notify(event, build_message, exclude_user)`: picks enabled Manager and System Manager users with devices, renders each message once per user in their language, and queues `send_job` after commit; `send_job` sends per device, deletes dead rows (tolerating read only) and logs a sanitised failure once. Hook Books Payment `on_submit` for Receive payments not flagged as counter payments, and the Sales Invoice for POS sales after `pay_at_counter`; tests for recipients, the submitter skip, POS split tender, language, a locked site and the cancel/Pay cases, satisfies **AC-5**, **AC-9**, **AC-10**
5. Frontend: add `firebase` (modular `firebase/app` and `firebase/messaging` only, loaded with a dynamic `import()`), a `src/utils/pushNotifications.ts` module (support check; the iOS check, which also treats a Mac user agent with `navigator.maxTouchPoints > 1` as an iPad; permission; `getToken` with the `/books/sw.js` registration and no `onMessage`; register with the previous token; unregister; the local token key read in try/catch), the app menu entry beside "Chat with support", the start up re register (skipped when `books.subscription.locked`), and the unregister step in `logOut` before `endSupportChat`, wrapped in try/catch with a 2 second limit so sign out always goes on; node tests for the module, satisfies **AC-2**, **AC-3**, **AC-4**, **AC-9**, **AC-13**
6. Service worker: add plain `push` and `notificationclick` handlers to `frappe_books/pwa/service_worker.js` (no Firebase `importScripts`; `firebase-messaging-sw.js` is never requested). `push` reads the FCM data from the payload (confirm its exact shape against a real FCM web push during the build), skips a push with no title or a link that is not a same origin `/books/` path, and calls `showNotification(title, { body, tag, icon, data: { link } })` inside `event.waitUntil`. `notificationclick` closes the notification and, inside `event.waitUntil`, focuses a /books client from `clients.matchAll({ type: "window", includeUncontrolled: true })` and navigates it, else `clients.openWindow`. A Playwright test dispatches a push to the worker and clicks the notification, satisfies **AC-11**
7. Slice 2, low stock. Add `reorder_level` and `low_stock_notified` to Books Item, hook the check after `stock_posting.post` and `stock_posting.cancel` in `inventory/transaction.py` (which covers shipments, receipts, stock movements and invoice auto transfers) and in the Books Item controller when `reorder_level` or `track_item` changes, in the locked order of Key invariants; Python tests for crossing, clearing, cancel, a level change, level 0 and concurrency, satisfies **AC-6**
8. Slice 3, subscription. Add the hourly `notify_subscription_phase` job (sending directly, phase stored after the send) and its four messages, using `current_clock()`; tests for each phase, the first run, unmanaged and exempt sites, and a locked site, satisfies **AC-7**, **AC-13**
9. Add the daily `delete_stale_devices` job and its test, satisfies **AC-14**
10. Playwright: turn on, blocked permission toast, iPhone toast, turn off, sign out, the lock notice on a locked site, and no entry without keys, satisfies **AC-1**, **AC-2**, **AC-4**, **AC-13**
11. Amend from `/check verify` (2026-11-28): the `prompt` push names `lock_starts_on` with the new title and body, and is skipped when `subscription_starts_on` is set (read from the clock before any send; a no push run that stores the phase, never the retry path); replace the two old translation keys ("Your trial ends soon", "Subscribe by {0} to keep making changes.") with the two new ones; tests for day 22, day 25, and the PayPal day 22 then day 23 runs, satisfies **AC-7**

## Consequences

**Positive**:
- Owners hear about money in, low stock and the subscription without opening /books, which is what an owner away from the till needs most.
- No server to run: Google delivers, and the cost of sending is zero at any volume we expect.
- One Firebase project serves every hosted site, so onboarding a new site needs no push setup.
- The device registry and `notify()` make a fourth event (overdue invoices, the POS shift summary) a small change.

**Negative / tradeoffs**:
- A new outside dependency on Google: an FCM outage or a revoked service account silently stops pushes (logged, but nobody is paged).
- The `firebase` JS package adds weight; it must stay lazily imported so screens that never touch push do not load it.
- POS sales push once per sale (the engineer's choice to include them); a busy shop will want the "Payment received" switch off, and nothing smaller than on or off exists.
- The subscription check runs every hour on every site; it reads the clock and one single, which is cheap, but it is 24 runs a day instead of one.
- iPhones get pushes only when /books is installed on the Home Screen (iOS 16.4 or later), so some owners will see the "Add to Home Screen" toast instead.
- A browser left signed in when the session expires keeps its row until another user signs in there or FCM drops the token.
- Nothing is retried: a push lost to a Google error is gone, by design, since a late or duplicate "payment received" is worse than a missing one.

**Neutral**:
- Two new doctypes (one single), two Books Item fields, one patch, two daily jobs, one new frontend dependency.
- `frappe_books/AGENTS.md` gains a `notifications/` row and the rule that only `notifications/fcm.py` talks to Google (for `/sync`).

## Follow-up

- [ ] Connect Firebase's official MCP server for the build, to send test pushes and check the project: `claude mcp add firebase npx -- -y firebase-tools@latest mcp` (its exact FCM tools are unverified; read its docs first).
- [ ] No Agent Skill covers Firebase Cloud Messaging yet (searched 2026-11-28); check again before `/develop`.
- [ ] Decide where the three `books_fcm_*` keys are set on Frappe Cloud benches (the same place as the spec 0009 tawk.to keys) and write it in `frappe_books/AGENTS.md` Gotchas.
- [ ] Later specs: invoice overdue (needs a due date on Sales Invoice) and the POS shift close summary, both dropped from v1.
- [x] Enrolled as scope feature 27 (Slice 14).
