# 0005. Trial clock and read only lock: decision record

Build spec: [index.md](index.md).

## Context

RareBooks hosts many customer sites on its own bench, one Frappe site per customer, created by a signup flow or script. The business model (scope Slice 5) gives each new site 30 days: a 21 day free trial, a window to pay from day 22, read only from day 26 when unpaid, and removal on day 30 (feature 7). Today nothing tracks a site's clock or payment state, and nothing stops writes.

The forces:
- **The lock must hold on the server, for every role and every path.** The scope says "no matter the role". Frappe has many write paths: `/api/v2` documents, `frappe.client`, `run_doc_method`, about 33 whitelisted Books modules, desk at /app, background jobs, and around 60 places in the app's own code that write with `db.set_value`, `db_set`, raw SQL or `ignore_permissions`. Any path that's missed is a free subscription.
- **Viewing and export must keep working while locked.** Some reads write on the side: view logs, access logs on PDF and report export, and session updates.
- **One payment webhook can't reach many sites.** Providers send webhooks to a few fixed endpoints, and each site holding provider secrets multiplies the risk. Payment is split by market: ClickPesa (mobile money, one payment a year) for Tanzania, and PayPal Subscriptions (auto renewing, monthly or yearly) for everyone else.
- **Time zones.** "Day 26" means the business's own midnight. Customers are mostly in East Africa (UTC+3), and the setup wizard sets the site time zone after the site is created.
- **The app is AGPL and self hostable.** Self hosters, dev benches and CI sites must never lock.
- **Version 16 specifics.** Frappe 16 (checked on the local v16.55.2 bench) has a request level read only mode for maintenance (`frappe.app.setup_read_only_mode`: `frappe.flags.read_only` plus `frappe.db.begin(read_only=True)`). Its own logging defers to Redis under that flag (`make_access_log` and the view log use `deferred_insert`). `before_job` handlers get the job's `method` name.

## Options considered

### Enforcement

**Option A: a read only DB transaction per request, plus wildcard doc events (chosen).** A `before_request` hook opens a read only transaction on a locked site, except for a short allowlist. Wildcard `doc_events` refuse document writes first with a clear message.
- Pros: the database refuses every write path, including ones added later. It reuses the mechanism Frappe itself ships for maintenance, so Frappe's logging already copes with it. It's a small amount of code.
- Cons: writes that are only side effects (list settings, seen flags) fail too. The allowlist is a hand kept list. Desk shows Frappe's maintenance wording.

**Option B: wildcard doc events only.** Refuse in `before_insert`, `validate`, `before_submit`, `before_cancel`, `on_trash` and `before_rename` for every doctype, plus an audit of whitelisted methods that write directly.
- Pros: clear messages everywhere, and side effect writes keep working.
- Cons: `db.set_value`, `db_set`, raw SQL and Frappe core methods skip document events. The audit goes stale the moment someone adds a method, so the lock leaks quietly.

**Option C: Frappe maintenance mode set from outside.** The control side sets `maintenance_mode` and `allow_reads_during_maintenance` in site_config.
- Pros: no app code at all.
- Cons: login (the Sessions insert), the subscribe flow and the signed update that lifts the lock are all refused, so a locked owner can't pay from inside the site. Scheduled jobs stop too.

### Where the site keeps its state

**Option 1: a locked Single doctype holding facts, with the phase computed per request (chosen).**
- Pros: Frappe backed (the house rule for /books screens). Works on any server. The lock starts at midnight on its own. Track changes gives an audit trail.
- Cons: needs a controller guard against Administrator edits, and a cache to stay cheap per request.

**Option 2: site_config keys written by `bench set-config`.**
- Pros: no user can touch them, and they're cheap to read.
- Cons: needs the same host or SSH, isn't Frappe backed, has no audit trail, and the in process caching after a write needs care.

**Option 3: ask the control site live, with a short cache.**
- Pros: one source of truth.
- Cons: if the control site is down, the site can't decide whether to lock, and every customer site depends on one service's uptime.

### Who receives payment confirmation

**A central control site (chosen)** versus **each site's own webhook** (doesn't scale past the provider's endpoint cap, and spreads secrets) versus **a separate serverless service** (one more stack to run). The control site also becomes feature 7's removal runner, since a site can't safely remove itself.

