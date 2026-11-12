# 0005. Trial clock and read only lock

**Date**: 2026-11-12
**Status**: In Progress

Decision history: [rationale.md](rationale.md).

## Summary

Each hosted site gets a 30 day clock that starts when the site is created. Days 1 to 21 are a free trial. From day 22 a banner asks you to subscribe. From day 26, if no one has paid, the server opens every request in a read only database transaction (the database itself refuses any write), so you can still view, print and export but can't add or change anything. Payment happens on a central control site of yours (ClickPesa yearly for Tanzanian companies, PayPal monthly or yearly for everyone else), which then sends the customer site a signed message that lifts the lock at once. This spec builds the customer site side and pins down the contract with the control site. The control site itself gets its own spec.

## Requirements

**User stories**:
- As a site owner on a trial, I want to see how many days I have left and how to subscribe, so the lock never comes as a surprise.
- As a System Manager or Books Manager, I want to pay from inside /books with the payment method that fits my country, so I can keep working without contacting anyone.
- As any user of a locked site, I want to keep viewing, printing and exporting my records, so my data is never held hostage while the owner pays.
- As the operator, I want the lock enforced on the server for every write path and every role, so no API call, desk screen or Administrator login gets around it.
- As a paying customer, I want the lock to lift the moment my payment is confirmed, and a short grace period if a renewal fails, so I'm never locked for a hiccup.

