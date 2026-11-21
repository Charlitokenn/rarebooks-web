# 0008. Billing control site

**Date**: 2026-11-18
**Status**: In Progress

> **Amended by [spec 0010](../0010-frappe-cloud-hosting/index.md) (2026-11-20, hosting on Frappe Cloud).** Registration (AC-1, `bench books-register-site`, `register_site`) and secret rotation (AC-15, `secret_rotated`) now go through the Frappe Cloud API from the control site, `hosting_bench` and `books_runner_secrets` are gone, and the host isolation parts of AC-22 and task 19 become a separate Frappe Cloud bench group (0010 AC-14). AC-1's "a repeat returns the same secret" no longer applies. Rate limits are per site only (0010 AC-17); the per bench limits go with the bench, and the Follow-up item on rotating `books_runner_secrets` is void. The signature failure alert of AC-22, and every billing rule, still hold.

## Summary

The billing control site is a small Frappe app of yours (`rarebooks_control`, in its own repo) that keeps the list of hosted sites with a secret for each one. It takes payment through ClickPesa (one yearly payment, for Tanzania) and PayPal Subscriptions (monthly or yearly, for everyone else), and sends each change to the customer site as a signed message, the contract fixed in spec 0005. It never trusts a webhook on its own: it checks the signature, then asks the provider for the real state before it changes anything. It runs as a separate bench, under its own Linux user, on the same server as the hosting bench, and it also hosts the removal records of spec 0007.

## Requirements

**User stories**:
- As a site owner, I want Subscribe to take me to a real ClickPesa or PayPal checkout, and my site to unlock within a minute of paying, so paying feels instant.
- As a site owner who pays during the trial, I want my paid period to start when the trial ends, so I never lose free days.
- As the operator, I want each payment proven with the provider before it unlocks anything, and every odd case (wrong amount, refund, a payment for a removed site, a double subscription) flagged to me, so no one gets free access by mistake and no payer is ignored.
- As the operator, I want to register sites, fix a site's billing state, and rotate a site's secret without typing secrets by hand, so support is quick and safe.

