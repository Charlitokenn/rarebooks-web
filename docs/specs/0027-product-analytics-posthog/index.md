# 0027. Product analytics with PostHog in /books and the control site

**Date**: 2026-11-28
**Status**: Proposed

## Summary

This spec adds PostHog (a product analytics service) to the `/books` app and the billing control site, and joins both to the PostHog setup the marketing site already has (spec 0022). The `/books` app sends screen views and a few named usage events. The control site sends the business lifecycle: sign up, trial, checkout, payment, lapse and removal. No email, person's name or record name ever leaves a shop: a person is a keyed hash, and a shop is identified only by its public site address. Shops can turn analytics off, self hosted installs never send anything, and every piece stays off until its key is configured.

## Requirements

**User stories**:
- As the RareBooks operator, I want to see which screens and features shop users actually use, so that I know what to improve and what nobody needs.
- As the operator, I want one funnel from a marketing click to a paying shop, so that I can see where people drop out.
- As the operator, I want frontend errors from real shops reported, so that I find bugs before a customer tells me.
- As a shop's Books Manager, I want to turn usage analytics off for my shop, so that I decide what leaves my site.

**Acceptance criteria**:

*The /books app (rarebooks-web)*

- **AC-1**: Boot block. `extend_bootinfo` adds `books.analytics`. It is `None` unless every one of these holds: `books_control_url` is in the site config (a hosted site), `books_posthog_key` and `books_posthog_salt` are both set (read with `frappe.conf`, so the Frappe Cloud bench's `common_site_config.json` provides them), Books System Settings `share_usage_analytics` is on, the user is not `Administrator`, and the user has at least one of Books User, Books Manager or Books Cashier. Otherwise it is `{key, distinct_id, site_key, roles, country_code, language}`, and `books_posthog_salt` itself is never in it.
- **AC-2**: Person id. `distinct_id` is the first 32 hex characters of HMAC SHA256 over `"<site>:<user>"` keyed with `books_posthog_salt`, where `<site>` is `frappe.local.site` and `<user>` is `frappe.session.user`. The same user on the same site always gets the same id; the email never appears in any event.
- **AC-3**: Lazy load, nothing when off. `frontend/src/utils/analytics.ts` is the only module that imports `posthog-js`, and it imports it with a dynamic `import()` after the app has mounted. When `books.analytics` is `None`, no PostHog chunk is fetched and no request goes to any `posthog.com` host.
- **AC-4**: Init options. `posthog.init(key, …)` runs with exactly: `api_host: "https://eu.i.posthog.com"`, `ui_host: "https://eu.posthog.com"`, `capture_pageview: false`, `capture_pageleave: false`, `autocapture: false`, `disable_session_recording: true`, `disable_surveys: true`, `advanced_disable_flags: true`, `person_profiles: "identified_only"`, `persistence: "localStorage"`, `capture_exceptions: {capture_unhandled_errors: true, capture_unhandled_rejections: true, capture_console_errors: false}`, and the `before_send` hook of AC-6. Errors thrown before PostHog has loaded are not captured (posthog-js also fetches its exception handler lazily); this is accepted. Then `identify(distinct_id, {books_roles, language})`, `group("site", site_key)`, and `register({site_key, country_code, app_version})`, so every event carries `site_key` as a plain property too.
- **AC-5**: Pageviews by route template. After each completed navigation (`router.afterEach(to, from, failure)`, skipped when `failure` is set, so aborted and redirected navigations send nothing), one `$pageview` is sent through `track()` (so the first one, before PostHog loads, waits in the AC-8 queue) with `route_name` (the vue-router route name), `route_template` (`to.matched.at(-1).path`, for example `/edit/:schemaName/:name`) and `schema_name` when `to.params.schemaName` exists. A navigation where only the query string changes (list filters) sends nothing. The real `name`, `pageTitle` or other params are never sent.
- **AC-6**: No record names. `before_send` rewrites every event: `$current_url` becomes `<origin>/books<route_template>` with no query string or hash, `$pathname` becomes `/books<route_template>`, and `$title`, `$referrer`, `$referring_domain` and every `$initial_*` URL property are removed or rewritten the same way. For `$exception` events it also replaces each `$exception_list[].value` and `$exception_values` entry with the exception type (and, for a server error, `exc_type` and status, AC-9), so no error message leaves the site. Unit tests feed a `$pageview` whose URL holds a customer name and an `$exception` whose message holds one, and assert no property still contains it.
- **AC-7**: Doc events. In `src/frappe/document.ts`: `doc_created` from `_sync` after a successful insert, where "new" is read before `_insert()` runs (so a deduped `sync()` call never counts twice, and a draft autosaved on first save counts once); `doc_submitted` after a successful `submit()` call (not when it returns early for a doc that isn't submittable); `doc_cancelled` after a successful `cancel()`, once for the main doc even when linked docs are cancelled with it. Each carries only `schema_name`. Singles (`schema.isSingle`, the settings screens) and child table schemas send none. A failed call sends nothing. Plus `pos_sale_completed` in `submitSale` in `src/utils/posCheckout.ts`, with `payment_method_count` = `tenders.length` (the same sale also sends `doc_submitted`, which is intended); `import_finished` when an Import Wizard run ends in `ImportWizard.vue`, with `schema_name`, `row_count` (successes plus failures from `dataImport.getLogs()`) and `failed_count`; and `print_opened` when `PrintView` mounts and when `printDocument()` runs, with `schema_name`. No event carries a doc name, a party, an amount or any field value.
- **AC-8**: Early events. `track()` called before PostHog has loaded is queued in memory (at most 50, oldest dropped) and sent once it loads. When analytics is off, `track()` does nothing and the queue is never filled.
- **AC-9**: Errors. Uncaught errors and unhandled promise rejections reach PostHog through its exception autocapture. `handleError` in `src/errorHandling.ts` also calls `captureException` for an error that is stored (`shouldStore` true) and is not a `ValidationError` (which includes `MandatoryError`). `getServerError` in `src/web/api.ts` attaches `excType` and `status` to the error it builds, so `handleError` and `before_send` can read them. For any error, only the exception type and stack are sent, plus `exc_type` and status for a server error, never the message, since it can name a record (AC-6). An error `handleError` captures is marked so autocapture doesn't send it a second time.
- **AC-10**: Opt out. Books System Settings gets a Check field `share_usage_analytics` (label "Share usage analytics with RareBooks", default 1, with a translated description that says what is sent). Only Books Manager can change it, like the rest of that single. Its `on_update` clears the cached boot info for every user (`frappe.cache.delete_key("bootinfo")`), so AC-1 gives `None` from each user's next page load.
- **AC-11**: Silent failure. With PostHog blocked or down, or the chunk failing to load, `/books` works as before, shows no toast or dialog, and logs at most one `console.warn`. Analytics never delays first paint or a save.

*The control site (rarebooks_control)*

- **AC-12**: One provider. `rarebooks_control/providers/posthog.py` is the only module that talks to PostHog. Its `send(events: list[dict])` POSTs one batch to PostHog's capture v1 endpoint `https://eu.i.posthog.com/i/v1/analytics/events` with `requests`, the key in an `Authorization: Bearer` header, a 10 second timeout and no redirect followed. The body is `{created_at, batch: [{event, uuid, distinct_id, timestamp, properties}]}` with every field a string except `properties` (an object, never null). Capture v1 is used, not the legacy `/batch/`, because it answers per event and rejects a wrong key, where `/batch/` answers 200 and drops the events silently. A per event `drop` or `warning` result is logged like a failure (AC-13). Its key comes from the site config `posthog_project_key`; with no key it returns and sends nothing. Tests patch `send`.
- **AC-13**: After commit, never in the way. Every lifecycle event is handed to `analytics.queue_event(...)`, which builds the whole batch (the event, its `$groupidentify` and every property) right away, inside the caller's transaction and from the row the caller holds, as plain JSON (no `Decimal`, no doc objects), then calls `frappe.enqueue(..., enqueue_after_commit=True, job_id=<event uuid>, deduplicate=True)` on the short queue. The job re-reads nothing. Each event carries a deterministic `uuid` (uuid5 over event, site or signup, and the moment or local date), so a rerun is dropped by PostHog. A rolled back transaction sends nothing. A failed send logs one line with the `rarebooks_control.analytics` logger (never the key, never the request body), is not retried, never writes an Error Log, and never changes a signed answer, a billing write or an operator email.
- **AC-14**: The events and where they fire.
  - `site_requested`: in `onboarding.request_site`, after the Books Signup insert and before its `frappe.db.commit()`, with `signup`. No group (there is no site yet).
  - `site_ready`: in `onboarding.mark_ready`, after its `status != "Preparing"` guard and the save, so a repeat sends nothing.
  - `signup_failed`: `fail_signup(row, lines, kind)` gets a new `kind` argument, passed by its three callers: `timeout` (`fail_if_slow`), `owner_step` (`run_owner_step`), `domain` (`fail_signup_of_site`). Sent as `reason_kind` after the guard that returns for a row already Ready, Failed or Released. Never the free text.
  - `checkout_started`: in `billing.new_checkout`, with `provider`, `plan`, `billing_period`, enqueued after the function's final save (after the ClickPesa link call), so a failed link call that rolls back sends nothing.
  - `payment_confirmed`: in `billing.apply_clickpesa`, and in `billing.apply_paypal` only when `payment` is set (not for status only events or `adopt_subscription` without a payment), after `row.save()`, so `$group_set` holds the new `paid_until`. It carries `provider`, `plan`, `billing_period`, `currency`, `is_renewal` (whether `last_payment_on` was set, read before `row.update` overwrites it), and `amount` from the provider payment (ClickPesa `collectedAmount` through `decimal_amount`, PayPal `amount`), as a string: `whole_amount` for TZS, 2 decimals with `ROUND_HALF_UP` for USD. The Mismatch branches never reach the apply functions, so they send nothing.
  - `auto_renew_ended`: in `billing.apply_paypal` when `auto_renews` goes from 1 (read before the `row.update`) to 0, with `paypal_status` (the subscription status that ended it: cancelled, suspended or expired).
  - `site_removed`: in `removal.mark_removed`, only when the row was not already Removed.
- **AC-15**: Date events. A daily job `analytics.daily` (in `scheduler_events["daily"]`, so about 00:00 UTC, which is 03:00 in Dar es Salaam) looks only at Books Hosted Site rows with `status` Active, `exempt` 0 and `pool_status` empty or Claimed (unclaimed warm pool sites are left out). It sends `trial_ended_unpaid` for each such site whose `trial_ends_on` was yesterday in the site's time zone (`state.site_zone`) and whose `paid_until` is empty, and `subscription_lapsed` for each such site whose `paid_until` was 3 days ago in its time zone (the 3 days leave room for a late PayPal renewal). Their `uuid` uses the site's local date, so a second run the same day sends nothing new. A missed day's run loses that day's events; this is accepted.
- **AC-16**: Groups and ids. Every control event except `site_requested` carries `$groups: {"site": <site>}` and `site_key: <site>`, and is sent in the same batch as a `$groupidentify` for that site with `$group_set` = `{phase, provider, billing_period, auto_renews, exempt, trial_ends_on, paid_until, time_zone, created_on}`. `phase` is `removed`, `exempt`, `paid` (`paid_until` today or later in the site zone), `trial` (`trial_ends_on` today or later) or `lapsed`. The site's public address (`site`, for example `duka.rarebooks.cc`) is sent on purpose as the shop id, since it is already public in DNS; the company name, the owner's email and name are never sent. `distinct_id`: for `site_requested`, the `posthog_distinct_id` from that request when valid, else `signup:<name>`; for every other event, the site's Books Signup `posthog_distinct_id` when there is one, else `site:<site>`. Reusing the marketing anonymous id makes it the shop's lifecycle person in PostHog; this is accepted, since it is the only id the funnel shares.

*The funnel link (rarebooks-site and rarebooks_control)*

- **AC-17**: Anonymous id at sign up. `src/pages/api/onboarding/signup.ts` reads the `ph_<PUBLIC_POSTHOG_KEY>_posthog` cookie from the request, URL decodes it, parses the JSON and takes its `distinct_id`, and when it matches `^[A-Za-z0-9-]{1,64}$` adds it as `posthog_distinct_id` to the `request_site` body. A missing, broken or odd cookie sends no field and never fails the sign up. `request_site` stores a value that matches the same pattern in Books Signup `posthog_distinct_id` and ignores anything else, without refusing.

*Privacy and rollout*

- **AC-18**: Privacy page. `rarebooks-site/src/pages/privacy.astro` gets a line for the app: "PostHog (EU cloud), inside RareBooks: which screens you open, which kinds of records you create, submit or cancel, and app errors, under a random id, along with your shop's web address. It never receives your name, email, your customers' names or any amounts from your books. A Books Manager can turn it off in Settings." The marketing line from spec 0022 stays.
- **AC-19**: Off by default everywhere. With no `books_posthog_key`, no `posthog_project_key` or no `PUBLIC_POSTHOG_KEY`, that part sends nothing, and every existing test and CI run passes with none set.

## Decision

**Chosen option**: Option 2: client events in /books with route templates and a keyed hash id, server lifecycle events from the control site through one provider module, all into the one PostHog EU project spec 0022 uses.

Reasoning and options: see [rationale.md](rationale.md).

**Implementation skills**: `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`, the lazy analytics module) · `vue-router-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-router-best-practices/`, the `afterEach` pageview) · `frappe-app-dev` (the boot block, the settings field, the control site queue) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `workers-best-practices` (`cloudflare/skills`, `rarebooks-site/.agents/skills/workers-best-practices/`, the cookie read in the sign up route)