**Acceptance criteria**:
- **AC-1**: A new site gets Books Subscription `trial_started_on` set to the install instant in UTC, from the `after_install` hook (`setup.bootstrap`), which runs when the site is created, not when the setup wizard completes. On an existing site, `bench migrate` runs a patch that sets `trial_started_on` to the moment the patch runs when it is empty (every site, managed or not; it only matters on managed ones). Day 1 is the date of that instant in the site's time zone (AC-18), and day N is day 1 plus N minus 1 days. Changing the time zone later moves the day boundaries with it.
- **AC-2**: A site whose `site_config.json` has no `books_control_url`, or whose Books Subscription has `exempt` checked, is never locked, shows no banner, and shows no Subscription item in the sidebar. Its Subscription page says the site is not on a hosted plan.
- **AC-3**: On days 1 to 21 with no payment, the site has full access and shows no banner. The Subscription page shows "Free trial", the days left in the trial, the date the trial ends (day 21) and the date read only starts (day 26).
- **AC-4**: On days 22 to 25 with no payment, every /books screen shows a banner: "{0} days left to subscribe before your books turn read only." where {0} is 26 minus the day number. System Managers and Books Managers see a Subscribe button that opens the Subscription page. Other users see "Ask your administrator to subscribe." The banner can be dismissed until the next site day: dismissing stores `localStorage` key `books_subscription_banner_dismissed` = the status dict's `today` (ISO date in the site's time zone), and the banner shows again once `today` differs. Locked and lapsed banners ignore the key.
- **AC-5**: From day 26 with no payment (and in the lapsed state of AC-14), the server refuses every web request that would write, on /books and /app alike, for every user including Administrator. A document insert, save, submit, cancel, update after submit, delete or rename is refused with `SiteLockedError` (HTTP 403) and the message "This site is read only. Subscribe to make changes again." Any other write (a whitelisted method, `db.set_value`, raw SQL) is refused by the read only transaction with `frappe.InReadOnlyMode`. In both cases nothing is written.
- **AC-6**: On a locked site every read keeps working: the dashboard, lists, forms, reports, the search palette, the print view, PDF download, the list Export wizard (CSV) and the report exports.
- **AC-7**: On a locked site these requests still run normally: login (including its two factor step, which goes through `login`), logout, `frappe.sessions.clear`, the email login link (`frappe.www.login.send_login_link`, `login_via_key`, `login_via_token`), social login callbacks (`frappe.integrations.oauth2_logins.*`), password reset (`reset_password` and `update_password`), the Books setup wizard's `complete_setup` (so a site that wasn't set up by day 26 can still finish setup and then pay), `get_subscription`, `start_checkout` and `receive_state`.
- **AC-8**: On a locked site the banner can't be dismissed. On the unpaid trial path it says "Your books are read only. Subscribe by {0} to keep your data." where {0} is the day 30 date. In the lapsed phase it says "Your books are read only. Renew to make changes again." Both show the Subscribe button to System Managers and Books Managers, and "Ask your administrator to subscribe." to everyone else. A refused save shows the same lock notice instead of a generic error. The client treats a response as the lock notice when its `exc_type` is `SiteLockedError` or `InReadOnlyMode`. On /app (desk) the site shows Frappe's own read only banner, and this feature adds nothing there.
- **AC-9**: On a locked site, scheduled jobs (those run through Frappe's `run_scheduled_job`) run normally. Every other background job runs in a read only transaction, so a job a user queued fails on its first write and nothing it would have written is stored.
- **AC-10**: On the Subscription page, a System Manager or Books Manager sees the plans the control site offers this site, with prices. A site whose company country is Tanzania is offered only ClickPesa Yearly, and every other site only PayPal Monthly and PayPal Yearly. Choosing a plan calls `start_checkout`, stores `checkout_started_on`, and sends the browser to the returned checkout URL. Any other user calling `start_checkout` gets `frappe.PermissionError` (403). It is refused with a `ValidationError` when the period isn't offered to this site, when the phase is `active` ("Your subscription is active. Change your plan from your PayPal account."), when the phase is `unmanaged` or `exempt`, or when the company has no country yet ("Finish setup first.").
- **AC-11**: `receive_state` applies a push only when its `X-Books-Signature` is a valid HMAC SHA256 of the raw body under this site's `books_control_secret`, its `site` is this site, and its `issued_at` (an ISO 8601 timestamp that must carry a time zone; a naive one is refused) is within 5 minutes of now. Otherwise it answers 401 and changes nothing. A valid push whose `issued_at` is not strictly newer than `last_synced_on` is ignored (200, `ignored`), so a replayed or late push can't undo a newer one. A signed push with a bad value (an unknown `provider` or `billing_period`, or a bad date) answers 400, is logged to the Error Log, and changes nothing. Unknown keys are ignored. The method is rate limited per IP.
- **AC-12**: Paying lifts the lock at once. After an accepted push with `paid_until` on or after today, the very next request is not locked. When the browser returns to `/books/subscription?checkout=returned`, the page pulls fresh state from the control site and writes it into the shared `subscriptionStatus` ref (`src/utils/refs.ts`), which the banner reads, so the banner clears without a page reload. An applied push or pull with a newer `paid_until` clears `checkout_started_on`.
- **AC-13**: While `paid_until` is today or later, the site has full access. With `auto_renews`, there's no banner, and the page shows "Renews on {0}". Without it (ClickPesa, or a cancelled PayPal subscription that is still paid), a renew banner shows once `paid_until` minus today is 14 days or fewer: "Your subscription ends on {0}. Renew to keep full access." The rule keys on `auto_renews`, not on the provider.
- **AC-14**: For 7 days after `paid_until` the site keeps full access and shows a banner: "Your subscription ended on {0}. Renew by {1} to keep full access." After those 7 days the site is locked exactly as in AC-5 (lapsed), with no removal date shown.
- **AC-15**: If the site is locked and `checkout_started_on` is within the last 24 hours, the lock notice adds "Payment pending. The lock lifts as soon as your payment is confirmed." The lock itself stays.
- **AC-16**: If the control site can't be reached (connection error, timeout of 10 seconds, or a bad response signature), the Subscription page shows "Couldn't reach billing. Try again." with a Retry button, and `start_checkout` fails with the same message. The lock rules keep following the stored Books Subscription values.
- **AC-17**: No site user, Administrator included, can change Books Subscription through the desk, `/api/v2`, `frappe.client` or `run_doc_method`. Every Books role can read it. Its only writers are `receive_state`, the pull inside `get_subscription`, the install and patch code that sets `trial_started_on`, and `apply_state` run from `bench execute`. Every change is kept as a Version (track changes).
- **AC-18**: Day boundaries follow the System Settings `time_zone`. A site set to Africa/Dar_es_Salaam locks at 00:00 local time on day 26, not at 00:00 UTC. While `time_zone` is empty (before the setup wizard), the site uses UTC, not Frappe's Asia/Kolkata fallback.
- **AC-19**: The banner, the lock notice and the Subscription page work at phone width, in the installed PWA too, with no sideways page scroll. The texts are the same on desktop and phone, translated at runtime (`t` in Vue, `_()` with `{0}` in Python), and dates show in the user's date format through the frontend's existing date formatter (`fyo.format` with fieldtype Date).

## Decision

**Chosen option**: Facts on a locked Books Subscription single, phase computed per request, lock enforced by a read only database transaction opened in `before_request` with a short allowlist, plus wildcard `doc_events` for a clear message. State changes arrive only as HMAC signed pushes from a central control site, which owns ClickPesa and PayPal.

The customer site never talks to a payment provider. It stores the facts it is told, works out its own phase from the clock, and lets the database refuse writes while locked.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`) · `paypal-best-practices` (`paypal/ai-toolkit`, `.agents/skills/paypal-best-practices/`, for the control site spec and the contract only; this site makes no PayPal call)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:

Books Subscription: a Single doctype in module Frappe Books, `track_changes: 1`. Every Books role (Books User, Books Manager, Books Cashier) and System Manager has read only. No role has write.

| Field | Type | Required | Notes |
|---|---|---|---|
| `trial_started_on` | Datetime | yes | Stored as a naive UTC value from `datetime.now(UTC)` (not `now_datetime()`, which uses the system time zone that may be unset at install), and always read back as UTC. Read only in the form, with the description "UTC". |
| `paid_until` | Date | no | The last day of paid access, in the site's time zone. Empty means never paid. |
| `provider` | Select: ClickPesa, PayPal | no | |
| `billing_period` | Select: Monthly, Yearly | no | ClickPesa is always Yearly. |
| `auto_renews` | Check | no | 1 while a PayPal subscription is active. |
| `provider_reference` | Data | no | The PayPal subscription id or the ClickPesa order reference. Shown for support. |
| `exempt` | Check | no | Never locked, no banner. |
| `checkout_started_on` | Datetime | no | Naive UTC. Drives the payment pending note (AC-15). Cleared when a push or pull brings a newer `paid_until`. |
| `last_synced_on` | Datetime | no | Naive UTC `issued_at` of the last applied push or pull. Used for replay protection. |

`site_config.json` (written by your provisioning script, never by the app): `books_control_url` and `books_control_secret`. There are no links to other doctypes. The site list lives on the control site.

**State transitions** (the phase is computed, never stored; `today` is the current date in the site's time zone, which is System Settings `time_zone` or UTC while that is empty; `day` = today minus day 1, plus 1):

| Phase | When | Locked | Banner |
|---|---|---|---|
| `unmanaged` | no `books_control_url` | no | none |
| `exempt` | `exempt` checked | no | none |
| `active` | `paid_until` ≥ today, and `auto_renews` or `paid_until` minus today > 14 days | no | none |
| `renew_soon` | `paid_until` ≥ today, not `auto_renews`, `paid_until` minus today ≤ 14 days | no | renew (AC-13) |
| `grace` | today is 1 to 7 days after `paid_until` | no | renew by (AC-14) |
| `lapsed` | today is more than 7 days after `paid_until` | yes | lock, renew text (AC-8) |
| `trial` | no `paid_until`, day 1 to 21 | no | none |
| `prompt` | no `paid_until`, day 22 to 25 | no | days left (AC-4) |
| `locked` | no `paid_until`, day 26 or later | yes | lock with the day 30 date (AC-8) |

The rows are checked top to bottom, and the first match wins. A payment during the trial gets a `paid_until` past the trial end (the control site starts the paid period when the trial ends), so it reads as `active`. Once a site has any `paid_until`, it never returns to the trial rows: a lapsed site stays `lapsed` until a newer `paid_until` arrives.

**API surface** (customer site, module `frappe_books/subscription.py`; every method is type annotated):

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `frappe_books.subscription.get_subscription` | GET | `refresh: bool = False` | the status dict (below); `plans` and `plans_error` when the caller can subscribe | logged in, read on Books Subscription | 403 without read |
| `frappe_books.subscription.start_checkout` | POST | `billing_period: Literal["Monthly", "Yearly"]` (req). The provider is not an input: the server sends `offered_provider` | `checkout_url` | System Manager or Books Manager (`frappe.only_for`) | 403 other roles; 417 plan not offered, phase `active`, unmanaged or exempt, no company country, control site unreachable |
| `frappe_books.subscription.receive_state` | POST | raw JSON body read with `frappe.request.get_data()` (the signature covers these exact bytes; never re-serialize `form_dict`): `site`, `issued_at`, `paid_until`, `provider`, `billing_period`, `auto_renews`, `provider_reference`, `exempt`; header `X-Books-Signature: sha256=<hex>` | `{"result": "applied"}` or `{"result": "ignored"}` | guest, HMAC signature, `@rate_limit(limit=60, seconds=60)` | 401 bad signature, wrong site or stale `issued_at`; 400 bad value after a valid signature |
| `frappe_books.subscription.apply_state` | `bench execute` only (not whitelisted) | `state: dict` (same fields as the push, no signature) | none | bench operator | ValidationError on a bad value |
| boot (`extend_bootinfo`) | n/a | none | `bootinfo.books.subscription` = the status dict, without plans | session | none |

Status dict: `phase`, `locked`, `today`, `day_number`, `trial_ends_on`, `lock_starts_on`, `removal_on` (unpaid trial path only), `paid_until`, `grace_ends_on`, `provider`, `billing_period`, `auto_renews`, `payment_pending`, `can_subscribe`, `offered_provider`, `offered_periods`. Dates are ISO dates in the site's time zone.

Control site contract (built in the control site spec; the customer site calls these):

| Call | Body (signed with `X-Books-Signature`) | Response (also signed) |
|---|---|---|
| `POST {books_control_url}/api/method/rarebooks_control.api.get_state` | `site`, `issued_at` | `state` (the push fields plus `issued_at`) and `plans`: list of `provider`, `billing_period`, `amount`, `currency`, `label` |
| `POST {books_control_url}/api/method/rarebooks_control.api.create_checkout` | `site`, `issued_at`, `provider`, `billing_period`, `return_url` | `checkout_url` |
| The control site calls `receive_state` on each change | as above | as above |

Signing: `sha256=` + hex HMAC SHA256 of the exact raw body bytes under `books_control_secret`, compared with `hmac.compare_digest`. Requests carry it in the `X-Books-Signature` header, and the control site's responses carry it in the same header over the raw response body. `issued_at` is an ISO 8601 timestamp with a time zone, parsed with `datetime.fromisoformat` and converted to UTC; a naive one is refused. Both servers must keep their clocks in sync (NTP), since the window is 5 minutes. One secret per site, so a leaked secret exposes one site only. `exempt` is trusted from the control site by design.

**Lock enforcement** (hooks in `hooks.py`):
- `before_request`: `frappe_books.subscription.lock_request`. If the phase is locked and the request is not on the allowlist, set `frappe.flags.read_only = True` and `frappe.flags.books_site_locked = True`, then `frappe.db.begin(read_only=True)`. That's the same pair Frappe's maintenance mode sets in `frappe.app.setup_read_only_mode`, so Frappe defers its own view and access logs to Redis. The allowlist matches `/api/method/<name>` and `/api/v2/method/<name>` for the methods in AC-7: `login`, `logout`, `frappe.sessions.clear`, `frappe.www.login.send_login_link`, `frappe.www.login.login_via_key`, `frappe.www.login.login_via_token`, every `frappe.integrations.oauth2_logins.*`, `frappe.core.doctype.user.user.reset_password`, `frappe.core.doctype.user.user.update_password`, `frappe_books.frappe_books.doctype.books_setup_wizard.books_setup_wizard.complete_setup` and the three `frappe_books.subscription` methods. The legacy `cmd=` route isn't matched, so it fails closed. The hook runs before Frappe's API key and OAuth auth (`validate_auth`), so it must not depend on the user. The phase check doesn't.
- `before_job`: `frappe_books.subscription.lock_job(method, kwargs=None, transaction_type=None, **_)`, the keywords Frappe passes. `method` is the job's dotted name string (Frappe passes `method_name`). If locked and `method` is not `frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job`, set `frappe.flags.read_only = True` and `frappe.flags.books_site_locked = True`, then `frappe.db.begin(read_only=True)`. The flag matters: `frappe.db.commit()` inside a job begins again read only only while `frappe.flags.read_only` is set. Frappe resets flags per job in `frappe.init`. Tests check that the next job in the same worker isn't locked.
- `doc_events` `"*"`: `before_insert`, `validate`, `before_submit`, `before_cancel`, `before_update_after_submit`, `on_trash` and `before_rename` call `refuse_when_locked(doc, method=None, *args, **kwargs)` (`before_rename` passes old, new and merge), which raises `SiteLockedError` when `frappe.flags.books_site_locked` is set. It skips the log and housekeeping doctypes (Error Log, Version, Comment, Activity Log, Access Log, View Log, Scheduled Job Log, Route History, Deleted Document) so error handling can't loop. Those writes still meet the read only transaction, or defer to Redis. This is the first `doc_events` entry in the app.
- `books_subscription_sync` is set only inside a `_syncing()` context manager in `subscription.py`, used by `receive_state`, the pull, `apply_state`, install and the patch, and never from request input. `bench migrate` doesn't save the single, so the guard never blocks a migration.
- `SiteLockedError(frappe.ValidationError)` with `http_status_code = 403`, in `frappe_books/subscription.py`. The client maps it and `InReadOnlyMode` to the lock notice.
- The phase check reads `frappe.get_cached_doc("Books Subscription")` and `frappe.conf`, so a request adds no query once the cache is warm. Saving the single clears the cache.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| install, patch | `trial_started_on` | `frappe.utils.now_datetime()` converted from the system time zone to UTC at that moment |
| phase, every request | today, day 1 | System Settings `time_zone` (read directly; UTC when empty, never `get_system_timezone()`'s Asia/Kolkata fallback) applied to the current UTC instant and to `trial_started_on` |
| banner dismissal | `today` | the status dict, so the browser uses the site's day, not its own |
| phase | managed or not | `frappe.conf.books_control_url` present |
| phase | paid, exempt, auto renew | Books Subscription `paid_until`, `exempt`, `auto_renews` |
| banner, page | `trial_ends_on`, `lock_starts_on`, `removal_on` | day 1 + 20, + 25 and + 29 days |
| banner (AC-4) | days left | 26 minus `day_number` |
| banner (AC-14) | `grace_ends_on` | `paid_until` + 7 days |
| lock notice (AC-15) | `payment_pending` | `checkout_started_on` within 24 hours of now |
| page, `start_checkout` | `can_subscribe` | the session user has System Manager or Books Manager |
| page, `start_checkout` | `offered_provider`, `offered_periods` | `frappe_books.settings.company_country()` is "Tanzania" → ClickPesa, Yearly; any other country → PayPal, Monthly and Yearly; no country yet → none offered ("Finish setup first.") |
| page, banner | the status after a refresh | `subscriptionStatus` ref in `src/utils/refs.ts`, seeded from boot |
| page | plan prices, currency, labels | the control site's `get_state` response `plans`, cached in `frappe.cache` for 1 hour, not stored |
| `start_checkout` | `site` sent to the control site | `frappe.local.site` |
| `start_checkout` | `return_url` | `frappe.utils.get_url("/books/subscription?checkout=returned")` |
| `start_checkout` | `checkout_url` | the control site's `create_checkout` response |
| `receive_state`, pull | `paid_until` and the paid period start (trial end when paid early) | computed by the control site from the provider's confirmation; the site stores it as given |
| `receive_state` | which site the push is for | body `site` must equal `frappe.local.site` |
| `receive_state` | replay order | body `issued_at` compared with `last_synced_on` |
| all signed calls | the secret, the control URL | `frappe.conf.books_control_secret`, `frappe.conf.books_control_url` |

**Key invariants**:
- A locked site commits no write made inside a web request outside the allowlist, or inside a non scheduled job. The database enforces this, not only the app code.
- Books Subscription changes only through a verified push, the signed pull, install and patch code, or `bench execute`. The controller `validate` refuses any save without `frappe.flags.books_subscription_sync` set.
- `last_synced_on` only moves forward.
- The phase is never stored. It is always derived from the facts, today and the time zone, so the lock starts at midnight with no job and no push.
- The site never holds a provider credential. ClickPesa and PayPal keys live only on the control site.
- A site without `books_control_url` behaves exactly as before this feature.

**Security model**:
- Read: every Books role and System Manager can read Books Subscription and call `get_subscription`. Only System Manager and Books Manager get `plans` and may call `start_checkout`, which the server checks with `frappe.only_for`.
- Write: no role. Administrator is refused by the controller guard (AC-17).
- `receive_state` is a guest endpoint. It is protected by the per site HMAC secret, the 5 minute `issued_at` window, the site name check, forward only `last_synced_on` and a rate limit. Every failure answers 401 with no detail.
- Outgoing calls go over HTTPS only. The site refuses a `books_control_url` that isn't `https://` unless `developer_mode` is on. Responses must carry a valid signature before the site applies them.
- Payment data: no card, wallet or phone number reaches the customer site. It is out of PCI scope. `provider_reference` is an opaque id.
- Audit: track changes on the single keeps a Version for every state change (who or which push, old and new values).

**Configuration required**:
- `books_control_url` (site_config): the control site's base URL. Its presence turns the feature on for the site.
- `books_control_secret` (site_config): a random secret of at least 32 bytes, unique per site, shared with the control site's record for this site.
- Provider credentials (ClickPesa client id, API key and checksum key; PayPal client id, secret, webhook id and plan ids) belong to the control site spec, not this one.
- Prerequisite: ClickPesa has no sandbox (every call is live, with a limit of TZS 100,000 before KYC), so the control site's ClickPesa testing needs a real account and small real payments.

**Critical test scenarios**:
- Happy path: site on day 26 is locked; a signed push with `paid_until` a year out arrives; the next save succeeds and the banner is gone. Verifies **AC-5**, **AC-11**, **AC-12**.
- Clock: with the clock frozen, day 21, 22, 25, 26 and 30 give `trial`, `prompt`, `prompt`, `locked`, `locked`. A site in Africa/Dar_es_Salaam at 23:30 UTC on day 25 is already on day 26. Verifies **AC-1**, **AC-3**, **AC-4**, **AC-18**.
- Bypass attempts on a locked site, each over real HTTP: `/api/v2/document` insert, a whitelisted Books method that calls `db.set_value` (for example `set_print_formats`), `frappe.client.set_value`, a submit, a delete and a rename, as Books Manager and as Administrator. Each is refused, and a database read afterwards shows nothing changed. Verifies **AC-5**.
- Reads on a locked site: list, form, report, PDF download, list CSV export and search all succeed. Verifies **AC-6**.
- Allowlist: login, logout, password reset and the Books setup wizard's `complete_setup` work on a locked site. Verifies **AC-7**.
- Jobs: a queued job that inserts, commits midway, then inserts again stores nothing; a scheduled job runs; the next unlocked job in the same worker writes normally. Verifies **AC-9**.
- Time zone: with `time_zone` empty, day boundaries are UTC. Verifies **AC-18**.
- Checkout refusals: phase `active`, and no company country, are each refused with their message. Verifies **AC-10**.
- Push security: a bad signature, the wrong site, `issued_at` 6 minutes old, and a replay of an older valid push each change nothing. Verifies **AC-11**.
- Permission: a Books User calling `start_checkout` gets 403. A Tanzania site asking for Monthly is refused. Verifies **AC-10**.
- Guard: Administrator saving Books Subscription through `/api/v2` is refused. Verifies **AC-17**.
- Lifecycle: `paid_until` = today is `active`, +1 day is `grace`, +8 days is `lapsed` and locked; a ClickPesa site 14 days out is `renew_soon`. Verifies **AC-13**, **AC-14**.
- Unmanaged: with no `books_control_url`, day 40 is not locked and shows no banner. Verifies **AC-2**.
- Control site down: a stub that times out gives the Retry state, and the lock is unchanged. Verifies **AC-16**.

## Build plan

Tracer Bullet: the first slice proves the read only lock end to end on a real request, before any payment wiring.

**Milestone 1: Server thread, the lock works**
1. Spike test first: in an `IntegrationTestCase` driving Frappe's WSGI app (as `frappe/tests/test_api.py` does), prove that `frappe.db.begin(read_only=True)` from a `before_request` hook refuses an insert and that Frappe's end of request commit doesn't error. If it fails, stop and return to `/architect`. Satisfies **AC-5**.
2. Books Subscription single (JSON, read only perms, track changes) and its controller guard (`books_subscription_sync` flag). Satisfies **AC-17**.
3. `frappe_books/subscription.py`: `get_phase()` and the status dict, with the time zone rules and the table above. Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-18**.
4. Set `trial_started_on` in `setup.bootstrap` and in a patch `patches/start_subscription_trial.py` (listed in `patches.txt`). Satisfies **AC-1**.
5. `lock_request` with the allowlist, `SiteLockedError`, wildcard `doc_events`, `lock_job`, and their hooks. Satisfies **AC-5**, **AC-7**, **AC-9**.
6. `apply_state` for `bench execute` (so the lock can be lifted before the control site exists). Satisfies **AC-12**, **AC-17**.
7. Python tests: clock and phase, the bypass list, reads and exports under lock, allowlist, jobs, guard, unmanaged. Satisfies **AC-1** to **AC-9**, **AC-17**, **AC-18**.

**Milestone 2: Thin UI end to end**
8. Status in `extend_bootinfo`; `get_subscription` (status only). Satisfies **AC-3**, **AC-4**.
9. Banner component in the app shell (desktop and phone), with the prompt and lock texts, dismissal for the day, and the Subscribe button only when `can_subscribe`. Satisfies **AC-4**, **AC-8**.
10. Map `SiteLockedError` and `InReadOnlyMode` in `src/web/api.ts` to the lock notice. Satisfies **AC-5**, **AC-8**.
11. `/subscription` route and page (read only view of the status), and a sidebar item for everyone on managed sites. Satisfies **AC-2**, **AC-3**.
12. Node tests for the banner texts per phase; one Playwright test: a locked site shows the banner and refuses a save. Satisfies **AC-4**, **AC-5**, **AC-8**.

**Milestone 3: The control site contract**
13. Signing helpers (sign, verify, `issued_at` window) and `receive_state` with the rate limit and replay rule. Satisfies **AC-11**.
14. Signed pull of `get_state` inside `get_subscription(refresh=True)`, applied through the same path, with plans cached. Satisfies **AC-10**, **AC-12**, **AC-16**.
15. `start_checkout` with the role check, provider and period rules, `checkout_started_on`, 10 second timeout. Satisfies **AC-10**, **AC-15**, **AC-16**.
16. Subscription page: plans with prices, Subscribe per plan, return refresh on `?checkout=returned`, payment pending note, Retry state. Satisfies **AC-10**, **AC-12**, **AC-15**, **AC-16**.
17. A control site stub for tests (signs responses with the test secret) and Python tests for push security, checkout and the down state. Satisfies **AC-10**, **AC-11**, **AC-16**.

**Milestone 4: Paid lifecycle**
18. `active`, `renew_soon`, `grace` and `lapsed` banners and page texts, and tests at each boundary. Satisfies **AC-13**, **AC-14**.

**Milestone 5: Phone and the full browser suite**
19. Phone layout of the banner, the lock notice and the page, plus the full Playwright suite on desktop and phone (trial, prompt, locked, paid, grace, lapsed, unmanaged). Satisfies **AC-19** and rechecks **AC-2** to **AC-16**.

## Consequences

**Positive**:
- The lock holds for every write path, including ones written later, because the database refuses the write, not a list of checks.
- The lock starts and ends on its own: no scheduler job flips it, and a missed push heals on the next pull.
- No provider secret or payment data lives on a customer site, and a leaked site secret affects one site only.
- Self hosted and dev sites are untouched.

**Negative / tradeoffs**:
- A locked request's first write fails mid request. Any whitelisted method that writes before it reads gives `InReadOnlyMode`, with Frappe's maintenance wording unless the client maps it (task 10).
- /app (desk) shows Frappe's own "read only mode" banner on a locked site, with maintenance wording that this feature doesn't control.
- A locked site's user can't do anything that writes as a side effect, such as saving list view settings, report column choices or a notification seen state. Those fail quietly or with the lock notice.
- The feature can't take a real payment until the control site spec is built. Until then `apply_state` from `bench execute` is the only way to lift a lock.
- The allowlist is a hand kept list. A new Frappe auth method (for example a new login flow in a v16 minor release) needs adding.
- Deferred inserts (access and view logs) sit in Redis until a scheduled flush, so a Redis restart can drop a few log rows from a locked site.
- Frappe doesn't extend sessions in read only mode, so on a locked site users are logged out at their session's original expiry and must log in again (login stays allowed).
- File uploads (`upload_file`) and attachments fail on a locked site by design.
- The push window needs both servers' clocks in sync (NTP). A site clock off by more than 5 minutes refuses every push until it's fixed, though the pull still heals it.

**Neutral**:
- `bench migrate`, `bench console`, backups and patches run outside a web request, so a locked site can still be upgraded and repaired.
- This adds the app's first `doc_events`, `before_request` and `before_job` hooks. `frappe_books/AGENTS.md` says there are no `doc_events`, so that line goes stale (for `/sync`).
- There's one new patch, one new single, and two new site_config keys that the provisioning script must write.

## Follow-up

- [ ] Enroll the control site as its own scope feature and spec (`rarebooks_control`, its own Frappe app and repo): the site registry, per site secrets, ClickPesa checkout links and webhook checksum, PayPal Subscriptions and webhook verification, computing `paid_until` (the paid period starts at trial end when someone pays early), pushing `receive_state`, and the return page. Production use of this feature waits on it.
- [ ] In the control site spec, confirm on the ClickPesa docs which header or field carries the webhook checksum and which key signs it, and whether a checkout link's status can be queried by `orderReference` (the docs check couldn't confirm either). The return URL is set in the ClickPesa dashboard, not per request, so the control site needs its own return page that redirects to the site's `return_url`.
- [ ] In the control site spec, check PayPal's current replacement for the deprecated `application_context` (return and cancel URLs) and the exact `approve` link rel, using the `paypal-best-practices` skill.
- [ ] Feature 7 reads `removal_on` (day 30) and the `lapsed` phase from this spec. It must decide whether a long lapsed site is ever removed.
- [ ] The `hookdeck/webhook-skills@paypal-webhooks` skill didn't install (the clone failed: `github.com` couldn't be resolved). Install it before the control site build: `npx skills add hookdeck/webhook-skills --skill paypal-webhooks -y`.
- [ ] PayPal's official MCP server (PayPal Agent Toolkit, npm `@paypal/mcp`, with a sandbox endpoint) would help the control site build create plans and inspect sandbox subscriptions. Connect it then, with sandbox credentials only, since its write tools run without asking.
- [ ] `paypal-best-practices` is installed but not in any `AGENTS.md`. Its conventions belong in the control site repo's `AGENTS.md`, not in this repo's root (this repo makes no PayPal call). Record it for `/sync`.
- [ ] Your provisioning script must write `books_control_url` and a fresh `books_control_secret` into each new hosted site's `site_config.json`, and register both on the control site.