**Acceptance criteria**:
- **AC-1**: `bench books-register-site <site> --owner-email <email> --site-url <https url>` (a bench command in frappe_books, run on the hosting bench; it stops with an error before any call when `--site-url` isn't `https://`) calls the control site's `register_site`, signed with that bench's runner secret (spec 0007 AC-15). The control site creates a Books Hosted Site row with a fresh secret of 32 random bytes (64 hex characters) and answers with it in a signed response. The command then writes `books_control_url` and `books_control_secret` into that site's `site_config.json`. Running it again for the same site from the same bench returns the same secret and changes nothing else (a different `owner_email` or `site_url` is not applied, and the command prints that). A site that is registered on another bench, or is `Removed`, gets 409 and nothing is written. A bad signature, an unknown bench or a stale `issued_at` gets 401.
- **AC-2**: `get_state` (signed with the site's secret, spec 0005) answers with the site's current state (`paid_until`, `provider`, `billing_period`, `auto_renews`, `provider_reference`, `exempt`), with `issued_at` set to the request's own `issued_at` (an echo), plus `plans`: every enabled Books Plan (`provider`, `billing_period`, `amount`, `currency`, `label`), where a plan marked `test_only` is listed only for a site with `allow_test_plans`, and there it replaces the real plan of the same provider and period. The answer is signed with the same secret that verified the request. The call also stores the site facts it carries (`trial_ends_on`, `time_zone`, `language`, `company_name`) on the row. A bad signature, a stale `issued_at`, an unknown site or a `Removed` site gets 401.
- **AC-3**: `create_checkout` for ClickPesa creates a Books Checkout (`Created`), asks ClickPesa for a checkout link at the plan's amount in TZS with the checkout's `order_reference`, and answers with `checkout_url` = `{control url}/api/method/rarebooks_control.billing.go?token=<token>`. An unpaid `Created` checkout (either provider) for the same site and plan that is less than 24 hours old is reused instead of creating another: it gets a new token (its `token_hash` is overwritten, so an older `go` link for it stops working). `create_checkout` also stores the four site facts of its body on the row, as `get_state` does.
- **AC-4**: `create_checkout` for PayPal creates a PayPal subscription on the plan's `paypal_plan_id` with `custom_id` = the site. Take the later of (`trial_ends_on` plus 1 day) and (`paid_until` plus 1 day), plain calendar arithmetic on the site's own dates, using the request body's `trial_ends_on` and leaving out an empty term; with both empty, no `start_time` is sent. `start_time` is 12:00 in `America/Los_Angeles` on that same calendar date (the same year, month and day, read on PayPal's Pacific calendar), converted to UTC (`Z` form). It is sent only when that day is later than the site's today (in the body's `time_zone`); otherwise none is sent and PayPal charges at approval, so a lapsed site renews at once. PayPal bills on the Pacific date of `start_time` at about 10:00 UTC (sandbox run, 2026-11-19), so the first charge lands on that day, on or after local midnight for every site zone from UTC−10 eastward. Sites at UTC−11 and UTC−12 (American Samoa, Niue) are charged late on the trial's last day; that is accepted. Without a `start_time` (a lapsed site, say) PayPal charges at approval. `application_context` sets the return and cancel URLs to the control site's return page. The Checkout stores the subscription id, and `checkout_url` is the same `go` link as in AC-3, which leads to PayPal's `approve` link.
- **AC-5**: `create_checkout` refuses, with a signed 409 carrying a `refusal` code and no checkout: `plan_not_offered` (no enabled plan for that provider and period, or a `test_only` plan without `allow_test_plans`); `already_subscribed` (either provider, while the site's current PayPal subscription, its `provider_reference`, is `ACTIVE` or `APPROVED` at PayPal); `being_removed` (the site's removal case is `Dropping` or `Removed`, or `Holding` within the last hour before `hold_until`, spec 0007 AC-11). A `return_url` that is not `https://`, or whose host is not the host of the row's `site_url`, gets 400. The customer site shows a translated message for each code. Every signed answer, refusals and auth failures included, is built by one helper (`signing.signed_response`) that serializes the body once, signs those exact bytes in `X-Books-Signature`, and sets the HTTP status; signed endpoints never use `frappe.throw` or Frappe's `{"message": ...}` wrapper. A 401 carries no detail.
- **AC-6**: The `go` link sets an HttpOnly, Secure, SameSite=Lax cookie holding the token (path `/api/method/rarebooks_control.billing`, 24 hours), then redirects (302) to the provider's checkout. A token that is unknown, or older than 24 hours, shows "This payment link has expired. Start again from your books." with HTTP 410.
- **AC-7**: A ClickPesa webhook is accepted only when its `checksum` is valid under the ClickPesa checksum key (keys sorted at every level, compact JSON, HMAC SHA256 hex, `checksum` and `checksumMethod` left out). Otherwise it answers 401 and stores nothing. A valid one is stored as a Books Payment Event with no outcome yet, and committed. An `event_id` that already exists with an outcome answers 200 (`duplicate`), stores no new row and changes nothing; one that exists without an outcome is processed again (so a failed provider call can be retried by the provider). Then, holding the site row lock, the control site calls ClickPesa `GET /payments/{orderReference}` and acts only on that answer: `SUCCESS` or `SETTLED`, with `collectedCurrency` equal to the checkout's currency and `collectedAmount` at least the checkout's amount, marks the checkout `Paid` (`paid_on` = now, only the first time), sets `provider` ClickPesa, `billing_period` Yearly, `auto_renews` 0, `provider_reference` = the `order_reference`, and the new `paid_until` (AC-8), pushes (AC-13), and emails the owner a receipt (AC-19). A ClickPesa provider error or timeout answers 503 and leaves the event without an outcome. A second confirmed payment on a checkout already `Paid` (a different ClickPesa payment id) gets outcome `Unknown` and an ops email, with no extra year.
- **AC-8**: A ClickPesa payment buys one year. Start = the latest of (old `paid_until` plus 1 day), (the checkout's `paid_on`, the control site's first confirmation time, as a date in the site's time zone), and (`trial_ends_on` plus 1 day); an empty `paid_until` or `trial_ends_on` term is left out. `paid_until` = start plus 1 year, minus 1 day (a start on 29 February ends on 27 February).
- **AC-9**: A PayPal webhook is accepted only when `POST /v1/notifications/verify-webhook-signature` with the configured `webhook_id` answers `SUCCESS`. Otherwise it answers 401 and stores nothing. A valid one is stored and deduplicated as in AC-7. Then, holding the site row lock, the control site fetches the subscription (`GET /v1/billing/subscriptions/{id}`) and acts only on that answer. It changes the site only when the subscription id equals the site's `provider_reference`, or the site has no live PayPal subscription (then the id becomes `provider_reference`); any other subscription is handled by AC-11. The subscription's `plan_id` must match a Books Plan's `paypal_plan_id` (disabled plans included), else outcome `Mismatch` and an ops email. `ACTIVE` sets `auto_renews` 1, `provider` PayPal, that plan's `billing_period`, and `provider_reference`. When `billing_info.last_payment` exists, its `time` is newer than the latest payment recorded for the site, and its amount and currency match the plan, `paid_until` = the later of the stored value and the smaller of (the date of `billing_info.next_billing_time` in the site's time zone) and (the date of `last_payment.time` in `America/Los_Angeles` plus one period, with no minus 1). `next_billing_time` is the truth and the cap only bounds it, so a retry period that moves `next_billing_time` later grants nothing; with no `next_billing_time` (a cancelled subscription, the final cycle), the cap alone is used. The payment date is read on PayPal's Pacific calendar because PayPal counts its periods there; `next_billing_time` is read in the site's zone because `paid_until` is compared with the site's own today. The charge day itself counts as paid, so a renewing site never reads as `grace` on the morning before PayPal's charge lands, the Subscription page's "Renews on" date is PayPal's real charge day, and a cancelled subscriber keeps that one day (accepted); a payment that doesn't match the plan is `Mismatch` with an ops email. `ACTIVE` with no payment yet (a future `start_time`) sets the fields except `paid_until`. `CANCELLED`, `SUSPENDED` or `EXPIRED` sets `auto_renews` 0 and leaves `paid_until` alone. A PayPal error or timeout answers 503 (PayPal redelivers). Events that arrive out of order or more than once end in the same state.
- **AC-10**: A provider never moves `paid_until` earlier. A PayPal refund or reversal (`PAYMENT.SALE.REFUNDED`, `PAYMENT.SALE.REVERSED`) is stored with outcome `Refund`, emails `books_ops_email`, and changes no state. A ClickPesa payment that fails the AC-7 amount, currency or status check marks the checkout `Mismatch` and the event `Mismatch`, pushes nothing, and emails `books_ops_email` with the order, the amounts and the payer details. A `Mismatch` is final; you settle it with a manual edit (AC-14). `BILLING.SUBSCRIPTION.PAYMENT.FAILED` is stored with no state change and listed in the daily digest.
- **AC-11**: When a second PayPal subscription for a site becomes `ACTIVE` while another is `ACTIVE`, the control site cancels the newer one (by `create_time`) through the PayPal API, keeps the older one, stores the event as `Ignored`, and emails `books_ops_email` (saying to refund by hand if the newer one was already charged). The `CANCELLED` event that follows changes nothing on the site, because that id isn't its `provider_reference` (AC-9). A subscription whose `custom_id` matches a site but that has no Books Checkout gets outcome `Unknown` and an ops email, and changes nothing.
- **AC-12**: The return page (`rarebooks_control.billing.returned`, set as the ClickPesa dashboard return URL and as PayPal's `return_url` and `cancel_url`) finds the checkout from PayPal's `subscription_id` query value or else the AC-6 cookie. It asks the provider for the state, exactly as a webhook would (AC-7, AC-9), applies it in the same idempotent way, and redirects (302) to the checkout's `return_url`. With no checkout found, it shows "You can close this page and go back to your books." with HTTP 200.
- **AC-13**: Every state change (a payment, a lifecycle event, a manual edit, a rotation) increments `state_version` and queues a push of the site's full current state to `receive_state`, run at once in a background job. There is at most one push job per site (`enqueue(job_id="push:<site>", deduplicate=True)`), and the job reads the row and stamps `issued_at` while holding the row lock, so a push never carries older data with a newer `issued_at`. An `applied` or `ignored` answer sets `pushed_version` to the version sent, and the row is `Synced` only when `pushed_version` equals `state_version` (otherwise another push is queued). Otherwise the push is retried 1, 5, 15 and 60 minutes later, then every hour, with no limit, and the row shows `Failing`. One email goes to `books_ops_email` when a site has been `Failing` for 6 hours (once per failing streak), and at once when a site answers 400. A `Removed` site is never pushed. With the customer site up, a confirmed payment lifts its lock within one minute.
- **AC-14**: A Billing Manager can edit `paid_until`, `provider`, `billing_period`, `auto_renews`, `provider_reference`, `exempt`, `allow_test_plans` and `owner_email` on a Books Hosted Site (`provider_reference` only in the same save as a `provider` change). Each save is kept as a Version and pushes the new state. ClickPesa with a period other than Yearly is refused. This manual edit is how you settle a `Mismatch`, a refund, or an `Unknown` payment after a restore. The form's Push now button queues a push at once.
- **AC-15**: Rotate secret (Billing Manager) stores a new `pending_secret`. The next `report_sites` from that site's bench (spec 0007) includes a `rotate_secret` instruction carrying it. The runner writes it into the site's `site_config.json` and calls `secret_rotated`. The control site then makes it the `control_secret`, clears `pending_secret`, and pushes. While a rotation is pending, incoming calls signed with either `control_secret` or `pending_secret` are accepted, and each answer is signed with the secret that verified its request; pushes use `control_secret` until the swap. After the swap only the new secret works. A push refused in the first minute (the customer's web workers cache `site_config.json` for up to 60 seconds) is covered by AC-13's retries. No secret is shown in desk or written to any log.
- **AC-16**: An hourly job asks ClickPesa about every `Created` or `Expired` ClickPesa checkout less than 48 hours old, and a daily job fetches the PayPal subscription of every site with `auto_renews` and of every PayPal checkout less than 7 days old that isn't `Paid`. Any change found is applied as in AC-7 to AC-11, through the same confirm function as the return page (this catches missed webhooks). `Created` checkouts older than 24 hours become `Expired`, but a later confirmed payment on an `Expired` checkout still counts.
- **AC-17**: A confirmed payment for a site that is `Removed` or has a `Dropping` removal case, or whose `order_reference` or `custom_id` matches no registry row, is stored with outcome `Unknown`, pushes nothing, and emails `books_ops_email` at once with the payer details and the amount, so you can refund it or restore the site. After a restore you apply it with a manual edit (AC-14). A payment for a site whose removal case is `Holding` is applied as normal, and spec 0007's next run cancels the case. A payment for an `exempt` site is applied as normal.
- **AC-18**: A daily job blanks `raw_payload` on Payment Events older than 90 days and keeps every other field. No role can delete a Books Payment Event, a Books Checkout or a Books Hosted Site. Books Hosted Site keeps track changes.
- **AC-19**: After each payment that moves `paid_until`, the owner (`owner_email`) gets exactly one receipt email for that event, in the site's `language` (English and Swahili translations ship with the app; any other language gets English): company name, plan label, amount and currency, the period, the new paid until date, and the provider reference. It says it is not a tax invoice.
- **AC-20**: Only a Billing Manager can edit billing fields and plans, or run Push now and Rotate secret. System Manager and Removal Manager can read Books Hosted Site, Books Plan, Books Checkout and Books Payment Event. No one can read a Password field. Every whitelisted action checks its role on the server (`frappe.only_for`), and others get 403. Every desk user must sign in with two factor authentication (an authenticator app).
- **AC-21**: The customer site (this repo, an update to spec 0005) sends `trial_ends_on`, `time_zone`, `language` and `company_name` in its `get_state` and `create_checkout` bodies. It applies a `get_state` answer only when the answer's `state.issued_at` equals the `issued_at` it sent. `call_control` verifies the signature before looking at the status, accepts a signed 409 and hands its `refusal` code to `start_checkout`, which maps each AC-5 code to a translated message (an unsigned or other non 200 answer is still "Couldn't reach billing", spec 0005 AC-16). When `provider` is PayPal, `auto_renews` is on and `paid_until` is empty, the Subscription page says "Your subscription starts on {0}." ({0} = `trial_ends_on` plus 1 day) (it named PayPal until 2026-11-21; the provider is no longer in the text), hides Subscribe, the day 22 to 25 prompt banner is not shown, and `start_checkout` refuses with that same text. From the day after {0} (the site's today later than it) with `paid_until` still empty, the first charge has failed and PayPal is retrying it (the subscription stays `ACTIVE`, so a new checkout would be refused `already_subscribed`): the note and the `start_checkout` refusal become "Your first PayPal payment hasn't arrived. Check the payment method in your PayPal account.", Subscribe stays hidden, and the prompt banner and the day 26 lock work as normal.
- **AC-22**: The control bench runs as its own Linux user, with its folders readable by that user only. Its Redis cache and queue require a password. It has its own MariaDB user and database, and it is served over HTTPS only. The hosting bench user can't read its `site_config.json` or run its jobs. Every guest endpoint is rate limited: signed site and runner calls per site or bench (they all come from the hosting server's one IP), webhooks, `go` and `returned` per client IP, read from nginx's `X-Forwarded-For`. One email per hour goes to `books_ops_email` when more than 20 calls in that hour fail signature checks.
- **AC-23**: Launch check: on a staging customer site, Subscribe reaches a real ClickPesa checkout (a `test_only` plan of TZS 1,000 on a site with `allow_test_plans`) and a PayPal sandbox checkout. Each confirmed payment lifts the lock within a minute. A PayPal sandbox cancel, suspend and expiry each push the change. A webhook with a bad signature or checksum changes nothing.

## Decision

**Chosen option**: Option 1: a Frappe 16 app on its own bench that verifies every provider event, asks the provider for the truth, and pushes the full state to the site.

`rarebooks_control` owns the site registry, the per site secrets, the plans, the provider calls and the push to each site, and it hosts spec 0007's removal side. Provider truth always comes from a fresh provider API read, never from a webhook body.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `paypal-best-practices` (`paypal/ai-toolkit`, `.agents/skills/paypal-best-practices/`, its `references/subscriptions.md` and `references/webhooks.md`) · `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

Two repos are touched. `rarebooks_control` (new, Frappe 16) holds everything below unless marked "this repo". This repo (frappe_books) gets the AC-21 contract update, the `books-register-site` command and the runner's `rotate_secret` step.

**Data model sketch** (control site; spec 0007's Books Hosting Bench and Books Removal Case are reused unchanged):

Books Hosted Site (the registry; autoname from `site`; `track_changes: 1`; no delete permission for any role):

| Field | Type | Required | Notes |
|---|---|---|---|
| `site` | Data, unique | yes | The customer's `frappe.local.site`. Primary key |
| `site_url` | Data | yes | `https://` URL from registration. Its host bounds `return_url` (AC-5) |
| `hosting_bench` | Link: Books Hosting Bench | yes | Spec 0007. N sites to 1 bench |
| `owner_email` | Data (Email) | yes | The signup email. Billing Manager edits |
| `status` | Select: Active, Removed | yes | Default Active. Set to Removed by 0007's `drop_done` |
| `removed_on` | Datetime | no | UTC. Spec 0007 |
| `control_secret` | Password | yes | 64 hex characters |
| `pending_secret` | Password | no | Set by Rotate secret until `secret_rotated`; accepted on incoming calls meanwhile |
| `paid_until` | Date | no | The site's date. Permlevel 1 (Billing Manager writes) |
| `provider` | Select: ClickPesa, PayPal | no | Permlevel 1 |
| `billing_period` | Select: Monthly, Yearly | no | Permlevel 1. ClickPesa is always Yearly |
| `auto_renews` | Check | no | Permlevel 1 |
| `provider_reference` | Data | no | Current PayPal subscription id or the paid ClickPesa `order_reference`. Permlevel 1, read only in the form unless `provider` is changed in the same save |
| `last_payment_on` | Datetime | no | UTC time of the latest payment applied (PayPal `last_payment.time`, or ClickPesa `paid_on`). Guards AC-9 |
| `exempt` | Check | no | Permlevel 1 |
| `allow_test_plans` | Check | no | Permlevel 1. Shows `test_only` plans (AC-2) |
| `trial_ends_on` | Date | no | From the site's last signed call (AC-2, AC-21) |
| `time_zone` | Data | no | IANA name from the site's last signed call. Empty means UTC |
| `language` | Data | no | From the site's last signed call. For emails |
| `company_name` | Data | no | From the site's last signed call. For emails |
| `state_version` | Int | yes | Default 0. Incremented on each change of a pushed field |
| `pushed_version` | Int | yes | Default 0. The `state_version` of the last `applied` or `ignored` push |
| `push_status` | Select: Synced, Pending, Failing | yes | Default Synced |
| `push_attempts` | Int | no | Failed attempts in the current streak |
| `next_push_on` | Datetime | no | UTC |
| `failing_since` | Datetime | no | UTC, start of the current failing streak |
| `failing_alerted` | Check | no | The 6 hour email was sent for this streak |
| `last_pushed_on` | Datetime | no | UTC, last `applied` or `ignored` answer |
| `last_push_error` | Small Text | no | No secrets |

Books Plan (Billing Manager writes; everyone in AC-20 reads):

| Field | Type | Required | Notes |
|---|---|---|---|
| `provider` | Select: ClickPesa, PayPal | yes | Unique together with `billing_period` (checked in `validate`) |
| `billing_period` | Select: Monthly, Yearly | yes | ClickPesa only Yearly |
| `amount` | Currency, `options: currency` | yes | Whole TZS for ClickPesa (precision 0); USD with cents for PayPal (precision 2), rounded per `currency` in `validate`; compared as Decimal |
| `currency` | Select: TZS, USD | yes | ClickPesa TZS, PayPal USD |
| `label` | Data | yes | Shown on the customer's Subscription page |
| `paypal_plan_id` | Data | PayPal only | Created by hand in PayPal and pasted here |
| `enabled` | Check | no | |
| `test_only` | Check | no | Offered only to `allow_test_plans` sites. A test plan lives beside the real one, so the unique rule covers (`provider`, `billing_period`, `test_only`) |

Books Checkout (autoname `CHK-.#####`; no delete; created only by `create_checkout`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `site` | Link: Books Hosted Site | yes | N checkouts to 1 site |
| `plan` | Link: Books Plan | yes | N checkouts to 1 plan |
| `provider`, `billing_period`, `amount`, `currency` | copied from the plan | yes | Frozen at creation |
| `token_hash` | Data, unique | yes | SHA256 hex of the `go` token |
| `order_reference` | Data, unique | ClickPesa only | `RB` plus the checkout number, 8 digits (for example `RB00000042`), letters and digits only |
| `paypal_subscription_id` | Data, unique | PayPal only | |
| `provider_url` | Small Text | yes | ClickPesa link or PayPal `approve` link |
| `return_url` | Data | yes | From the site, checked per AC-5 |
| `status` | Select: Created, Paid, Mismatch, Expired | yes | Default Created |
| `paid_on` | Datetime | no | UTC |

Books Payment Event (one per webhook or confirmation; no delete):

| Field | Type | Required | Notes |
|---|---|---|---|
| `event_id` | Data, unique | yes | PayPal `id`; ClickPesa `clickpesa:<data.id>:<event>`; a return page or reconcile confirmation `confirm:<checkout>:<provider status>` for ClickPesa and `confirm:<subscription id>:<status>:<next_billing_time>` for PayPal. Duplicates store no new row |
| `provider` | Select: ClickPesa, PayPal | yes | |
| `event_type` | Data | yes | |
| `site` | Link: Books Hosted Site | no | Empty when unknown |
| `checkout` | Link: Books Checkout | no | |
| `amount`, `currency` | Currency, Data | no | As the provider confirmed |
| `outcome` | Select: Applied, Ignored, Mismatch, Refund, Unknown | no | Empty until processed; an event with an outcome is never processed again |
| `paid_until_after` | Date | no | The site's `paid_until` after this event |
| `raw_payload` | Long Text | no | Blanked after 90 days (AC-18) |
| `received_on` | Datetime | yes | UTC |

**State transitions**:

Books Checkout: `Created` → `Paid` (confirmed and matching) · `Created` → `Mismatch` (confirmed, not matching) · `Created` → `Expired` (24 hours, unpaid) · `Expired` → `Paid` (a late confirmed payment; abandoned or auto cancelled PayPal checkouts simply expire). `Paid` and `Mismatch` are final.

Books Hosted Site `push_status`: `Synced` → `Pending` (any state change) → `Synced` (`applied` or `ignored` with `pushed_version` = `state_version`) or `Failing` (any other answer) → `Synced` on the next good push.

Rotation: (none) → `pending_secret` set (Rotate secret; both secrets accepted) → swapped (`secret_rotated`; new secret only).

**Provider calls** (thin modules `rarebooks_control/providers/clickpesa.py` and `paypal.py`, using `requests` with a 10 second timeout; no provider SDK):
- ClickPesa: token from `POST /third-parties/generate-token` (headers `client-id`, `api-key`), cached in `frappe.cache` for 55 minutes. Checkout link from the hosted checkout link endpoint with the amount, `TZS`, `order_reference`, and the owner's email. When checksums are enabled on the ClickPesa app, outgoing bodies carry `checksum` too. Payment status from `GET /third-parties/payments/{orderReference}`.
- PayPal: OAuth token from `POST /v1/oauth2/token`, cached until 60 seconds before `expires_in`. `POST /v1/billing/subscriptions` (`plan_id`, `custom_id`, `start_time`, `application_context` with `brand_name`, `shipping_preference: NO_SHIPPING`, `user_action: SUBSCRIBE_NOW`, `return_url`, `cancel_url`), `GET /v1/billing/subscriptions/{id}`, `POST /v1/billing/subscriptions/{id}/cancel`, `POST /v1/notifications/verify-webhook-signature`. Base URL from `paypal_mode` (sandbox or live).
- Handled PayPal events: `BILLING.SUBSCRIPTION.ACTIVATED`, `.UPDATED`, `.CANCELLED`, `.SUSPENDED`, `.EXPIRED`, `.PAYMENT.FAILED` (stored, no state change), `PAYMENT.SALE.COMPLETED`, `PAYMENT.SALE.REFUNDED`, `PAYMENT.SALE.REVERSED`. Any other type is stored as `Ignored`.

**Apply step** (`rarebooks_control/billing.py` `confirm(site, provider, reference, event)`): locks the Books Hosted Site row first (`for_update`), then calls the provider (10 second timeout, so a lock is held at most that long), works out the new state from that answer (AC-7 to AC-11), writes the Checkout, the Event outcome and the site fields in one transaction, and, when any pushed field changed, increments `state_version`, sets `push_status` Pending and queues the push after commit. Webhooks, the return page and the reconcile jobs all call it, so they can't disagree. The site is resolved before locking: ClickPesa by the Checkout's `order_reference`, PayPal by the subscription's `custom_id` from a first unlocked read, then read again under the lock.

**Signed answers** (`rarebooks_control/signing.py` `signed_response(body: dict, status: int, secret)`): serializes once with `json.dumps(separators=(",", ":"))`, sets `X-Books-Signature: sha256=<hex>` over those bytes, sets the status, and returns a werkzeug `Response`, so Frappe adds no wrapper or `_server_messages`. Used by every signed endpoint, for refusals and 401s too.

**API surface** (control site; every guest POST reads the raw body with `frappe.request.get_data()`; every whitelisted method is type annotated):

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `rarebooks_control.api.register_site` | POST | `bench`, `issued_at`, `site`, `site_url`, `owner_email` | signed `{site, secret}` | guest, runner HMAC (0007), rate limited 30 per minute per bench | 401 bad signature, unknown bench, stale; 409 site on another bench or Removed; 400 bad `site_url` or email |
| `rarebooks_control.api.get_state` | POST | `site`, `issued_at`, `trial_ends_on`, `time_zone`, `language`, `company_name` | signed `{state: {...push fields, issued_at: <echo>}, plans: [...]}` | guest, site HMAC, rate limited 30 per minute per site (keyed on the body's `site` after the signature check) | 401 bad signature, stale, unknown or Removed site |
| `rarebooks_control.api.create_checkout` | POST | `site`, `issued_at`, `provider`, `billing_period`, `return_url`, `trial_ends_on`, `time_zone`, `language`, `company_name` | signed `{checkout_url}` | guest, site HMAC, rate limited 10 per minute per site | 401 as above; 400 bad `return_url`; 409 signed `{refusal}` (AC-5); 502 signed, provider error or timeout |
| `rarebooks_control.webhooks.clickpesa` | POST | ClickPesa JSON with `checksum` | `{result}` | guest, checksum, `@rate_limit(limit=300, seconds=60)` per IP | 401 bad checksum; 503 ClickPesa unreachable; 200 for duplicates and unknown orders |
| `rarebooks_control.webhooks.paypal` | POST | PayPal event plus its `PAYPAL-*` headers | `{result}` | guest, PayPal verify call, `@rate_limit(limit=300, seconds=60)` | 401 verify not SUCCESS; 503 when PayPal can't be reached (PayPal retries) |
| `rarebooks_control.billing.go` | GET | `token` | 302 to `provider_url`, sets the cookie | guest, `@rate_limit(limit=30, seconds=60)` | 410 unknown or expired |
| `rarebooks_control.billing.returned` | GET | `subscription_id` (PayPal), cookie | 302 to `return_url`, or the close page | guest, `@rate_limit(limit=30, seconds=60)` | 200 close page when no checkout is found |
| `rarebooks_control.billing.push_now` | POST | `site` | `{queued: true}` | Billing Manager (`frappe.only_for`) | 403; 417 Removed site |
| `rarebooks_control.billing.rotate_secret` | POST | `site` | `{pending: true}` | Billing Manager | 403; 417 Removed site or a rotation already pending |
| `rarebooks_control.removal.secret_rotated` | POST | `bench`, `issued_at`, `site` | signed `{status}` | guest, runner HMAC | 401; 409 no rotation pending |
| `rarebooks_control.removal.report_sites` (spec 0007) | POST | as in 0007 | adds `rotate_secret` instructions: `{site, action: "rotate_secret", secret}` | runner HMAC | as in 0007 |
| `rarebooks_control.billing.billing_state(site)` | Python | site name | `paid_until`, `exempt`, `auto_renews`, `checkout_in_last_24h` (a Books Checkout of the site created in the last 24 hours that is `Created`, or that became `Paid` in the last 24 hours) | in process (spec 0007's drop and cancel checks) | none |

Rate limits keyed per site or bench use a `frappe.cache` counter (`rl:<endpoint>:<key>:<minute>`) checked right after the signature passes, since Frappe's `@rate_limit` keys on IP or user, and every customer site and runner calls from the hosting server's one IP.

Push to the site: `POST {site_url}/api/method/frappe_books.subscription.receive_state`, body `site`, `issued_at` (now, UTC, with `+00:00`), and the six state fields, signed `X-Books-Signature: sha256=<hex>` with `control_secret`, 10 second timeout.

This repo (frappe_books, AC-1, AC-15, AC-21):

| Piece | Change |
|---|---|
| `commands.py` `books-register-site` | New bench command with `--owner-email` and `--site-url` (required, `https://`). Reads `books-runner.json` (spec 0007) for `runner_name`, `runner_secret`, `control_url`; calls `register_site`; verifies the signed answer and its `issued_at` echo; writes both keys with Frappe's site config update; prints when a re run left fields unchanged |
| `runner.py` | Carries out `rotate_secret` before `clear` (writes `books_control_secret`, then calls `secret_rotated`) |
| `subscription/control.py` | Adds the four site facts to `get_state` and `create_checkout`; refuses a `get_state` answer whose `state.issued_at` isn't its own; checks the signature before the status and returns a signed 409's `refusal` instead of raising `ControlSiteUnreachable` |
| `subscription/api.py`, `clock.py`, the Subscription page and banner | Refusal code messages; the PayPal "starts on" note, the hidden Subscribe and the prompt banner rule; `start_checkout` refusal (AC-21) |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| `register_site` | secret | `secrets.token_hex(32)` on the control site |
| `register_site` | bench identity | body `bench` checked against `books_runner_secrets` in the control site's `site_config.json` (spec 0007) |
| `register_site` | `owner_email`, `site_url` | the command's `--owner-email` and `--site-url` arguments (`get_url()` outside a request gives `http://<site>:8000`, so it is not used) |
| `get_state`, `create_checkout` | `trial_ends_on`, `time_zone`, `language`, `company_name` | the customer site's status dict (`trial_ends_on`), System Settings `time_zone` and `language`, `frappe_books.settings` company name, all sent in the signed body (AC-21) |
| `get_state` | `state.issued_at` | the request's `issued_at`, echoed |
| `get_state` | `plans` | enabled Books Plan rows, `test_only` filtered by `allow_test_plans` |
| `create_checkout` | amount, currency, PayPal plan id | the Books Plan for body `provider` and `billing_period` (plus `test_only` when the site allows it and a test plan exists for that pair) |
| `create_checkout` | `order_reference` | `RB` plus the checkout's autoname number, zero padded to 8 |
| `create_checkout` | `start_time` (PayPal) | the later of body `trial_ends_on` + 1 day and stored `paid_until` + 1 day (body `trial_ends_on`, the site's own dates, calendar arithmetic), that same date at 12:00 in `America/Los_Angeles` (PayPal's billing calendar), as UTC `Z`; sent only when that day is later than the site's today in body `time_zone`, else none |
| `create_checkout` | reused checkout's link | a new token, its hash written over `token_hash` |
| `create_checkout` | PayPal `return_url`, `cancel_url` | `{control url}/api/method/rarebooks_control.billing.returned` |
| `create_checkout` | "current subscription is ACTIVE or APPROVED" | a live `GET` of the row's `provider_reference` when `provider` is PayPal |
| `create_checkout` | `being_removed` | the site's open Books Removal Case `status` and `hold_until` (spec 0007) |
| `go` | token | `secrets.token_urlsafe(32)`, made at `create_checkout`; only its SHA256 is stored |
| `returned` | which checkout | PayPal's `subscription_id` query value matched to `paypal_subscription_id`, else the cookie token's hash |
| ClickPesa apply | payment date | the checkout's `paid_on` (control site time of the first confirmation), converted to `time_zone` |
| ClickPesa apply | new `paid_until` | AC-8, from the stored `paid_until`, that payment date and the stored `trial_ends_on` |
| ClickPesa apply | "a second payment on a Paid checkout" | a SUCCESS or SETTLED item whose ClickPesa `id` differs from the one recorded on the checkout's Applied event |
| PayPal apply | new `paid_until` | AC-9: the smaller of (`next_billing_time` date in `time_zone`, the charge day counted as paid) and (`last_payment.time` date in `America/Los_Angeles` plus one period, no minus 1); the cap alone when there is no `next_billing_time`; only when `last_payment.time` is after `last_payment_on`, never earlier than the stored value |
| PayPal apply | `billing_period`, money check | the Books Plan (disabled included) whose `paypal_plan_id` equals the subscription's `plan_id`; `last_payment.amount` `value` and `currency_code` against it |
| alert emails | payer details | ClickPesa status answer `customer` (`customerName`, `customerPhoneNumber`, `customerEmail`); PayPal subscription `subscriber` (`name`, `email_address`) |
| PayPal apply | which subscription is newer (AC-11) | PayPal `create_time` |
| any apply | the site | ClickPesa: the Checkout by `orderReference`; PayPal: subscription `custom_id`, cross checked with the Checkout by subscription id |
| push | `issued_at` | the control site's clock at send time (NTP synced, spec 0005) |
| push | retry times | `next_push_on` = failure time plus 1, 5, 15, 60, then 60 minutes per attempt, from `push_attempts` |
| receipt | language, company name | Books Hosted Site `language` (English or Swahili, else English), `company_name` |
| receipt | "once per event" | sent inside the apply of the event that moved `paid_until`, after commit; a reprocessed event finds `paid_until` already moved and sends nothing |
| any date shown or computed for a site | "the site's day" | `time_zone` on the row; UTC when empty or not a valid IANA name (spec 0005 AC-18), never an error |
| rate limits by IP | client IP | `frappe.local.request_ip`, which honours nginx's `X-Forwarded-For` |
| ops emails | recipient | control site `books_ops_email` (spec 0007) |
| signature failure alert | count | a `frappe.cache` counter per hour, incremented on each failed check; the email is sent when it reaches exactly 21 |
| "at once" ops emails | delivery | `frappe.sendmail(..., now=True)`; everything else through the Email Queue, so the bench scheduler must be on |
| PayPal and ClickPesa credentials | keys | control site `site_config.json` (Configuration below) |

**Key invariants**:
- Nothing changes a site's state from a webhook body alone. The row lock is taken first, then the provider is read, then the state is written, so two events can't apply in the wrong order.
- Only the subscription named in `provider_reference` changes a PayPal site's state.
- A push never carries older data than the push before it (one job per site, `state_version`).
- A provider never moves `paid_until` earlier. Only a Billing Manager's tracked edit can.
- A ClickPesa payment buys at most one year, and only when amount and currency match the checkout.
- A site has at most one `ACTIVE` PayPal subscription that the control site keeps.
- Every push carries the full current state, so the latest push always wins and a lost push is repaired by the next one.
- `return_url` always points back to the site's own `https` host (no open redirect).
- The control site never computes a trial or removal date. It uses only what the site reports.
- A secret is never shown, logged, emailed or returned except to the bench that registered or is rotating that site.

**Security model**:
- Compliance: payment records and payer names, emails and phone numbers are personal data. No card data ever touches the control site (both providers host the checkout), so PCI scope stays with the providers. Raw payloads are kept 90 days. Summaries, Checkouts and Versions are the audit trail and are never deleted.
- Roles: Billing Manager (new) writes the permlevel 1 billing fields, Books Plan, `owner_email`, and runs Push now and Rotate secret. Removal Manager (spec 0007) and System Manager read. Password fields are never sent to the browser. Two factor sign in for every desk user.
- Machine calls: site calls use that site's secret, runner calls use the bench's runner secret, and both are signed both ways with a 5 minute `issued_at` window (spec 0005). Provider webhooks are verified by checksum (ClickPesa) or PayPal's verify call. All guest methods are rate limited.
- Host isolation: control bench under its own Linux user (`control`), home and bench folders mode 700, its own supervisor programs, Redis cache and queue with passwords (the queue through Frappe's `bench create-rq-users`), its own MariaDB user and database. Shared nginx with its own server block and certificate. The hosting runner's MariaDB root login (spec 0007) can still read the control database, so secrets stay safe only because Password fields are encrypted with the control site's `encryption_key`, which only the `control` user can read.
- Never log the site secrets, runner secrets, provider keys, the checksum key or a `go` token. Password fields must never appear in Version diffs (a test checks it).
- Administrator bypasses role checks and the no delete rule, as in any Frappe site. That is accepted; keep the Administrator password offline and use named users.

**Configuration required** (control site `site_config.json`, readable by the `control` user only):
- `clickpesa_client_id`, `clickpesa_api_key`: the ClickPesa app credentials (the same account rarebooks-site uses).
- `clickpesa_checksum_key`: the ClickPesa checksum key, for webhooks and signed requests.
- `paypal_mode` (`sandbox` or `live`), `paypal_client_id`, `paypal_client_secret`, `paypal_webhook_id`.
- `books_runner_secrets`, `books_ops_email` (spec 0007), and the spec 0007 removal keys.
- `encryption_key`: Frappe's own; keep an offline copy, since the Password fields are unreadable without it.
- System Settings: two factor auth on for all roles, method OTP App (set by `after_install`).
- Email Account: Resend SMTP (`smtp.resend.com`, port 465, user `resend`, an API key as password), on a sending domain with SPF, DKIM and DMARC, default outgoing.
- ClickPesa dashboard: webhook URL `…/api/method/rarebooks_control.webhooks.clickpesa`, return URL `…/api/method/rarebooks_control.billing.returned`, checksum enabled.
- PayPal: one product, one plan per period in USD (no setup fee, a payment failure threshold of 3), a webhook to `…/api/method/rarebooks_control.webhooks.paypal` for the events above; sandbox first, live later.
- Host: Linux user `control`, its own bench ports (web, socketio, Redis) apart from the hosting bench, `bench setup supervisor --user control`, the scheduler enabled (`bench --site <control site> enable-scheduler`), an nginx server block and certificate for the control domain that sets `X-Forwarded-For`, NTP on.
- Backups: Frappe's S3 Backup Settings daily to a separate private R2 bucket with its own token, plus an offline copy of `site_config.json`.
- Customer sites: `books_control_url` and `books_control_secret` are written by `books-register-site` (AC-1).

**Critical test scenarios** (Python in `rarebooks_control` with patched provider modules and a customer site stub; this repo's side with spec 0005's `ControlStub`):
- Happy path ClickPesa: register, `get_state`, `create_checkout`, `go`, a signed webhook, the status query says SUCCESS, the checkout is `Paid`, `paid_until` is a year out, the push is `applied`, the receipt is queued. Verifies **AC-1**, **AC-2**, **AC-3**, **AC-6**, **AC-7**, **AC-8**, **AC-13**, **AC-19**.
- Date rules: a payment on trial day 10 starts the year at `trial_ends_on` + 1; an early renewal extends from the old end; a renewal 30 days after lapse starts on the payment day; a start on 29 February; Dar es Salaam near midnight. Verifies **AC-8**.
- PayPal during trial: `start_time` is trial end + 1 at 12:00 Pacific in UTC `Z` (a trial ending 23 November gives `2026-11-24T20:00:00Z`, whatever the site zone); a site whose day after is today or past (a lapsed renewal) sends none; ACTIVATED with no payment sets `auto_renews` and no `paid_until`; SALE.COMPLETED sets `paid_until` by AC-9's smaller of rule (a first charge at 2026-11-24T10:00Z with the next on 2026-12-24T10:00Z gives 24 December in Dar es Salaam, not 23 December; a charge at 2026-11-19T05:01Z, Pacific 18 November, with the next on 2026-12-18T10:00Z gives 18 December); a Yearly plan gives the next billing date a year on; events in reverse order give the same state; CANCELLED keeps `paid_until`; a retry period where `next_billing_time` moves but `last_payment` doesn't grants no days; a payment on an unknown `plan_id` or with the wrong amount is `Mismatch`. Verifies **AC-4**, **AC-9**, **AC-10**.
- Ordering: two webhooks for one site processed at once (ACTIVE, then CANCELLED) end CANCELLED; two pushes queued close together send the newer state last and end `Synced`; a ClickPesa 503 on the status query leaves the event unprocessed and a redelivery applies it. Verifies **AC-7**, **AC-9**, **AC-13**.
- Signed answers: a refusal and a 401 come back as raw signed bytes with the right status and no `message` wrapper; this repo's `call_control` turns a signed 409 into the refusal message. Verifies **AC-5**, **AC-21**.
- Bad signatures: a bad ClickPesa checksum and a PayPal verify `FAILURE` both answer 401 and store nothing; 21 failures in an hour send one alert. Verifies **AC-7**, **AC-9**, **AC-22**, **AC-23**.
- Mismatch, refund, unknown: an underpayment, a USD ClickPesa payment, a refund, and a payment for a Removed site each store the right outcome, push nothing and email ops. Verifies **AC-10**, **AC-17**.
- Double subscription: a second ACTIVATED for the same site cancels the newer one only, and its CANCELLED event leaves `auto_renews` on. `create_checkout` (PayPal or ClickPesa) with an ACTIVE subscription refuses `already_subscribed`. A reused checkout gets a new working link and the old link answers 410. Verifies **AC-3**, **AC-5**, **AC-11**.
- Refusals: `being_removed` within the hour before `hold_until`; a `return_url` on another host gets 400; a `test_only` plan without `allow_test_plans` gets `plan_not_offered`. Verifies **AC-5**.
- Push failure: the stub times out, the row is `Failing`, retries follow the schedule, one alert at 6 hours, a 400 alerts at once, recovery returns to `Synced`. Verifies **AC-13**.
- Return page: a PayPal return applies the state before the webhook, and the later webhook makes no second change and sends no second receipt; no cookie shows the close page. Verifies **AC-12**.
- Reconcile: a missed ClickPesa webhook is found by the hourly job; an old `Created` checkout expires and a late payment on it still counts. Verifies **AC-16**.
- Rotation: while pending, calls signed with either secret pass and are answered with the same secret; `rotate_secret` reaches the runner; `secret_rotated` swaps; afterwards the old secret gets 401. Verifies **AC-15**.
- Rate limits: 30 `get_state` calls a minute from one IP for 30 different sites all pass; the 31st call for one site in a minute is refused. Verifies **AC-22**.
- Auth: a Removal Manager calling `push_now` gets 403; a System Manager can't edit `paid_until`; no API answer includes a Password field. Verifies **AC-14**, **AC-20**.
- Retention: a 91 day old event has an empty `raw_payload` and keeps its summary. Verifies **AC-18**.
- Contract vectors: both repos sign the same golden vectors (body bytes, secret, expected header) and get the same result. Verifies **AC-2**, **AC-13**.
- This repo: the four facts are in the signed bodies; a `get_state` answer with another `issued_at` gives the Retry state; each refusal code shows its message; the "starts on" note, hidden Subscribe and no prompt banner on day 23 with PayPal `auto_renews` and no `paid_until`. Verifies **AC-21**.

## Build plan

Tracer Bullet: Milestone 1 runs one real ClickPesa shaped payment end to end (registry, signed pull, checkout, webhook, provider check, push, unlocked customer site) against stubs before PayPal, retries or operator tools. Milestone 5 is the only one that touches real money.

**Milestone 1: The thread, one ClickPesa payment end to end (against stubs)**
1. New repo `rarebooks_control` (Frappe 16 app): ruff 0.14.10, tabs, CI on MariaDB 11.8 and Redis 7 as in this repo, an `AGENTS.md` (run `/audit` there). Satisfies **AC-20**, **AC-22**.
2. The whole data model in one go: Books Hosted Site, Books Plan, Books Checkout, Books Payment Event, plus spec 0007's Books Hosting Bench, with the Billing Manager role and its permlevels. Satisfies **AC-14**, **AC-18**, **AC-20**.
3. `signing.py` (sign, verify, `issued_at` window, echo, `signed_response`, per site rate limit), copied from this repo's `subscription/control.py` rules, with shared golden vectors tested in both repos. Satisfies **AC-1**, **AC-2**, **AC-5**, **AC-13**, **AC-22**.
4. `register_site` and, in this repo, `bench books-register-site`. Satisfies **AC-1**.
5. `get_state` with plans and stored facts; in this repo, the four facts in the bodies, the echo check, and `call_control` accepting a signed 409 refusal. Satisfies **AC-2**, **AC-21**.
6. `create_checkout` for ClickPesa, `go`, the ClickPesa module (token, link, status query) behind a patchable boundary. Satisfies **AC-3**, **AC-6**.
7. The ClickPesa webhook, checksum, event dedup, `confirm` (lock, then fetch, then write), the AC-8 date rule, and a single push attempt with `state_version`. Satisfies **AC-7**, **AC-8**, **AC-13**.

**Milestone 2: PayPal**
8. PayPal module (token, create, get, cancel, verify) with `paypal_mode`. Satisfies **AC-4**, **AC-9**.
9. `create_checkout` for PayPal with `start_time` and `already_subscribed`; the PayPal webhook and its event handling; refunds; the double subscription cancel. Satisfies **AC-4**, **AC-5**, **AC-9**, **AC-10**, **AC-11**.
10. This repo: refusal code messages, the "starts on" note, the hidden Subscribe, the prompt banner rule and the `start_checkout` refusal, with Node and Playwright tests. Satisfies **AC-5**, **AC-21**.
11. A PayPal sandbox run end to end on a staging customer site (also confirms the subscription status PayPal reports before a future `start_time`). Satisfies **AC-4**, **AC-9**, **AC-23**.
11a. From the sandbox findings (2026-11-19): `start_time` at 12:00 Pacific on the day after the trial or `paid_until`, and the PayPal `paid_until` counting the charge day; update `state.paypal_start_time`, `state.paypal_paid_until` and their tests (Monthly and Yearly, a lapsed renewal, no `next_billing_time`); in this repo the "first payment hasn't arrived" note and refusal (AC-21); then, before relying on the rule, check in the sandbox that PayPal's first `next_billing_time` lands on that day for a Monthly and a Yearly plan. Satisfies **AC-4**, **AC-9**, **AC-21**.

**Milestone 3: Reliability**
12. The push queue: one deduplicated job per site, `pushed_version`, retry schedule, `push_status`, the 6 hour and 400 alerts (`now=True`), the per minute sweep of `next_push_on`. Satisfies **AC-13**.
13. The return page with its provider confirmation. Satisfies **AC-12**.
14. Reconcile jobs, checkout expiry, mismatch and unknown payment alerts, the receipt email, the 90 day retention job. Satisfies **AC-10**, **AC-16**, **AC-17**, **AC-18**, **AC-19**.
15. `create_checkout`'s `being_removed` refusal and `billing_state()` for spec 0007's checks. Satisfies **AC-5**.

**Milestone 4: Operator tools and hardening**
16. Manual edit with validation and push on save, Push now, a Billing workspace with list views showing `push_status`. Satisfies **AC-14**.
17. Rotate secret, the `rotate_secret` instruction in `report_sites`, `secret_rotated`, and in this repo the runner step. Satisfies **AC-15**.
18. Two factor auth in `after_install`, rate limits on every guest method, the signature failure counter and alert. Satisfies **AC-20**, **AC-22**.

**Milestone 5: Rollout**
19. Host setup: the `control` user, the bench and its ports, Redis passwords, supervisor, nginx and certificate, NTP, R2 backups and the offline `site_config.json` copy. Check that the hosting bench user can't read the control files or reach its Redis. Satisfies **AC-22**.
20. Resend Email Account and DNS; ClickPesa dashboard webhook, return URL and checksum; PayPal live product, plans and webhook; Books Plan rows with the real prices. Satisfies **AC-3**, **AC-4**, **AC-19**.
21. The live launch check with the TZS 1,000 `test_only` plan and the PayPal sandbox; then disable the test plan and register the first real sites. Satisfies **AC-23**.

## Consequences

**Positive**:
- Customer sites never hold a provider key, and every unlock is proven with the provider, so a forged or replayed webhook can't unlock anything.
- One apply step serves webhooks, the return page and reconcile, so a slow or missing webhook still unlocks within a minute of return, or within an hour of payment.
- The same app hosts spec 0007's removal records, so billing state and removal checks read one database.

**Negative / tradeoffs**:
- A second app to build, test and operate, and a second repo to keep in sync with this one through a contract only tests can guard (the golden vectors).
- Same server hosting (your choice over a separate VPS): a compromise or outage of the hosting server takes billing with it. The hosting runner's MariaDB root login can read the control database, so the plain payment records there are only as safe as that server. Redis passwords are mandatory, because an open Redis queue would let the hosting user run code as `control`.
- ClickPesa has no sandbox, so the launch check costs real money, and its webhook and return details may only be fully confirmed live.
- Each webhook makes one or two extra provider API calls (verify, fetch). Fine at this scale, but provider outages now delay state.
- Lost `encryption_key` means every site secret is lost, and every site must be registered again.
- Receipts are not TRA fiscal receipts.
- The `go` cookie holds one token, so two checkouts opened in one browser leave only the newer one for a ClickPesa return; the webhook and the hourly reconcile still apply the other.
- A lock is held across one provider call (up to 10 seconds) per event. Fine at this volume, a hot spot only at thousands of events a minute.

**Neutral**:
- Spec 0005's contract grows by four body fields, refusal codes and the echo check (AC-21), and spec 0007's `report_sites` gains `rotate_secret`. Both specs need a short amendment.
- Price changes for existing PayPal subscribers aren't covered. A new price is a new PayPal plan for new subscribers only.

## Follow-up

- [ ] Amend spec 0005 (contract table: the four facts in `get_state` and `create_checkout`, the echo, refusal codes, the "starts on" note) and spec 0007 (`rotate_secret`, `secret_rotated`, `billing_state()`), pointing to this spec.
- [ ] Two specs share the number 0007 (`0007-lock-hardening`, `0007-trial-end-export-removal`). Consider renumbering one so links stay unambiguous.
- [ ] Confirm the exact ClickPesa hosted checkout link endpoint and field names, whether its return redirect carries the order reference, and whether checksums are required on outgoing requests, during task 6 (Context7 showed two different summaries of the link endpoint).
- [x] Confirm in the PayPal sandbox the status and `billing_info` a subscription shows between approval and a future `start_time` (task 11). Done 2026-11-19: `ACTIVE`, no `last_payment`, `cycles_completed` 0, so AC-9's "no payment yet" rule holds.
- [ ] The Pacific billing calendar rests on two sandbox subscriptions. Recheck it on the live account at launch (AC-23), and once while the US is on daylight saving time (PayPal's charge should then move to about 09:00 UTC, still on the same Pacific day).
- [ ] Rotation of the runner secrets in `books_runner_secrets` (spec 0007) isn't covered. Design it when a bench secret needs changing.
- [ ] Fiscal (TRA VFD/EFD) receipts for Tanzanian payments, if your accountant needs them.
- [ ] Self serve signup (a public form that provisions a site and calls `register_site`) as its own scope feature.
- [ ] `paypal-best-practices` conventions belong in the `rarebooks_control` repo's `AGENTS.md` (payments area), not in this repo's root. The spec 0005 follow ups for the `hookdeck/webhook-skills@paypal-webhooks` skill and the PayPal MCP server (sandbox credentials only) still apply.
- [ ] Agent Skills or MCP servers for Resend and ClickPesa were not searched (you chose later). A ClickPesa skill would give the build its real request shapes, and a Resend MCP server could check delivery of the removal warnings.