## Rationale

The lock is the product's revenue boundary, so it has to fail closed. Option A puts the refusal in the database. That's the only layer every write path goes through, so a whitelisted method added next year is locked without anyone remembering. Frappe 16 already ships and tests this exact mechanism for maintenance, which is why export and viewing keep working: its access and view logs defer under `frappe.flags.read_only`. The doc events layer is there only for a good message on the common path. Option B was the runner up. It's friendlier, but a lock that leaks through `db.set_value` is worse than a lock with a rough message. Option C fails the "pay from inside the site" requirement.

Storing facts instead of a phase follows "never store derived values" and removes a whole class of failures. No job has to flip the lock at midnight, and a control site outage can't lock or unlock anyone. The per site HMAC secret, the time window and the forward only `last_synced_on` make the guest push endpoint safe without the site ever holding a provider key. Gating everything on `books_control_url` keeps the AGPL self hosting promise.

Small calls made while writing:
- **Phase cache**: `frappe.get_cached_doc`, whose cache saving clears, over a Redis key with a TTL (runner up). Zero staleness after a push.
- **Job rule**: tell scheduled jobs apart by the `run_scheduled_job` method name rather than by the job's user (runner up), since Frappe runs scheduled jobs as Administrator, and Administrator can also enqueue by hand.
- **Error type**: `SiteLockedError` as a `ValidationError` with HTTP 403 rather than `PermissionError` (runner up), so the client can tell "not allowed for your role" apart from "site locked".
- **Pull spacing**: pull only when the Subscription page loads with `refresh` or after returning from checkout, not on every boot (runner up), to keep the control site off the hot path.
- **Renew notice**: 14 days before `paid_until` for ClickPesa only. A 7 day notice (runner up) is too short for a yearly mobile money payment that may need a budget approval.

## References

**Project sources**:
- `AGENTS.md` and `frappe_books/AGENTS.md`: business rules live in the controller, `require_type_annotated_api_methods`, roles, no raw SQL in reports, and "there are no `doc_events`".
- `docs/framework-backed-doctypes.md`: singles load at startup, and virtual and Frappe owned settings.
- Frappe v16.55.2 source on the local bench: `frappe/app.py` `setup_read_only_mode`, `frappe/database/database.py` (`InReadOnlyMode`), `frappe/core/doctype/access_log/access_log.py` (`deferred_insert`), `frappe/model/document.py` (`doc_events` `"*"`, view log), `frappe/utils/background_jobs.py` (`before_job` gets `method`), `frappe/rate_limiter.py`.
- `frappe_books/settings.py` (`company_country`, `regional_code`), `frontend/src/utils/export.ts` (client side CSV export).
- Specs 0001 to 0004: no overlap; this is the first billing decision.
- Installed skill `paypal-best-practices` (`paypal/ai-toolkit`).

**Practices & standards**:
- Fail closed for access control; enforce at the lowest shared layer.
- HMAC SHA256 webhook signing with a timestamp window and constant time compare; replay protection with a forward only marker.
- Never store derived values; compute at read time.
- Audit trail for money and access state changes.
- Rate limit every public endpoint.
- Secrets in config, never in the database or code.

**Links** (checked during the design conversation):
- ClickPesa, introduction (auth token, no sandbox, KYC limits): https://docs.clickpesa.com/home/introduction
- ClickPesa, generate checkout link: https://docs.clickpesa.com/api-reference/collection/generate-checkout-link/generate-checkout-link
- ClickPesa, webhooks: https://docs.clickpesa.com/home/webhooks
- ClickPesa, checksum (HMAC SHA256 over sorted JSON): https://docs.clickpesa.com/home/checksum
- PayPal, create subscription: https://developer.paypal.com/api/subscriptions/v1/subscriptions-create
- PayPal, show subscription (`billing_info.next_billing_time`): https://developer.paypal.com/api/subscriptions/v1/subscriptions-get
- PayPal, webhook event names: https://developer.paypal.com/api/rest/webhooks/event-names
- PayPal, verify webhook signature: https://developer.paypal.com/api/webhooks/v1/definitions/verify_webhook_signature
