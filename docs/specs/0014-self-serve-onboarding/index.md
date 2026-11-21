# 0014. Self serve onboarding through a warm pool of Books sites

**Date**: 2026-11-21
**Status**: Proposed

Amends: spec [0010](../0010-frappe-cloud-hosting/index.md) (AC-1 and AC-13: the removal round and pushes skip pool sites, and the Frappe Cloud client gains `new_site`), spec [0012](../0012-custom-domains-registration/index.md) (AC-2: a label held by a Books Signup is taken; a discarded site releases its label after cleanup) and spec [0013](../0013-archived-site-proof/index.md) (a Discard case uses the same archive proof). Every other rule in those specs still holds.

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
- **AC-1**: Only a visitor signed in with Clerk, whose primary email is verified, can reach `/dashboard/start`. The form asks for a subdomain and a company name (1 to 140 characters, trimmed). The owner's email, first name and last name come from the Clerk user on the server, never from the form.
- **AC-2**: While the visitor types a subdomain, the form asks `POST /api/onboarding/check-subdomain` (debounced 400 ms) and shows "available" or the reason it is refused (spec 0012 AC-1's rule, or "taken"). The Worker forwards the check to the control site's `check_subdomain`. At most 30 checks a minute per Clerk user; over that the field shows "slow down" and the form still submits.
- **AC-3**: `POST /api/onboarding/signup` verifies the Cloudflare Turnstile token with Siteverify first, then allows at most 3 attempts an hour per client IP (Workers rate limiting binding), then calls the control site's `request_site`. A failed Turnstile answers 403 and a rate limit answers 429, both before any control site call. On success it writes a D1 `signups` row (`clerk_user_id` primary key, `email`, `request_id`, `created_at`) and the browser goes to `/dashboard`. A second submit by the same Clerk user returns the existing request (no new row, no new call result).
- **AC-4**: `/dashboard` shows the signed in user's request status, read through `GET /api/onboarding/status`, which looks up the request by the Clerk user id in D1 and asks the control site's `signup_status`; it is polled every 5 seconds while the status is Queued, Claiming or Preparing, and stops on Ready or Failed. Steps shown: "Getting your site", "Setting up your address", "Ready". Ready shows the address and a "Set your password" button. Failed shows "We hit a problem setting up your site. We're on it and will email you." with the support email. A user with no request sees the start form.
- **AC-5**: `GET /dashboard/site/open` (Clerk signed in) asks the control site's `owner_link` for the user's request and redirects (302) to the URL it returns: a fresh password set link while the owner has not set a password yet, else the site's `/login`. Before Ready it redirects to `/dashboard`.
- **AC-6**: `POST /api/onboarding/notify` accepts only a request signed by the control site with the marketing secret (spec 0005 signing, `issued_at` within 5 minutes) and answers signed. On `Ready` it sends the "Your RareBooks site is ready" email through Resend to the request's email, once per request (D1 `signups.ready_emailed_at`), with a button to `/dashboard/site/open`, never the password link itself. On `Failed` it sends the "We're on it" email, once. A repeated notice answers 200 and sends nothing.
- **AC-7**: The desktop license key trial is gone: `/api/license`, `/api/create-license`, `/api/deactivate-key`, `/api/license-info`, `/api/redemption`, `/redemption`, `/trial/download`, the trial modal and form, the dashboard license, device and renewal parts and their email templates are removed, `KEYMINT_API_KEY` is unused, and every "Start free trial" link goes to Clerk sign up, then `/dashboard/start`. The D1 `trials` table is exported to a file you keep, then dropped by a migration. No existing key holder is migrated or emailed.

*Control site (`rarebooks_control`)*
- **AC-8**: Every marketing call (`check_subdomain`, `request_site`, `signup_status`, `owner_link`) is a guest POST to `rarebooks_control.onboarding.<name>`, signed with Books Onboarding Settings `marketing_secret` exactly as spec 0005 and spec 0008 AC-5 sign site calls (HMAC SHA256 of the raw body in `X-Books-Signature`, `issued_at` within 5 minutes, every answer including a 401 signed through `signed_response`). Each is rate limited to 120 calls a minute in total. A bad signature answers a signed 401 and counts toward spec 0008 AC-22's signature failure alert.
- **AC-9**: `request_site` takes `clerk_user_id`, `email`, `first_name`, `last_name`, `company_name` and `subdomain`. It runs spec 0012 AC-1 and AC-2 (as amended by AC-21) on the subdomain and refuses, with a signed 422 and a reason, before writing anything. It refuses with a signed 409 `{"refusal": "already_used"}` when any Books Signup, in any status, holds the same `email_key` (lowercased; for `gmail.com` and `googlemail.com` dots and any `+` suffix removed, as `normalizeEmail` does today); a request by the same `clerk_user_id` returns that user's existing request instead, in any status (idempotent). Otherwise it inserts a Books Signup in status Queued; the unique indexes on `email_key`, `clerk_user_id` and `subdomain` make a duplicate key from a concurrent request the same answer. While Books Onboarding Settings `paused` is set it refuses with a signed 503 `{"refusal": "paused"}`.
- **AC-10**: Right after the commit, `request_site` enqueues the claim job (`job_id="signup-claim:<name>"`, deduplicated), and a 5 minute sweep enqueues it for every Queued request. More than `max_claims_per_day` (default 20) claims in the last 24 hours leaves new requests Queued (they show as "Getting your site") and emails `books_ops_email` once a day while it holds.
- **AC-11**: The claim job, holding the Books Signup row lock, takes the oldest Books Hosted Site with `pool_status` Ready (`SELECT ... FOR UPDATE SKIP LOCKED`), sets it Claimed with the request's `owner_email`, `company_name` and `subdomain` (spec 0012's `_save_label`, `domain_status` blank), links it as `hosted_site`, sets the request Preparing with `claimed_on`, and commits. With no Ready site it stays Queued and starts one pool build at once (AC-15) if fewer than `pool_size` are Ready or Building.
- **AC-12**: Owner step: after the claim commit, the control site calls the Books site's `claim_site` through `call_site` with `owner_email`, `first_name`, `last_name` and `company_name`. A verified `claimed` answer sets the request `step` to Domain. A failure counts one `attempts`; the 5 minute sweep tries again; the third failure fails the request (AC-17). The existing 5 minute domain job then runs spec 0012's five steps for the claimed site, since it now has a `subdomain` and an Active config.
- **AC-13**: When the claimed site's `domain_status` becomes Active, the request becomes Ready with `ready_on`, and the control site POSTs a signed notice `{request_id, status}` to `marketing_notify_url`. A notice that isn't answered with a verified 200 is sent again by the 5 minute sweep until it is (`notified_status` holds the last status answered), for at most 24 hours, then one ops email.
- **AC-14**: `owner_link` takes `request_id` and `clerk_user_id` and answers only when both match a Ready request. It calls the Books site's `owner_link` and returns its `url`. Every other case answers a signed 404 with no detail.
- **AC-15**: Pool builds: an hourly job, and AC-11 when the pool is short, start builds until Ready plus Building sites equal `pool_size` (default 2), at most 3 builds a run. A build calls `frappe_cloud.new_site` with a name `rb-<8 random hex>` on `books_bench_group`, `frappe_cloud_server` and `frappe_cloud_plan` with apps `frappe` and `frappe_books`, and inserts a Books Hosted Site with `pool_status` Building, `pool_built_on`, blank `owner_email` and blank `subdomain`. The 5 minute job polls `get_site`; once Active it sends the config exactly as `register_site` does (spec 0010 AC-10, same checks), and the first verified `control_ping` sets `config_status` Active and `pool_status` Ready.
- **AC-16**: A Building site not Ready 1 hour after `pool_built_on`, or one whose `new_site` call is refused, is discarded (AC-19) and alerts once a day while builds fail. Two failed builds in a row set Books Onboarding Settings `pool_builds_paused` with the reason; no build starts until a Billing Manager clears it.
- **AC-17**: A request fails when its owner step fails 3 times, its site's `domain_status` becomes Failed, or it is not Ready 2 hours after `claimed_on`. Then: status Failed with `failed_reason`, one ops email (`alerted_on`), the Failed notice to the marketing site (AC-13's retry rule), and the claimed site is discarded (AC-19). A Failed request still holds its email and subdomain, so the visitor can't start over; only you can retry it (AC-18).
- **AC-18**: Retry on a Failed Books Signup (Billing Manager, desk button) waits until its old site's domain cleanup is done, then clears `hosted_site`, `attempts`, `step` and `failed_reason`, sets it Queued and enqueues the claim, keeping the same subdomain.
- **AC-19**: Discard: the control site opens a Books Removal Case of `kind` Discard for the site, straight in Dropping, and runs spec 0010 AC-6's Frappe Cloud guards (exists, on `books_bench_group`, Active, a Books Hosted Site, not the control site) plus one more: a signed `claim_report` from the site (when it answers) shows no owner who has ever logged in. A site with an owner who has logged in is never discarded; the case goes Failed with an ops email. The archive, the mark, the poll, the spec 0013 proof and the domain cleanup are exactly those of a removal drop; no warning, export or owner email is sent. In removal `mode` other than `live` a discard only logs "would discard {site}". After `domain_cleaned_on` is set (or at once when the site never had a subdomain), the row's `subdomain` is cleared so the label can be used again.
- **AC-20**: The hourly removal round, pushes and `get_state` skip a Books Hosted Site whose `pool_status` is Building or Ready, as they skip a config that isn't Active (spec 0010 AC-1 and AC-11). A Claimed site is a normal hosted site from its claim on.
- **AC-21**: Spec 0012 AC-2 gains one more clash: a label is taken when any Books Signup holds it as `subdomain`, other than the request asking. `check_subdomain` on the control site applies AC-1 and this rule without writing anything.

