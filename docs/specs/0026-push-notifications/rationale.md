# 0026. Push notifications: decision record

The build spec is [index.md](index.md). This file holds the context, the options weighed, the reasoning and the references.

## Context

/books tells nobody anything unless they have it open. An owner who is out of the shop learns about a customer's payment, an item running out, or the trial about to end only by logging in and looking. The installed phone app (the PWA served from `frappe_books/pwa/`) only caches files; its service worker has no push handling, and the frontend never asks for notification permission. The server sends no email, realtime or push messages for these events.

Frappe 16 ships the server half of a push system (`frappe/push_notification.py` and Push Notification Settings), but it talks only to a relay server, and that relay (`push-notification-relay.frappe.cloud`) registers Frappe's own apps, such as Raven and Frappe HR, each with Frappe's Firebase project. Its code is not public. A custom app like RareBooks cannot register a project there, so the built in feature is unusable without running a relay of our own. Frappe also ships nothing for the browser side.

RareBooks is multi tenant at the site level: every customer is its own Frappe site with its own address (a subdomain, or a custom domain under spec 0012), hosted on Frappe Cloud (spec 0010) and driven by the control site. Any push setup must work for many sites without per site manual work, keep secrets out of the repo and the database (root `AGENTS.md` rules; spec 0009 set the pattern of keys in the bench config), and must not break the read only lock of spec 0005, where requests and most jobs run in a read only transaction but scheduled jobs still write.

The engineer wants v1 to cover three events (payment received, low stock, subscription ending), sent by role to Books Managers, switched on per device from the app menu, with a per shop switch per event, in each recipient's language, at no cost up to at least 10,000 subscribers. Two events the engineer also wanted, invoice overdue and the POS shift close summary, were dropped from v1: the first needs a due date Sales Invoice does not have, the second needs a summary screen of its own.

## Options considered

### Option 1: FCM HTTP v1 called directly, one shared Firebase project

`frappe_books` signs a Google access token from a service account key kept in the site config, and posts each message to FCM's HTTP v1 API from a background job. The browser gets an FCM token with the Firebase JS SDK, using /books' existing service worker, which handles `push` and `notificationclick` itself. One Firebase project serves every hosted site.

**Pros**:
- Free at any volume; Google lists Cloud Messaging as no cost (basis: Firebase pricing page).
- No relay or extra server to run; the only moving parts are Google and the app we already deploy.
- One project and one key set for every site, so a new site needs nothing (basis: spec 0010 and spec 0014, sites are created by automation).
- Follows the project's existing pattern for an outside service: one module owns the calls, keys in the bench config, tests patch the module (basis: root `AGENTS.md` and spec 0009).

**Cons**:
- We write and own the token signing, sending, dead token cleanup and service worker handlers ourselves.
- A new dependency on Google and a new frontend package (`firebase`).
- A leaked service account key lets anyone push to every RareBooks device until it is revoked.

### Option 2: Frappe's PushNotification API through a self hosted relay

Install a community relay app (for example `frappe_pwa_push` or `frappe_notifier`) on a server we run, probably the control site's bench, point every site at it with `push_relay_server_url`, and use Frappe's `PushNotification` class to send.

**Pros**:
- Reuses Frappe's own server API and settings doctype; less sending code in `frappe_books`.
- The Firebase key lives on the relay only, not on every site.

**Cons**:
- A relay server to run, monitor and keep up: if it is down, every site's pushes stop.
- Community relay apps with unknown maintenance and Frappe version support.
- Frappe still ships no browser side, so the frontend and service worker work is the same as Option 1.
- Every site name and device token passes through one more system.

### Option 3: OneSignal

Use OneSignal's Web SDK and REST API instead of Firebase.

**Pros**:
- The easiest browser setup: a ready made permission prompt and a dashboard to send test messages.
- Delivery and subscriber stats out of the box.

