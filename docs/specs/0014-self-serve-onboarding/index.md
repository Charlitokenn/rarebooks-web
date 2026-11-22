# 0014. Self serve onboarding through a warm pool of Books sites

**Date**: 2026-11-21
**Status**: Proposed

Amends: spec [0010](../0010-frappe-cloud-hosting/index.md) (AC-1 and AC-13: the removal round and pushes skip pool sites, and the Frappe Cloud client gains `new_site`), spec [0012](../0012-custom-domains-registration/index.md) (AC-2: a label held by a Books Signup is taken; AC-8 and the domain eligibility rule: a Claimed site's Primary step makes its request Ready, and its steps wait for the owner; AC-11 and AC-12: a discarded site releases its label after cleanup; `_fail_domain` sends no email for a Claimed site) and spec [0013](../0013-archived-site-proof/index.md) (a Discard case uses the same archive proof). Every other rule in those specs still holds.

## Summary

A visitor signs up on the marketing site, picks a subdomain and a company name, and gets their own Books site at `<subdomain>.rarebooks.cc` with a fresh 30 day trial, with no step from you. The control site keeps a small warm pool (sites already built on Frappe Cloud, with Books installed and their config working), so a sign up only has to claim one, name its owner, restart its trial clock and give it its address. The marketing site and the control site talk over the same signed HTTPS calls the hosted sites already use, with a secret of their own. The desktop license key trial and every desktop license part of the marketing site are retired.

## Requirements

**User stories**:
- As a visitor, I want to sign up, choose my address and land in my own Books site, so I can try RareBooks today without waiting for anyone.
- As a visitor, I want to see where my site is while it is prepared, and get an email when it is ready, so I can close the page and come back.
- As the operator, I want a failed or stuck sign up to alert me once and never leave a half made site running unbilled, so the pool needs no babysitting.
- As the operator, I want one person or one script unable to create sites without limit, so the pool and my server can't be drained.

**Acceptance criteria**:

*Marketing site (`rarebooks-site`)*
- **AC-1**: Only a visitor signed in with Clerk, whose primary email is verified, can reach `/dashboard/start`. The form asks for a subdomain and a company name (1 to 140 characters, trimmed), and sends the browser's IANA time zone (`Intl.DateTimeFormat().resolvedOptions().timeZone`, UTC when missing). The owner's email, first name and last name come from the Clerk user on the server, never from the form. A blank Clerk first name becomes the part of the email before the `@`; a blank last name stays blank. The email is the one at sign up; a later change in Clerk does not reach the Books site.
- **AC-2**: While the visitor types a subdomain, the form asks `POST /api/onboarding/check-subdomain` (debounced 400 ms) and shows "available" or the reason it is refused (spec 0012 AC-1's rule, or "taken"). The Worker caches each answer for 30 seconds per label in KV and forwards a cache miss to the control site's `check_subdomain`. At most 30 checks a minute per Clerk user (KV counter); over that the field shows "slow down" and the form still submits.
- **AC-3**: `POST /api/onboarding/signup` verifies the Cloudflare Turnstile token with Siteverify first, then counts the attempt against the client IP (`CF-Connecting-IP`) in a KV counter keyed by IP and UTC hour, at most 3 an hour, then calls the control site's `request_site`. A failed Turnstile answers 403 and does not count; an attempt over the limit answers 429; both happen before any control site call. A repeat by a user who already has a D1 row returns that row and does not count. On success the Worker writes the D1 `signups` row (`INSERT ... ON CONFLICT(clerk_user_id) DO UPDATE` with the same `request_id`, so a retry is safe) and the browser goes to `/dashboard`. A 409 `already_used` shows "This email already has a RareBooks site. Contact support" with the support email.
- **AC-4**: `/dashboard` shows the signed in user's request through `GET /api/onboarding/status`. The Worker finds the request by Clerk user id in D1, or, when D1 has no row, asks the control site's `signup_status` by `clerk_user_id` alone and writes the missing row. It is polled every 5 seconds for the first 2 minutes, then every 15 seconds, while the status is Queued, Claiming or Preparing, and stops on Ready or Failed. Labels: Queued and Claiming show "Getting your site"; Preparing shows "Setting up your address"; Ready shows "Ready" with the address and a "Set your password" button. The address is returned only at Ready. Failed shows "We hit a problem setting up your site. We're on it and will email you." with the support email, and never `failed_reason`. A user with no request sees the start form.
- **AC-5**: `GET /dashboard/site/open` (Clerk signed in) asks the control site's `owner_link` for the user's request and redirects (302, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`) to the URL it returns: a fresh password set link while the owner has not set a password yet, else the site's `/login`. Before Ready it redirects to `/dashboard`. The Worker never logs the URL (the route logs only the status code).
- **AC-6**: `POST /api/onboarding/notify` accepts only a request signed by the control site with the marketing secret (spec 0005 signing, `issued_at` within 5 minutes) and answers signed. The notice carries `request_id`, `status`, `email` and `first_name`. An unknown `request_id` writes the D1 row from the notice and goes on. On `Ready` it sends the "Your RareBooks site is ready" email through Resend, with a button to `/dashboard/site/open` and never the password link itself, and sets `ready_emailed_at` only after Resend accepts it (at least once: a crash between the two can send it twice, never zero times). On `Failed` it sends the "We're on it" email the same way with `failed_emailed_at`. A notice for an email already sent answers 200 and sends nothing. A Resend failure answers a signed 503, so the control site retries.
- **AC-7**: The desktop license key trial is gone: `/api/license`, `/api/create-license`, `/api/deactivate-key`, `/api/license-info`, `/api/redemption`, `/redemption`, `/trial/download`, the trial modal and form, the dashboard license, device and renewal parts and their email templates are removed, `KEYMINT_API_KEY` is unused, and every "Start free trial" link goes to Clerk sign up, then `/dashboard/start`. The D1 `trials` table is exported with `wrangler d1 export` to a file stored in the R2 export bucket under `archive/` and on your machine, then dropped by a migration. Clerk accounts the old trial made stay; their holders sign in (or reset the generated password through Clerk) and see the start form like anyone new. No key holder is migrated or emailed.

*Control site (`rarebooks_control`)*
- **AC-8**: Every marketing call (`check_subdomain`, `request_site`, `signup_status`, `owner_link`) is a guest POST to `rarebooks_control.onboarding.<name>`, signed with Books Onboarding Settings `marketing_secret` exactly as spec 0005 and spec 0008 AC-5 sign site calls (HMAC SHA256 of the raw body in `X-Books-Signature`, `issued_at` within 5 minutes, every answer including a 401 signed through `signed_response`). Each endpoint has its own limit per minute, counted with spec 0008's cache counter: `check_subdomain` 120, `request_site` 30, `signup_status` 600, `owner_link` 60. A bad signature answers a signed 401 and counts toward spec 0008 AC-22's signature failure alert.
- **AC-9**: `request_site` takes `clerk_user_id`, `email`, `first_name`, `last_name`, `company_name`, `subdomain` and `time_zone`, and checks in this order, writing nothing until all pass: (1) a Books Signup with the same `clerk_user_id` exists, in any status: return it as it is (idempotent; a different subdomain or company is ignored); (2) Books Onboarding Settings `paused`: signed 503 `{"refusal": "paused"}`; (3) a Books Signup with the same `email_key` exists, in any status: signed 409 `{"refusal": "already_used"}`; (4) `company_name` 1 to 140 characters and `time_zone` a zone the server knows (else UTC): signed 422; (5) spec 0012 AC-1 and AC-2 as amended by AC-21: signed 422 with the reason, or a signed 503 `{"refusal": "try_again"}` when Cloudflare or Frappe Cloud can't be asked. Then it inserts a Books Signup in status Queued. `email_key` is the email trimmed and lowercased; `googlemail.com` becomes `gmail.com`; for `gmail.com` the local part loses every dot and anything from the first `+`. The Worker and the control site use this same rule (one function in each, tested against the same cases). The unique indexes on `email_key`, `clerk_user_id` and `subdomain` turn a duplicate key from a concurrent request into the answer of step 1, 3 or 5.
- **AC-10**: Right after the commit, `request_site` enqueues the claim job (`job_id="signup-claim:<name>"`, deduplicated), and a 5 minute sweep enqueues it for every Queued request and every Preparing request whose step is Owner. More than `max_claims_per_day` (default 20) claims in the last 24 hours (UTC, by `claimed_on`) leaves new requests Queued and emails `books_ops_email` once a day while it holds. A request still Queued 1 hour after `requested_on` emails `books_ops_email` once (`queue_alerted_on`), naming the cause (cap, pool builds paused, or no Ready site).
- **AC-11**: The claim job sets the request Claiming and commits, then, holding the Books Signup row lock, takes the oldest Books Hosted Site with `pool_status` Ready (`SELECT ... FOR UPDATE SKIP LOCKED`), sets it Claimed with the request's `owner_email`, `company_name` and `subdomain` (spec 0012's `_save_label`, `domain_status` blank), links it as `hosted_site`, sets the request Preparing with step Owner and `claimed_on`, and commits. With no Ready site it sets the request back to Queued and asks for a pool build at once (AC-15).
- **AC-12**: Owner step: after the claim commit, and on each sweep while step is Owner, the control site calls the Books site's `claim_site` through `call_site` with `owner_email`, `first_name`, `last_name`, `company_name` and `time_zone`. A verified `claimed` answer sets step to Domain. A failure counts one `attempts`; the sixth failure (about 30 minutes) fails the request (AC-17). The 5 minute domain job runs spec 0012's five steps for a Claimed site only once its request's step is Domain (a new eligibility rule in `_domain_eligible`); sites with a blank `pool_status` are unchanged.
- **AC-13**: The Primary step's transaction (spec 0012 AC-8), when the site is Claimed, also sets its request Ready with `ready_on` and `notify_status` Ready with `notify_started_on`. On every change to Ready or Failed the control site POSTs the signed notice (AC-6) to `marketing_notify_url`; until a verified 200 sets `notified_status` to that status, the 5 minute sweep sends it again, for at most 24 hours after `notify_started_on`, then emails `books_ops_email` once (`notify_alerted_on`).
- **AC-14**: `owner_link` takes `request_id` and `clerk_user_id` and answers only when both match a Ready request. It calls the Books site's `owner_link` and returns its `url` in the signed answer; the URL is never logged or stored. Every other case answers a signed 404 with no detail; a site that can't be reached answers a signed 503.
- **AC-15**: Pool builds: the hourly job, and AC-11 when it found no Ready site, start builds while holding the Books Onboarding Settings row lock, until Ready plus Building sites equal `pool_size` (default 2) plus the number of Queued requests, at most 3 builds a run, and none while `pool_builds_paused` is set. A build first inserts and commits a Books Hosted Site: `site` `rb-<8 random hex>.<frappe_cloud_domain>`, `site_url` `https://` plus that name, `status` Active, `config_status` Pending, a fresh `control_secret` (`secrets.token_hex(32)`), `pool_status` Building, `pool_built_on`, blank `owner_email` and `subdomain`. Then it calls `frappe_cloud.new_site` with that name on `books_bench_group`, `frappe_cloud_server` and `frappe_cloud_plan`, apps `frappe` and `frappe_books`. A refused call deletes the row (no site exists). A sent call with an unknown outcome keeps the row, and the poll finds the site or AC-16's hour ends it. The 5 minute job polls `get_site` for Building rows; once Active it sends the config with `send_config` (spec 0010 AC-10's checks on the group and name) and sets `config_sent_on`, and the first verified `control_ping` sets `config_status` Active and `pool_status` Ready.
- **AC-16**: A Building site not Ready 1 hour after `pool_built_on` is discarded (AC-19) and counts one `build_failures` on Books Onboarding Settings; a site that reaches Ready sets it to 0. A refused `new_site` also counts one. At 2, `pool_builds_paused` is set with the reason and one ops email; a Billing Manager clears it by hand, which also sets the count to 0. A Ready pool site whose `control_ping` fails for 1 hour, or one older than 30 days by `pool_built_on`, is discarded and replaced by the next top up.
- **AC-17**: A request fails when its owner step fails 6 times, its site's `domain_status` becomes Failed, or it is not Ready 2 hours after `claimed_on`. Then: status Failed with `failed_reason`, one ops email (`alerted_on`; it replaces spec 0012's `_fail_domain` email for a Claimed site, so you get one email, not two), the Failed notice (AC-13), and the claimed site is discarded (AC-19). A Failed request still holds its email and subdomain, so the visitor can't start over; only you can retry it (AC-18).
- **AC-18**: Retry on a Failed Books Signup (Billing Manager, desk button) is refused until its old site's Discard case is Removed and `domain_cleaned_on` is set (or the site never had a subdomain). Then it clears `hosted_site`, `attempts`, `step`, `failed_reason`, `alerted_on` and the notice fields, sets it Queued and enqueues the claim, keeping the same subdomain.
- **AC-19**: Discard: the control site creates a Books Removal Case with `kind` Discard, `status` Dropping, `mode` from Books Onboarding Settings `discard_mode` (`dry_run` or `live`, default `dry_run`; it does not read removal `mode`), `owner_email` the site's owner or `books_ops_email` when blank, `site_url` the site's, and `removal_on` today. A Discard case skips the export checks of `drop_refusal` and `fresh_report_refusal`, and does not count toward `max_drops_per_day`. It keeps every other guard of spec 0010 AC-6, except that a Frappe Cloud status of Active, Broken, Pending or Installing passes. It adds one: a verified `claim_report` showing `owner_logged_in` false, read before the archive mark and again inside `archive_now` right before the call. A site that doesn't answer, or answers unverified, waits for the next hourly run and counts toward the case's `attempts` (the third failure makes the case Failed with an ops email); a Building site with no config yet skips this check. A site whose owner has logged in is never discarded: the case goes Failed with an ops email. The archive, the mark, the poll, the spec 0013 proof and the domain cleanup are those of a removal drop. No warning, export or owner email is sent. In `dry_run` a discard only logs "would discard {site}". After `domain_cleaned_on` is set (or at once when the site never had a subdomain), `registry.py` clears the row's `subdomain`, so the label can be used again. Only the Books Signup that held it can take it until that request is Removed (AC-21).
- **AC-20**: The hourly removal round, pushes and `get_state` skip a Books Hosted Site whose `pool_status` is Building or Ready, as they skip a config that isn't Active (spec 0010 AC-1 and AC-11). The hourly removal round still runs Discard cases. A Claimed site is a normal hosted site from its claim on.
- **AC-21**: Spec 0012 AC-2 gains one more clash: a label is taken when any Books Signup holds it as `subdomain`, other than the request asking. Spec 0012 AC-11 and AC-12 change too: a label is kept for ever, except on a site discarded under AC-19, where `registry.py` clears it after cleanup. `check_subdomain` on the control site applies AC-1 and this rule without writing anything.

*Books (`rarebooks-web`)*
- **AC-22**: `frappe_books.subscription.claim_site` (guest POST, signed with the site's control secret, rate limited 60 a minute, in `ALLOWED_METHODS`) creates the owner as an enabled System User with `owner_email`, `first_name` and `last_name`, roles Books Manager and System Manager, no welcome email. It sets System Settings `time_zone` to `time_zone`, and stores `company_name` as the GetStarted prefill. In the same transaction, after the time zone is set, it sets `trial_started_on` to now through `state.py` (a new `restart_trial_at_claim` writer), so day 1 is the claim date in the owner's zone. GetStarted keeps that time zone as its default. It refuses with a signed 409 when any enabled System User other than Administrator and that same email exists. Called again with the same email it answers `claimed` and changes nothing.
- **AC-23**: `frappe_books.subscription.owner_link` (same signing and limits, in `ALLOWED_METHODS`) answers 409 until the site's `host_name` is its subdomain address. While the owner's `last_password_reset_date` is empty and `last_login` is empty, it calls `User.reset_password(send_email=False)` and returns that link with `password_set` false. Each call makes a new key, so an older link stops working. Otherwise it returns `{host}/login` with `password_set` true. It never logs the link. `claim_report` returns `owner_email` and `owner_logged_in` (true when the owner's `last_login` is set).
- **AC-24**: The owner's first sign in lands in the existing GetStarted wizard with the company name prefilled; country, currency and chart of accounts are chosen there as today. The trial reads day 1 on the claim date in the zone set at claim, whatever the pool site's install date.

## Decision

**Chosen option**: Option 2: a warm pool of prebuilt Books sites on Frappe Cloud, claimed through signed calls from the marketing site.

A sign up claims a site that is already built and configured; only the owner, the trial clock and the address are set at sign up.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`) · `turnstile-spin` (`cloudflare/skills`, for the Siteverify check) · `workers-best-practices` (`cloudflare/skills`, for the Worker endpoints and the KV counters)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

Three parts: the marketing Worker (`rarebooks-site`, Astro on Cloudflare Workers with Clerk, D1 and Resend), the control site (`rarebooks_control`, new module `onboarding.py`), and each Books site (`frappe_books/subscription/onboarding.py`, exposed in `__init__.py`).

**Data model sketch**:

*Books Signup* (new, control site, autoname `SU-.#####`, track changes, Billing Manager reads and writes, System Manager reads)
| Field | Type | Required | Notes |
|---|---|---|---|
| `email` | Data (Email) | yes | as Clerk gave it |
| `email_key` | Data | yes | unique index; normalized as AC-9 |
| `clerk_user_id` | Data | yes | unique index |
| `first_name`, `last_name` | Data | first yes | from Clerk |
| `company_name` | Data (140) | yes | |
| `subdomain` | Data | yes | unique index; spec 0012 rules |
| `time_zone` | Data | yes | IANA zone from the browser, UTC fallback |
| `status` | Select | yes | Queued, Claiming, Preparing, Ready, Failed |
| `step` | Select | no | Owner, Domain |
| `attempts` | Int | yes | default 0, owner step tries |
| `hosted_site` | Link Books Hosted Site | no | unique while set; 1:1 |
| `failed_reason` | Small Text | no | no secrets |
| `requested_on`, `claimed_on`, `ready_on`, `alerted_on`, `queue_alerted_on` | Datetime (UTC) | requested yes | |
| `notify_status` | Data | no | the status to tell the Worker (Ready or Failed) |
| `notified_status` | Data | no | the last status the Worker answered with a verified 200 |
| `notify_started_on`, `notify_alerted_on` | Datetime | no | for the 24 hour notice limit and its one email |

*Books Hosted Site* (existing) gains `pool_status` (Select: blank, Building, Ready, Claimed; indexed) and `pool_built_on` (Datetime). `owner_email` may be blank only while `pool_status` is Building or Ready (controller `validate`).

*Books Removal Case* (existing) `kind` gains `Discard`.

*Books Onboarding Settings* (new single, track changes, Billing Manager writes, System Manager reads): `paused` (Check), `pool_size` (Int, 2), `max_claims_per_day` (Int, 20), `pool_builds_paused` (Check), `pool_pause_reason` (Small Text), `build_failures` (Int, 0), `discard_mode` (Select: dry_run, live; default dry_run), `frappe_cloud_server` (Data), `frappe_cloud_plan` (Data), `frappe_cloud_domain` (Data, the domain new site names get, confirmed in build task 1), `marketing_secret` (Password, never shown), `marketing_notify_url` (Data, https only).

*D1 `signups`* (marketing site): `clerk_user_id` TEXT PRIMARY KEY, `email` TEXT NOT NULL, `request_id` TEXT NOT NULL, `created_at`, `ready_emailed_at`, `failed_emailed_at` (TEXT, nullable). D1 `trials` is dropped (AC-7).

Relationships: Books Signup N:0..1 then 1:1 Books Hosted Site (one active claim each); D1 `signups` 1:1 Books Signup by `request_id`; Books Hosted Site 1:N Books Removal Case (unchanged).

**State transitions**:
- Books Signup: Queued → Claiming (committed by the claim job before it looks for a site) → Preparing (site claimed; step Owner, then Domain) → Ready (in the Primary step's transaction). Claiming with no Ready site → Queued. Preparing → Failed (AC-17). Failed → Queued only by Retry (AC-18).
- Books Hosted Site `pool_status`: (row committed) Building → Ready (first verified ping) → Claimed (claim job). Building, or Ready when stale or not answering, → discarded through a Discard case (AC-16, AC-19); a refused `new_site` deletes the row. Claimed → discarded only when its request Failed.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| Worker `/api/onboarding/check-subdomain` | POST | `subdomain`: str | `available`: bool, `reason`: str | Clerk session | 401 signed out, 429 |
| Worker `/api/onboarding/signup` | POST | `subdomain`, `company_name`, `turnstile_token` | `request_id`, `status` | Clerk session, verified email | 403 Turnstile, 409 already used, 422 subdomain, 429, 503 paused |
| Worker `/api/onboarding/status` | GET | none | `status`, `step`, `address` | Clerk session | 404 no request |
| Worker `/dashboard/site/open` | GET | none | 302 | Clerk session | 302 to `/dashboard` before Ready |
| Worker `/api/onboarding/notify` | POST | `request_id`, `status`, `email`, `first_name`, `issued_at` | `{ok}` signed | marketing secret HMAC | 401 bad signature, 503 Resend failed |
| Control `rarebooks_control.onboarding.check_subdomain` | POST | `subdomain` | `available`, `reason` | marketing HMAC, guest | 401, 429, 503 can't ask Cloudflare |
| Control `...onboarding.request_site` | POST | `clerk_user_id`, `email`, `first_name`, `last_name`, `company_name`, `subdomain`, `time_zone` | `request_id`, `status` | marketing HMAC | 409 `already_used`, 422, 503 `paused` or `try_again` |
| Control `...onboarding.signup_status` | POST | `clerk_user_id`, `request_id` (optional) | `request_id`, `status`, `step`, `address` (Ready only) | marketing HMAC | 404 |
| Control `...onboarding.owner_link` | POST | `request_id`, `clerk_user_id` | `url` | marketing HMAC | 404 not Ready or no match, 503 site unreachable |
| Control desk `retry_signup` | POST | `signup` | `status` | Billing Manager | refused while cleanup pending |
| Books `frappe_books.subscription.claim_site` | POST | `owner_email`, `first_name`, `last_name`, `company_name`, `time_zone` | `claimed` | site secret HMAC, guest | 401, 409 another owner |
| Books `frappe_books.subscription.owner_link` | POST | none | `url`, `password_set` | site secret HMAC | 401, 409 not claimed or address not primary yet |
| Books `frappe_books.subscription.claim_report` | POST | none | `owner_email`, `owner_logged_in` | site secret HMAC | 401 |
| Frappe Cloud `press.api.site.new` (via `frappe_cloud.new_site`) | POST | name, group, server, plan, apps | site name | team key | refused, unknown outcome |

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| signup | owner email, first and last name | Clerk Backend `getUser(auth().userId)`, primary email with verification status `verified`; blank first name falls back to the email's local part |
| signup | time zone | the browser's `Intl` zone, sent by the form; UTC when missing or unknown |
| signup | client IP for the limit | `CF-Connecting-IP` header, KV key `signup:<ip>:<UTC hour>` |
| signup | Turnstile result | Siteverify answer for `turnstile_token` with `TURNSTILE_SECRET_KEY` |
| request_site | `email_key` | derived from `email` (AC-9 rule, the same function in the Worker and the control site) |
| check_subdomain, request_site | available or reason | spec 0012 `check_subdomain` plus Books Signup `subdomain` (AC-21) |
| status page | address | `https://<subdomain>.<books_site_domain>` from the request and site config |
| status page | step label | `status` and `step` of Books Signup |
| claim job | which site | oldest `pool_built_on` with `pool_status` Ready |
| claim job | daily cap count | Books Signup `claimed_on` within the last 24 hours (UTC) |
| pool build | site name, `site_url`, secret | `rb-` + `secrets.token_hex(4)` + `.` + `frappe_cloud_domain`; `https://` + name; `secrets.token_hex(32)` |
| pool build | how many to build | `pool_size` + count of Queued requests − (Ready + Building), counted under the settings row lock |
| pool build | server, plan, group | Books Onboarding Settings, Books Removal Settings `books_bench_group` |
| claim_site | trial day 1 | `utc_now()` at the claim, read in the System Settings zone that `claim_site` set from `time_zone` just before |
| claim_site | company prefill | `company_name` input, stored as the global default `books_signup_company`, read by GetStarted |
| owner_link | password set link | Frappe `User.reset_password(send_email=False)` on the Books site, minted on each click; host from the site's `host_name` |
| owner_link | password set or not | the owner's `last_password_reset_date` and `last_login` on the Books site |
| ready email | link target | `https://<marketing host>/dashboard/site/open` (`PUBLIC_SITE_URL`) |
| notify | where to send | Books Onboarding Settings `marketing_notify_url` |

**Key invariants**:
- One Books Signup per `email_key`, per `clerk_user_id` and per subdomain, ever (database unique indexes); a removed site's request is kept.
- A Books Hosted Site is claimed by at most one Books Signup; claiming happens only under the row lock with `SKIP LOCKED`.
- A pool site (Building or Ready) never gets a push, a removal case of kind Trial or Lapsed, or a `get_state` answer.
- No site with an owner who has ever logged in is discarded; the check is made twice, the second time inside `archive_now`, and a missing answer never counts as "not logged in".
- The password set link never travels by email and never reaches D1, a database row or a log (only the signed answer and the 302 `Location` carry it).
- Trial day 1 is the claim day.
- Every network call to a Books site or the Worker is made with no row lock held (spec 0007 lock hardening). The one exception is the Frappe Cloud archive inside `archive_now`, which follows spec 0010 AC-6's existing commit then archive order.
- A Building row is committed before `new_site` is called, so no Frappe Cloud site exists without a row.

**Security model**:
- The marketing Worker is the only holder of `marketing_secret` besides the control site; it can only check a name, ask for a site for a Clerk verified user, read that user's status and get that user's link. It can't reach the registry, billing or removal.
- Every read on the control site is keyed by both `request_id` and `clerk_user_id`, so knowing one request id is not enough.
- The Books owner gets Books Manager and System Manager on their own site only; `claim_site` refuses once a real owner exists, so a replay can't add a second owner.
- PII held: email, names and company name, on the control site (Books Signup) and in D1 (email). Kept while the site exists; Books Signup rows follow the hosted site's removal and are kept for the one per email rule.

**Configuration required**:
- Marketing Worker: `CONTROL_SITE_URL` (var), an `ONBOARDING_KV` KV namespace (the IP and check counters and the 30 second check cache), `CONTROL_SIGNING_SECRET` (wrangler secret, equals `marketing_secret`), `TURNSTILE_SECRET_KEY` (secret), `PUBLIC_TURNSTILE_SITE_KEY` (var), `PUBLIC_SITE_URL` (var), the existing Resend key and Clerk keys. Remove `KEYMINT_API_KEY`.
- Clerk: email verification required at sign up.
- Control site: Books Onboarding Settings fields above; existing Frappe Cloud and Cloudflare keys.
- Frappe Cloud: a team key allowed to create sites on the Books bench group (the current key may be scoped narrower; check in build task 1).

**Critical test scenarios**:
- Happy path: a Clerk verified visitor submits `acme`, a Ready pool site is claimed, `claim_site` makes the owner and resets the trial, the domain steps finish, the Ready email is sent once, `/dashboard/site/open` lands on the password set page, GetStarted shows "Acme", verifies **AC-1**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-11** to **AC-13**, **AC-22** to **AC-24**
- Empty pool: the request stays Queued, a build starts at once, and the request is claimed when the build is Ready, verifies **AC-11**, **AC-15**
- Concurrent claims: two claim jobs and one Ready site; one wins, the other stays Queued, verifies **AC-11**
- Same person twice: a second sign up by email with dots or a `+` suffix on Gmail answers 409 `already_used`, verifies **AC-9**
- Stuck domain: the domain step fails, the request goes Failed, one alert, the site is discarded with its label released after cleanup, Retry claims a fresh site with the same subdomain, verifies **AC-17** to **AC-19**
- Guard: a discard of a site whose owner has logged in is refused and alerts; a site that doesn't answer `claim_report` is not archived; an owner who logs in between the two checks stops the archive, verifies **AC-19**
- Orphan guard: `new_site` times out after sending; the committed Building row is found Active by the poll and goes Ready, verifies **AC-15**
- Pool skip: a Ready pool site 40 days after install gets no removal case and no push, and is claimed with trial day 1, verifies **AC-20**, **AC-24**
- Auth: a forged marketing signature gets a signed 401; `owner_link` with a right `request_id` but another `clerk_user_id` gets 404; a signed out visitor on `/dashboard/start` goes to sign in; a replayed `claim_site` with a different email gets 409, verifies **AC-8**, **AC-14**, **AC-1**, **AC-22**
- Abuse: a fourth sign up attempt from one IP within an hour gets 429 before any control site call; the 21st claim in 24 hours stays Queued and sends one alert, verifies **AC-3**, **AC-10**

## Build plan

Tracer Bullet: the first slice is one real sign up claiming one hand made pool site end to end; then the pool builds itself; then failure handling; then the desktop retirement.

1. Confirm `press.api.site.new` live with your key: the payload (name, group, server, plan, apps), the answer, the Frappe Cloud domain new names get, and that the key may create sites; record it in `providers/frappe_cloud.py`'s docstring as spec 0012 did for domains, satisfies **AC-15**
2. The schema: Books Signup, Books Onboarding Settings, `pool_status` and `pool_built_on` on Books Hosted Site with the blank owner rule, `kind` Discard on Books Removal Case, and a patch setting `pool_status` blank on existing rows, satisfies **AC-9**, **AC-15**, **AC-19**
3. Books side: `claim_site`, `owner_link`, `claim_report`, `restart_trial_at_claim` in `state.py`, `ALLOWED_METHODS`, the GetStarted prefill, and their tests, satisfies **AC-22**, **AC-23**, **AC-24**
4. The thread against stubs: `onboarding.py` with the marketing signing (reusing `signing.py`), `check_subdomain`, `request_site`, the claim job, the owner step, Ready on domain Active, `signup_status`, `owner_link`, the notice; and AC-21's clash rule in `registry.check_subdomain`. the domain eligibility rule for Claimed sites, Ready set in the Primary step's transaction, and no `_fail_domain` email for a Claimed site. Mark one hand registered site as pool Ready to drive it, satisfies **AC-8** to **AC-14**, **AC-21**
5. The marketing thread: TS HMAC signing tested against a copy of `signing_vectors.json`, the shared `email_key` function and its test cases, the `ONBOARDING_KV` namespace with the IP and check counters and the check cache, the D1 `signups` migration, `/dashboard/start` with the live check, Turnstile and the IP limit, `/api/onboarding/signup`, status polling on `/dashboard`, `/dashboard/site/open`, `/api/onboarding/notify` and the two Resend emails, satisfies **AC-1** to **AC-6**
6. Pool skip rules in the removal round, pushes and `get_state`, satisfies **AC-20**
7. Pool builds: `frappe_cloud.new_site`, the hourly top up and the build on demand, the Building poll into the existing config send and ping, satisfies **AC-15**, **AC-11**
8. Failures: the daily cap and its alert, the paused refusal, the owner step tries, the 2 hour rule, Failed handling and the notice retry limit, the Queued age alert, the Discard case (`discard_mode`, the skipped export and report checks, the wider Frappe Cloud statuses, the two `claim_report` checks, no daily cap) with label release, the build failure counter and pause, stale and silent pool sites, the Retry button, satisfies **AC-10**, **AC-13**, **AC-16** to **AC-19**
9. Retire the desktop trial: export D1 `trials`, remove the license routes, pages, components and templates, repoint every trial link, drop `trials`, remove `KEYMINT_API_KEY`, satisfies **AC-7**
10. Rollout: Books Onboarding Settings on the control site, the Worker secrets and binding, Clerk email verification, pool size 1 on staging with removal mode `dry_run`, one sign up end to end on staging, one forced failure to see the alert and the "would discard" line, then live with pool size 2, satisfies **AC-1** to **AC-24**

## Consequences

**Positive**:
- A visitor is in their own site in minutes, at any hour, with no step from you.
- The slow and failure prone part (building a site) happens before anyone waits on it, and a failed build costs no customer anything.
- The marketing site and control site reuse the signing scheme, vectors and alert habits you already run.

**Negative / tradeoffs**:
- Two idle sites always use server resources and count toward any Frappe Cloud plan cost.
- A third repo now signs with the shared scheme, so `signing_vectors.json` has a third copy to keep identical.
- More scheduled work on the control site (pool poll, claim sweep, notice retries) and more states to read on the desk.
- Pool sites run a Books version from their build time; a release must reach them like any other site on the bench group, or they are discarded and rebuilt.
- Retiring the desktop trial ends a working acquisition path the day this ships; there is no fallback if hosted sign up is down.

**Neutral**:
- `register_site` stays for manual sites (demo sites, special customers).
- The one per email rule keeps Books Signup rows after a site is removed.

## Follow-up

- [ ] `signing_vectors.json` rule in both AGENTS.md files should name the third copy in `rarebooks-site` (for `/sync`).
- [ ] `rarebooks-site` has no AGENTS.md; running `/audit` there would give `/develop` its rules (Astro, Clerk, D1, Resend).
- [ ] `turnstile-spin` and `workers-best-practices` are available but not yet in any AGENTS.md; they belong in the `rarebooks-site` context file once it exists.
- [ ] Privacy policy on the marketing site should name Clerk, Cloudflare Turnstile and Resend for sign up data.
- [ ] Decide later whether Books Signup rows should be anonymized some time after removal (kept now for the one per email rule).