## Feature design

**Data model sketch**:

| DocType | Repo | New field | Type | Required | Notes |
|---|---|---|---|---|---|
| Books System Settings (single) | rarebooks-web | `share_usage_analytics` | Check | default 1 | Books Manager writes, everyone reads (existing single permissions) |
| Books Signup | rarebooks_control | `posthog_distinct_id` | Data (64) | nullable | read only in the desk; set once by `request_site`; no index needed (read by the row's own name) |

No new DocType and no relationships. PostHog is the store for events; nothing about events is kept in MariaDB.

**State transitions**: the `phase` group property is derived each time it is sent (AC-16), never stored: `trial` → `paid` or `lapsed`; `paid` → `lapsed` → `paid` (a late payment); any → `removed`; `exempt` overrides all but `removed`.

**API surface**:

| Surface | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `books.analytics` boot block (`frappe_books/analytics.py` `boot_block()`) | session boot | config, settings, session user | `{key, distinct_id, site_key, roles, country_code, language}` or `None` | signed in user | never raises; any failure gives `None` |
| `analytics.ts` `startAnalytics(block)`, `track(event, props)`, `captureError(error)` | client functions | the boot block; event name and allowed props | events to PostHog | n/a | load failure: one warn, then no op (AC-11) |
| `request_site` (existing) | POST, signed | new optional `posthog_distinct_id: str` | unchanged | `marketing_secret` signature (spec 0014 AC-8) | a bad value is dropped, never a refusal |
| `providers/posthog.send(events)` | Python | list of event dicts | none | `posthog_project_key` | timeout or non 2xx: one log line (AC-13) |
| `analytics.queue_event(event, site=None, signup=None, props=None)` | Python | event name, the site or signup | an after commit job | internal | none raised to the caller |
| `analytics.daily()` | scheduler, daily | none | the AC-15 events | scheduler | one site failing skips only that site |
| PostHog capture v1 | POST `https://eu.i.posthog.com/i/v1/analytics/events` | `Authorization: Bearer <key>`; `{created_at, batch: [{event, uuid, distinct_id, timestamp, properties}]}` | per event results (`ok`, `warning`, `drop`, `retry`) | project key | 400 `request_parsing_error` rejects the whole batch; a wrong key is refused |

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| Boot block | `key` | `frappe.conf.books_posthog_key` (bench common config) |
| Boot block | `distinct_id` | HMAC SHA256 of `frappe.local.site:frappe.session.user` with `frappe.conf.books_posthog_salt` (AC-2) |
| Boot block | `site_key` | `frappe.local.site` (stays the same when a custom domain is added) |
| Boot block | `roles` | `frappe.get_roles()` filtered to the three Books roles, sorted |
| Boot block | `country_code` | `regional_code()`, already in the boot |
| Boot block | `language` | `frappe.local.lang`, sent as Frappe gives it (for example `en` or `sw`) |
| Boot block | TS type | an `analytics` entry next to `push` in the `window.frappe.boot.books` declaration in `src/web/api.ts` |
| Boot block | hosted check | `frappe.conf.books_control_url` present |
| Boot block | opt out | Books System Settings `share_usage_analytics` |
| `register` | `app_version` | the `frappe_books` app version (`frappe_books.__version__`) |
| `$pageview` | `route_name`, `route_template`, `schema_name` | `to.name`, `to.matched.at(-1).path`, `to.params.schemaName` |
| Doc events | `schema_name` | the `FrappeDoc`'s schema name |
| `doc_created` | "is new" | read in `_sync` before `_insert()` runs |
| `pos_sale_completed` | `payment_method_count` | `tenders.length` in `submitSale` (`src/utils/posCheckout.ts`) |
| `import_finished` | `row_count`, `failed_count` | `success.length + failed.length` and `failed.length` from `dataImport.getLogs()` in `ImportWizard.vue` |
| Server error capture | `exc_type`, status | `excType` and `status` attached by `getServerError` in `src/web/api.ts` |
| Control events | `site_key`, `$groups.site` | Books Hosted Site `site` |
| Control events | `distinct_id` | Books Signup `posthog_distinct_id` (by `hosted_site`), else `site:<site>`, else `signup:<name>` |
| `checkout_started`, `payment_confirmed` | `provider`, `plan`, `billing_period` | the Books Checkout row and its Books Plan |
| `payment_confirmed` | `amount`, `currency` | ClickPesa `collectedAmount` (`decimal_amount`) or PayPal `amount`; TZS via `whole_amount`, USD 2 decimals `ROUND_HALF_UP` |
| `payment_confirmed` | `is_renewal` | `row.last_payment_on` set, read before `row.update` |
| `auto_renew_ended` | the 1 → 0 change, `paypal_status` | `row.auto_renews` read before `row.update` in `apply_paypal`; the subscription's `status` |
| `signup_failed` | `reason_kind` | the new `kind` argument of `fail_signup` (`timeout`, `owner_step`, `domain`) |
| Every control event | `uuid` | uuid5 over event name, site or signup, and the moment (or local date for daily events) |
| `$group_set` | every property | Books Hosted Site columns, `phase` derived with `state.site_zone` (AC-16), `created_on` = row `creation` |
| Daily job | "yesterday", "3 days ago" | today in `state.site_zone(row.time_zone)` |
| Funnel | `posthog_distinct_id` | the `ph_<key>_posthog` cookie on rarebooks.cc, read by the Worker (AC-17) |
| Control send | key | site config `posthog_project_key` |

**Key invariants**:
- No event, from any repo, carries an email, a person's name, a company name, a doc name, a party, a URL with a record name or query string, an error message, or an amount from a shop's books. The only amounts are RareBooks' own subscription payments. The shop's public site address is sent, on purpose, as its id.
- `books_posthog_salt` never leaves the server.
- Self hosted Books sites (no `books_control_url`) send nothing, whatever their config.
- A PostHog failure never changes what a user sees, what billing writes, or what a signed endpoint answers.
- All three repos send to the same PostHog EU project.

**Security model**: the project keys (`phc_…`) are public by design and may ship to browsers. The salt is a secret in bench config, like `encryption_key`, and is never logged or booted. `posthog_project_key` on the control site is never logged (the provider rule). Every shop user role is counted alike; Administrator and staff without a Books role are left out (AC-1). The site address the owner picked can contain their business name; it is sent knowingly, as it is public already. The only person data PostHog gets is a keyed hash and the browser's IP, and the RareBooks project already has `anonymize_ips` on, so the IP is not stored. GDPR applies to EU visitors of the marketing site and to any shop users in the EU: there is no personal data in events, the privacy page says what is sent (AC-18), and a shop can opt out (AC-10).

**Configuration required**:
- `books_posthog_key`: the PostHog EU project key (public `phc_…`), in the Frappe Cloud bench's common site config.
- `books_posthog_salt`: 32 or more random characters, in the same bench config. A secret; never change it, or every person id changes.
- `posthog_project_key`: the same project key, in the control site's own site config.
- `PUBLIC_POSTHOG_KEY`: already exists in `rarebooks-site` (spec 0022); it must be the same project.
- The project: PostHog EU project "RareBooks" (id 372817, `api_host` `https://eu.i.posthog.com`), checked through the PostHog connector on 2026-11-28. Its public project key is in the project settings; all three repos use that one key. It had ingested no events yet, so spec 0022's `PUBLIC_POSTHOG_KEY` is not live either.
- Group analytics is a paid add on (confirmed in PostHog's docs). Once on, it bills every identified event, not only grouped ones. Until you turn it on, use `site_key` as a breakdown instead of the group (see rationale).

**Critical test scenarios**:
- Happy path: on a hosted test site with the keys set, sign in as a Books User, open a Customer, submit a Sales Invoice: PostHog receives `$pageview` with `route_template=/edit/:schemaName/:name` and `doc_submitted` with `schema_name=SalesInvoice`, and no payload holds the customer's name, verifies **AC-4**, **AC-5**, **AC-6**, **AC-7**
- Off: a site with no `books_control_url`, a site with the opt out off, and Administrator each load `/books` with no request to any PostHog host and no PostHog chunk, verifies **AC-1**, **AC-3**, **AC-10**
- Hash: the same user on two sites gets two ids, the same user twice gets one id, and the id is not the SHA256 of the email, verifies **AC-2**
- Failure: block `eu.i.posthog.com`; `/books` loads and saves with no toast; verifies **AC-11**. On the control site, `send` raising a timeout during `apply_clickpesa` leaves the payment applied and the push queued, verifies **AC-13**
- Rollback: a `confirm_clickpesa` that rolls back enqueues nothing, verifies **AC-13**
- Lifecycle: each AC-14 call site enqueues its event once with the listed properties and a `$groupidentify`; a repeat `mark_removed`, `mark_ready` or `fail_signup` sends nothing more; `payment_confirmed` has `is_renewal` false on a first payment and true on the next, verifies **AC-13**, **AC-14**, **AC-16**
- Error privacy: a server error whose message names a customer reaches PostHog with only its type, `exc_type` and status, verifies **AC-6**, **AC-9**
- Pool sites: an unclaimed pool site whose trial date passed gets no daily event, and running `analytics.daily` twice sends each event once, verifies **AC-15**
- Dates: sites in `Africa/Dar_es_Salaam` and `America/Los_Angeles` with `trial_ends_on` yesterday in their own zone get `trial_ended_unpaid`; a paid one does not; `paid_until` 3 days ago gives `subscription_lapsed`, verifies **AC-15**
- Funnel: a sign up with a valid cookie stores the id and `site_ready` uses it as `distinct_id`; a broken cookie signs up normally with no field, verifies **AC-17**
- Errors: a thrown `TypeError` and a stored server error reach PostHog, the server one without its message; a `MandatoryError` does not, verifies **AC-9**

## Build plan

Tracer Bullet: the first slice runs one real event from a shop to PostHog end to end, then each later slice thickens one side.

1. The thread: `frappe_books/analytics.py` `boot_block()` with every AC-1 condition and the AC-2 hash, wired into `extend_bootinfo`; add `posthog-js` (pinned) to `frontend/package.json`; `src/utils/analytics.ts` with the lazy import, the AC-4 options, `before_send` and the `afterEach` pageview; Python tests for the boot block and node tests for `before_send`; checked on a hosted test site against the real EU project, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-19**
2. Opt out: the `share_usage_analytics` field on Books System Settings (doctype JSON, 1 space indent, translated label and description) and its boot check, with tests, satisfies **AC-10**
3. Usage events: `track()` with the early queue; the three doc events in `document.ts`; `pos_sale_completed`, `import_finished`, `print_opened` at their screens; node tests that a failed save sends nothing, satisfies **AC-7**, **AC-8**
4. Errors and failure: exception autocapture, the `handleError` call with the server error rule, the one warn on load failure; a Playwright test with PostHog blocked, satisfies **AC-9**, **AC-11**
5. Control thread: `providers/posthog.py` `send`, `rarebooks_control/analytics.py` with `queue_event`, the group identify builder and `phase`; the first two events (`site_ready`, `payment_confirmed`) wired in; tests patching `send`, including the rollback case, satisfies **AC-12**, **AC-13**, **AC-16**
6. The rest of the lifecycle: `site_requested`, `signup_failed` with the new `kind` argument at its three callers, `checkout_started`, `auto_renew_ended`, `site_removed`; the `analytics.daily` job in `hooks.py` `scheduler_events["daily"]`; tests per call site and for the date rules, satisfies **AC-14**, **AC-15**
7. Funnel link: the Books Signup `posthog_distinct_id` field (via `bench migrate`), `request_site` accepting it, and in `rarebooks-site` the cookie read in `signup.ts` with a node test, satisfies **AC-17**
8. Privacy and rollout: the `privacy.astro` line; set the bench config on Frappe Cloud and the control site config; check the first events arrive the same day, satisfies **AC-18**, **AC-19**

## Consequences

**Positive**:
- One PostHog project shows the marketing click, the sign up, the trial, the payment and in app use together.
- Frontend errors from real shops are reported with no new error tracking service.
- No personal or shop business data leaves a site, so the privacy story stays simple.

**Negative / tradeoffs**:
- A new frontend dependency (`posthog-js`, loaded lazily) to keep updated, and its option names change across versions.
- Ad blockers drop some `/books` events, since they go straight to `eu.i.posthog.com`; trends are fine, exact counts are not.
- Per shop views need either the paid group analytics add on or a `site_key` breakdown.
- The person in `/books` (hash id) and the person in the funnel (marketing anonymous id) are not merged; they meet only through the `site` group.
- The date events can be lost on a day the scheduler doesn't run.
- `before_send` must be kept in step with any new route whose params hold a name; a new route that bypasses vue-router params would leak.

**Neutral**:
- Two new fields and one migration in two repos; three config keys to set once.
- The control site gets its first daily analytics job.

## Follow-up

- [x] The PostHog connector (MCP server) is connected. `/develop` and `/check verify` use it to confirm events arrive in project 372817 and that no payload holds a record name. Record it on the `MCP servers:` lines when `/sync` runs.
- [ ] No PostHog Agent Skill was found in the `npx skills` registry (searched 2026-11-28). The PostHog connector serves its own skills through `learn`, which `/develop` should load before PostHog work. Record that in the `## Agent skills` sections when `/sync` runs.
- [ ] Decide later whether to buy the group analytics add on. Nothing in the code changes either way, but it bills every identified event, and identified events already cost about 4 times anonymous ones past the free million.
- [ ] Set spec 0022's `PUBLIC_POSTHOG_KEY` in production too; the project has no events yet, so the funnel has no marketing side until it is live.
- [ ] After build, `/sync` adds `frontend/src/utils/analytics.ts` to `frontend/AGENTS.md` and `providers/posthog.py` to the rarebooks_control provider rules.