*Books (`rarebooks-web`)*
- **AC-22**: `frappe_books.subscription.claim_site` (guest POST, signed with the site's control secret, rate limited 60 a minute, in `ALLOWED_METHODS`) creates the owner as an enabled System User with `owner_email`, `first_name` and `last_name`, roles Books Manager and System Manager, no welcome email, and stores `company_name` as the GetStarted prefill. In the same transaction it sets `trial_started_on` to now through `state.py` (a new `restart_trial_at_claim` writer). It refuses with a signed 409 when any enabled System User other than Administrator and that same email exists. Called again with the same email it answers `claimed` and changes nothing.
- **AC-23**: `frappe_books.subscription.owner_link` (same signing and limits, in `ALLOWED_METHODS`) returns a fresh Frappe password set link for the claimed owner while that user has never logged in and has no password, else `{site_url}/login`. `claim_report` returns `owner_email` and `owner_logged_in`.
- **AC-24**: The owner's first sign in lands in the existing GetStarted wizard with the company name prefilled; country, currency and chart of accounts are chosen there as today. The trial reads day 1 on the claim day, whatever the pool site's install date.

## Decision

**Chosen option**: Option 2: a warm pool of prebuilt Books sites on Frappe Cloud, claimed through signed calls from the marketing site.

A sign up claims a site that is already built and configured; only the owner, the trial clock and the address are set at sign up.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`) · `turnstile-spin` (`cloudflare/skills`, for the Siteverify check) · `workers-best-practices` (`cloudflare/skills`, for the Worker endpoints and the rate limiting binding)

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
| `status` | Select | yes | Queued, Claiming, Preparing, Ready, Failed |
| `step` | Select | no | Owner, Domain |
| `attempts` | Int | yes | default 0, owner step tries |
| `hosted_site` | Link Books Hosted Site | no | unique while set; 1:1 |
| `failed_reason` | Small Text | no | no secrets |
| `requested_on`, `claimed_on`, `ready_on`, `alerted_on` | Datetime (UTC) | requested yes | |
| `notified_status` | Data | no | last status the Worker answered |
| `notify_started_on` | Datetime | no | for the 24 hour notice limit |

*Books Hosted Site* (existing) gains `pool_status` (Select: blank, Building, Ready, Claimed; indexed) and `pool_built_on` (Datetime). `owner_email` may be blank only while `pool_status` is Building or Ready (controller `validate`).

*Books Removal Case* (existing) `kind` gains `Discard`.

*Books Onboarding Settings* (new single, track changes, Billing Manager writes, System Manager reads): `paused` (Check), `pool_size` (Int, 2), `max_claims_per_day` (Int, 20), `pool_builds_paused` (Check) and `pool_pause_reason` (Small Text), `frappe_cloud_server` (Data), `frappe_cloud_plan` (Data), `marketing_secret` (Password, never shown), `marketing_notify_url` (Data, https only).

*D1 `signups`* (marketing site): `clerk_user_id` TEXT PRIMARY KEY, `email` TEXT NOT NULL, `request_id` TEXT NOT NULL, `created_at`, `ready_emailed_at`, `failed_emailed_at` (TEXT, nullable). D1 `trials` is dropped (AC-7).

Relationships: Books Signup N:0..1 then 1:1 Books Hosted Site (one active claim each); D1 `signups` 1:1 Books Signup by `request_id`; Books Hosted Site 1:N Books Removal Case (unchanged).

**State transitions**:
- Books Signup: Queued → Claiming (job took the row lock) → Preparing (site claimed, step Owner then Domain) → Ready. Claiming or Preparing → Failed (AC-17). Failed → Queued only by Retry (AC-18). Claiming with no Ready site → back to Queued.
- Books Hosted Site `pool_status`: Building → Ready (first verified ping) → Claimed (claim job). Building or Ready → discarded through a Discard case (AC-16, AC-19); Claimed → discarded only when its request Failed.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| Worker `/api/onboarding/check-subdomain` | POST | `subdomain`: str | `available`: bool, `reason`: str | Clerk session | 401 signed out, 429 |
| Worker `/api/onboarding/signup` | POST | `subdomain`, `company_name`, `turnstile_token` | `request_id`, `status` | Clerk session, verified email | 403 Turnstile, 409 already used, 422 subdomain, 429, 503 paused |
| Worker `/api/onboarding/status` | GET | none | `status`, `step`, `address` | Clerk session | 404 no request |
| Worker `/dashboard/site/open` | GET | none | 302 | Clerk session | 302 to `/dashboard` before Ready |
| Worker `/api/onboarding/notify` | POST | `request_id`, `status`, `issued_at` | `{ok}` signed | marketing secret HMAC | 401 bad signature |
| Control `rarebooks_control.onboarding.check_subdomain` | POST | `subdomain` | `available`, `reason` | marketing HMAC, guest | 401, 429, 503 can't ask Cloudflare |
| Control `...onboarding.request_site` | POST | `clerk_user_id`, `email`, `first_name`, `last_name`, `company_name`, `subdomain` | `request_id`, `status` | marketing HMAC | 409 `already_used`, 422, 503 `paused` |
| Control `...onboarding.signup_status` | POST | `request_id`, `clerk_user_id` | `status`, `step`, `address` | marketing HMAC | 404 |
| Control `...onboarding.owner_link` | POST | `request_id`, `clerk_user_id` | `url` | marketing HMAC | 404 not Ready or no match, 503 site unreachable |
| Control desk `retry_signup` | POST | `signup` | `status` | Billing Manager | refused while cleanup pending |
| Books `frappe_books.subscription.claim_site` | POST | `owner_email`, `first_name`, `last_name`, `company_name` | `claimed` | site secret HMAC, guest | 401, 409 another owner |
| Books `frappe_books.subscription.owner_link` | POST | none | `url`, `password_set` | site secret HMAC | 401, 409 not claimed |
| Books `frappe_books.subscription.claim_report` | POST | none | `owner_email`, `owner_logged_in` | site secret HMAC | 401 |
| Frappe Cloud `press.api.site.new` (via `frappe_cloud.new_site`) | POST | name, group, server, plan, apps | site name | team key | refused, unknown outcome |

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| signup | owner email, first and last name | Clerk Backend `getUser(auth().userId)`, primary email with verification status `verified` |
| signup | client IP for the limit | `CF-Connecting-IP` header |
| signup | Turnstile result | Siteverify answer for `turnstile_token` with `TURNSTILE_SECRET_KEY` |
| request_site | `email_key` | derived from `email` (AC-9 rule) |
| check_subdomain, request_site | available or reason | spec 0012 `check_subdomain` plus Books Signup `subdomain` (AC-21) |
| status page | address | `https://<subdomain>.<books_site_domain>` from the request and site config |
| status page | step label | `status` and `step` of Books Signup |
| claim job | which site | oldest `pool_built_on` with `pool_status` Ready |
| claim job | daily cap count | Books Signup `claimed_on` within the last 24 hours (UTC) |
| pool build | site name | `rb-` plus `secrets.token_hex(4)` + `.` + the Frappe Cloud domain the build task confirms |
| pool build | server, plan, group | Books Onboarding Settings, Books Removal Settings `books_bench_group` |
| claim_site | trial day 1 | `utc_now()` at the claim, shown in the site's System Settings time zone (spec 0005) |
| claim_site | company prefill | `company_name` input, stored as the global default `books_signup_company`, read by GetStarted |
| owner_link | password set link | Frappe `User.reset_password(send_email=False)` on the Books site, minted on each click |
| ready email | link target | `https://<marketing host>/dashboard/site/open` (`PUBLIC_SITE_URL`) |
| notify | where to send | Books Onboarding Settings `marketing_notify_url` |

**Key invariants**:
- One Books Signup per `email_key`, per `clerk_user_id` and per subdomain, ever (database unique indexes); a removed site's request is kept.
- A Books Hosted Site is claimed by at most one Books Signup; claiming happens only under the row lock with `SKIP LOCKED`.
- A pool site (Building or Ready) never gets a push, a removal case of kind Trial or Lapsed, or a `get_state` answer.
- No site with an owner who has ever logged in is discarded.
- The password set link never travels by email and never reaches D1 or a log.
- Trial day 1 is the claim day.
- Every network call (Frappe Cloud, a Books site, the Worker) is made with no row lock held; locks are taken after the call returns (spec 0007 lock hardening).

**Security model**:
- The marketing Worker is the only holder of `marketing_secret` besides the control site; it can only check a name, ask for a site for a Clerk verified user, read that user's status and get that user's link. It can't reach the registry, billing or removal.
- Every read on the control site is keyed by both `request_id` and `clerk_user_id`, so knowing one request id is not enough.
- The Books owner gets Books Manager and System Manager on their own site only; `claim_site` refuses once a real owner exists, so a replay can't add a second owner.
- PII held: email, names and company name, on the control site (Books Signup) and in D1 (email). Kept while the site exists; Books Signup rows follow the hosted site's removal and are kept for the one per email rule.

**Configuration required**:
- Marketing Worker: `CONTROL_SITE_URL` (var), `CONTROL_SIGNING_SECRET` (wrangler secret, equals `marketing_secret`), `TURNSTILE_SECRET_KEY` (secret), `PUBLIC_TURNSTILE_SITE_KEY` (var), `PUBLIC_SITE_URL` (var), a `[[ratelimits]]` binding `SIGNUP_LIMITER` (3 per hour per IP; the binding's period is 10 or 60 seconds, so the build task picks the nearest supported rule or a KV counter), the existing Resend key and Clerk keys. Remove `KEYMINT_API_KEY`.
- Clerk: email verification required at sign up.
- Control site: Books Onboarding Settings fields above; existing Frappe Cloud and Cloudflare keys.
- Frappe Cloud: a team key allowed to create sites on the Books bench group (the current key may be scoped narrower; check in build task 1).

**Critical test scenarios**:
- Happy path: a Clerk verified visitor submits `acme`, a Ready pool site is claimed, `claim_site` makes the owner and resets the trial, the domain steps finish, the Ready email is sent once, `/dashboard/site/open` lands on the password set page, GetStarted shows "Acme", verifies **AC-1**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-11** to **AC-13**, **AC-22** to **AC-24**
- Empty pool: the request stays Queued, a build starts at once, and the request is claimed when the build is Ready, verifies **AC-11**, **AC-15**
- Concurrent claims: two claim jobs and one Ready site; one wins, the other stays Queued, verifies **AC-11**
- Same person twice: a second sign up by email with dots or a `+` suffix on Gmail answers 409 `already_used`, verifies **AC-9**
- Stuck domain: the domain step fails, the request goes Failed, one alert, the site is discarded with its label released after cleanup, Retry claims a fresh site with the same subdomain, verifies **AC-17** to **AC-19**
- Guard: a discard of a site whose owner has logged in is refused and alerts, verifies **AC-19**
- Pool skip: a Ready pool site 40 days after install gets no removal case and no push, and is claimed with trial day 1, verifies **AC-20**, **AC-24**
- Auth: a forged marketing signature gets a signed 401; `owner_link` with a right `request_id` but another `clerk_user_id` gets 404; a signed out visitor on `/dashboard/start` goes to sign in; a replayed `claim_site` with a different email gets 409, verifies **AC-8**, **AC-14**, **AC-1**, **AC-22**
- Abuse: a fourth sign up attempt from one IP within an hour gets 429 before any control site call; the 21st claim in 24 hours stays Queued and sends one alert, verifies **AC-3**, **AC-10**

## Build plan

Tracer Bullet: the first slice is one real sign up claiming one hand made pool site end to end; then the pool builds itself; then failure handling; then the desktop retirement.

1. Confirm `press.api.site.new` live with your key: the payload (name, group, server, plan, apps), the answer, the Frappe Cloud domain new names get, and that the key may create sites; record it in `providers/frappe_cloud.py`'s docstring as spec 0012 did for domains, satisfies **AC-15**
2. The schema: Books Signup, Books Onboarding Settings, `pool_status` and `pool_built_on` on Books Hosted Site with the blank owner rule, `kind` Discard on Books Removal Case, and a patch setting `pool_status` blank on existing rows, satisfies **AC-9**, **AC-15**, **AC-19**
3. Books side: `claim_site`, `owner_link`, `claim_report`, `restart_trial_at_claim` in `state.py`, `ALLOWED_METHODS`, the GetStarted prefill, and their tests, satisfies **AC-22**, **AC-23**, **AC-24**
4. The thread against stubs: `onboarding.py` with the marketing signing (reusing `signing.py`), `check_subdomain`, `request_site`, the claim job, the owner step, Ready on domain Active, `signup_status`, `owner_link`, the notice; and AC-21's clash rule in `registry.check_subdomain`. Mark one hand registered site as pool Ready to drive it, satisfies **AC-8** to **AC-14**, **AC-21**
5. The marketing thread: TS HMAC signing tested against a copy of `signing_vectors.json`, the D1 `signups` migration, `/dashboard/start` with the live check, Turnstile and the IP limit, `/api/onboarding/signup`, status polling on `/dashboard`, `/dashboard/site/open`, `/api/onboarding/notify` and the two Resend emails, satisfies **AC-1** to **AC-6**
6. Pool skip rules in the removal round, pushes and `get_state`, satisfies **AC-20**
7. Pool builds: `frappe_cloud.new_site`, the hourly top up and the build on demand, the Building poll into the existing config send and ping, satisfies **AC-15**, **AC-11**
8. Failures: the daily cap and its alert, the paused refusal, the owner step tries, the 2 hour rule, Failed handling and the notice retry limit, the Discard case with the login guard and label release, the build failure pause, the Retry button, satisfies **AC-10**, **AC-13**, **AC-16** to **AC-19**
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