**Cons**:
- OneSignal ties a web push app to one website address, so every customer site needs its own OneSignal app, created and tracked by the control site.
- The free plan caps each send at 10,000 web push recipients and, since late 2026, mobile push at 1,000 monthly active users; paid web push is about $0.004 per subscriber a month (basis: OneSignal's pricing blog posts and third party summaries; the live pricing page could not be loaded).
- A second worker script must share /books' service worker.

### Option 4: Standard Web Push with our own VAPID keys, no provider

The server encrypts and sends Web Push messages itself to each browser's push service (Google, Mozilla, Apple), using a Python Web Push library and VAPID keys.

**Pros**:
- No Firebase or OneSignal account; the open standard every browser implements.
- No vendor SDK in the frontend.

**Cons**:
- A new Python dependency for message encryption, and per browser quirks (Apple's push service especially) that FCM already absorbs.
- No path to native Android or iOS apps later, which FCM gives for free.

## Rationale

The force that decides this is RareBooks' shape: many small sites, each with its own address, created by automation, with secrets kept in the bench config and no appetite for another server to operate. Option 1 is the only one where a new site gets push with zero setup and nothing new has to stay up. Option 2 keeps Frappe's API but adds exactly the server we want to avoid, and its browser work is no smaller. Option 3's one app per website rule turns every site creation into a OneSignal API call and a stored key, and its free tier limits are the tightest. Option 4 is the most open but rebuilds what FCM already does, and it closes the door on native apps.

The engineer first picked Frappe's relay. That choice assumed the relay was usable by any Frappe app; it is not, since Frappe's relay serves only its own projects and its code is not public. Once that was clear the engineer chose Option 1. The engineer also chose to push on every sales payment, POS sales included, against the recommendation to leave POS out: a busy shop will get a push per till sale, which the per event switch (AC-8) is there to stop.

The smaller calls made while writing:
- **Firebase JS SDK in the page, our own handlers in the service worker** (runner up: Firebase's own `firebase-messaging-sw.js`). FCM tokens can only be minted by the Firebase SDK, but a second service worker cannot share /books' scope, so the page calls `getToken` with our registration and the worker reads the raw push itself. Messages are data only, so our worker decides how they show.
- **Sign the Google token with PyJWT** (runner up: the `google-auth` package). Frappe already depends on PyJWT and cryptography, so no new Python dependency; the token is cached in Redis for its lifetime.
- **Send in a background job after commit, never retried** (runner up: send inline, or retry on 5xx). A push must never slow or fail a submit, and a duplicate "payment received" is worse than a missing one.
- **Hourly subscription check, sending inside the scheduled job** (runner up: daily, queued). A daily run can push a day late, and on a locked site only scheduled jobs may write (`subscription/lock.py`), so the send cannot go through a queued job.
- **One push per POS sale, from the invoice** (runner up: one per payment row). A split tender would otherwise send two or three pushes for one sale.
- **Fire once with stored flags under a row lock** (runner up: Redis keys). Survives a cache flush and two concurrent transactions.
- **The first subscription run stores and does not push** (runner up: push on first run). Deploying the feature must not send every shop a message at once.
- **Delete devices unseen for 90 days** (runner up: keep forever). Every open /books refreshes `last_seen`, so 90 days means the device is gone.
- **Device label from the user agent, cut down on the client** (runner up: no label). Lets a future device list name devices without storing the full user agent.

### Amend: the `prompt` push date (2026-11-28)

`/check verify` sent the `prompt` push on a real site and it read "Subscribe by 26-11-2026" on 28-11-2026. The `prompt` phase runs from day 22 to day 25, so the trial end (day 21) is always in the past when the push goes out. What the owner must beat is the lock on day 26. The push now names `lock_starts_on` with the banner's framing ("before your books turn read only"), so the push and the banner point at the same day. The title changed too, since "Your trial ends soon" was already false. A PayPal subscription set to start after the trial hides the banner's prompt (spec 0008 AC-21); the push follows the same rule, so nobody who already subscribed is told to subscribe.

### Amend: the tap messages the page (2026-11-28)

On a real Android phone, tapping a push with /books already open left the tab where it was. The app and the installed app usually sit at `/books`, which is outside the service worker's `/books/` scope, so the worker does not control that tab, and `client.navigate()` throws ("This service worker is not the client's active service worker"). The worker now posts the link to the tab and focuses it, and the page routes itself. That works whether or not the worker controls the tab, and moves screens without reloading the app. The other route, widening the worker's scope to `/books` with a `Service-Worker-Allowed` header, was not taken: it would change what the worker controls for its offline cache as well, for a problem the message solves on its own. Confirmed on the phone after the fix.

### Amend: a daily summary while items stay low (2026-11-28)

The first push about an item fires once, when it drops, and nothing follows while it stays low, which is easy to miss. The engineer chose a daily reminder: one summary push a day rather than one per item (a shop with many low items would otherwise get a burst every morning), at 08:00 site time so it lands before the shop opens, with its own switch so a shop can keep the instant alert without the daily one. Decided here: the job is hourly and sends at the first run at or after 08:00, so a stopped worker still sends later that day; it checks every tracked item with a reorder level in one grouped stock total, not the AC-6 flag, which is not kept while push is off (a plain read is enough, since it writes no item flag and a slightly stale total only shifts a reminder); the most urgent items lead (lowest stock relative to the level); it skips a locked site, where no restock can be recorded; the day is recorded only after a successful send, like the subscription push, so a Google outage retries the next hour, and a device registered later in the day still gets that day's summary; a site that just got the feature starts the next morning, so the first run after a deploy doesn't send mid afternoon. Not chosen: a per shop time setting (more settings for little gain), and leaving out items that alerted the same morning (it would need a timestamp per item for a small saving).

## References

**Project sources** (verifiable, in this repo):
- Root `AGENTS.md`: roles, translation, secrets in config, Python and frontend conventions
- `frappe_books/AGENTS.md` and `frappe_books/subscription/AGENTS.md`: the lock, scheduled jobs past the lock, `current_clock()`, phases
- Spec 0005 (trial and read only lock), spec 0009 (support chat: keys in bench config, real email rule, sign out cleanup), spec 0010 (Frappe Cloud hosting), spec 0012 (custom domains)
- `frappe/push_notification.py` in the installed Frappe 16 (relay only client, no browser side)
- `frappe_books/pwa/service_worker.js` (no push handling today)

**Practices & standards**:
- Send side effects after commit; never let a third party call fail a user's write
- Idempotent alerts: fire on a state transition, stored durably, under a row lock
- Least privilege recipients: only roles that already read the data

**Links** (web verified only):
- Firebase pricing plans: https://firebase.google.com/pricing.md.txt
- Firebase Cloud Messaging product page: https://firebase.google.com/products/cloud-messaging/
- Firebase Cloud Messaging costs (firebase-talk): https://groups.google.com/g/firebase-talk/c/vtkImpBZbPg
- Understanding OneSignal's Pricing: https://onesignal.com/blog/understanding-onesignals-pricing/
- OneSignal caps free mobile push at 1,000 MAU: https://pasqualepillitteri.it/en/news/20636/onesignal-mobile-push-free-plan-limit
- Frappe Push Notification Client Reference: https://github.com/frappe/frappe/wiki/Frappe-Push-Notification-Client-Reference
- Push Notifications, Frappe HR (Frappe Forum): https://discuss.frappe.io/t/push-notifications/131991
- frappe_pwa_push (self hosted relay): https://github.com/green-circle/frappe_pwa_push
- Firebase MCP server: https://firebase.google.com/docs/cli/mcp-server
- Firebase agent skills: https://github.com/firebase/agent-skills
