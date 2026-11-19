# Verify: billing control site · spec 0008 · updated 2026-11-18
_Steps derived from spec 0008 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. Covers Milestone 1: this repo's half (tasks 3 to 5) and the control site half in `rarebooks_control` (tasks 3 to 7)._

## Commands (this repo)
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_registration` → 6 tests pass → AC-1
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_control` → 43 tests pass, including `IntegrationTestSpec0008Contract` and `UnitTestSigningVectors` → AC-2, AC-5, AC-21, task 3
- [x] `bench books-register-site <site> --owner-email a@example.com --site-url http://x.example.com` → prints `stopped: --site-url must start with https://`, exits 1, makes no call → AC-1
- [x] `bench books-register-site <site> --owner-email not-an-email --site-url https://x.example.com` → stops before any call → AC-1
- [x] With `config/books-runner.json` holding no `export_storage`, `books-register-site` still gets as far as calling the control site (it doesn't need the R2 keys) → AC-1

## Against the control site (once `register_site` and `get_state` exist)
- [x] Run `books-register-site` for a new site → the site's `site_config.json` gets `books_control_url` and a 64 hex `books_control_secret`, and the secret never appears in the output → AC-1
- [x] Run it again → prints `already registered, nothing changed`, and the secret is the same → AC-1
- [x] Run it for a site registered on another bench, or a `Removed` one → prints `answered HTTP 409`, and the config is unchanged → AC-1
- [x] Open /books/subscription as a Books Manager with `?checkout=returned` → the `get_state` body the control site stores carries `trial_ends_on`, `time_zone`, `language` and `company_name` → AC-21
- [ ] Make the control site answer `get_state` with any `issued_at` other than the request's → the page shows "Couldn't reach billing. Try again." and the state is unchanged → AC-21
- [ ] Make `create_checkout` answer a signed 409 with each of `plan_not_offered`, `already_subscribed`, `being_removed` → Subscribe shows that code's message, and no payment pending note appears → AC-5, AC-21
- [ ] The same 409 unsigned, or a signed 500 → "Couldn't reach billing. Try again." → AC-21, spec 0005 AC-16

## Value sourcing
- [ ] `trial_ends_on` sent equals the Subscription page's trial end date, in the site's time zone (set System Settings to `Africa/Dar_es_Salaam`, then to an empty zone, and compare) → AC-21
- [ ] `time_zone` and `language` follow System Settings; `company_name` follows Books Accounting Settings; an empty value is sent as `null` → AC-21
- [ ] `state.issued_at` must be the request's own `issued_at`, not just a fresh one: an answer one second off is refused → AC-2, AC-21
- [x] `register_site` sends `--owner-email` and `--site-url` exactly as given (trailing `/` removed), never `get_url()` → AC-1
- [x] Copy `frappe_books/tests/signing_vectors.json` into `rarebooks_control` and check its `signed_response` gives the same headers → task 3

## Commands (rarebooks_control)
- [x] `bench --site <control site> run-tests --app rarebooks_control` → 47 tests pass, including `UnitTestSigningVectors`, `IntegrationTestRegisterSite`, `IntegrationTestGetState`, `IntegrationTestCreateCheckout`, `IntegrationTestClickPesaPayment` and `IntegrationTestPush` → AC-1 to AC-3, AC-5 to AC-8, AC-10, AC-13, AC-17, task 3
- [x] `diff frappe_books/tests/signing_vectors.json rarebooks_control/tests/signing_vectors.json` → no difference → task 3

## Control site, by hand (a staging control site, ClickPesa calls against the real API once keys are set)
- [x] Sign a `register_site` body with a bench secret from `books_runner_secrets` → 200, a signed `{site, secret, issued_at}` whose `issued_at` is the request's own → AC-1
- [x] Send the same call with one byte changed, an unknown `bench`, or `issued_at` 6 minutes old → 401 with body `{}` → AC-1
- [x] Call `get_state` 31 times in a minute for one site → the 31st gets 429; a second site in the same minute still gets 200 → AC-22
- [x] `create_checkout` for ClickPesa → a `Created` Books Checkout with `order_reference` `RB` plus 8 digits; the answer's `go` link redirects (302) to the ClickPesa checkout and sets `books_checkout` (HttpOnly, Secure, SameSite=Lax, 24 hours) → AC-3, AC-6
- [x] Call `create_checkout` again within 24 hours → the same checkout, a new link; the old link now shows "This payment link has expired" with 410 → AC-3, AC-6
- [x] `create_checkout` with a `return_url` on another host, or `http://` → 400 → AC-5
- [x] Post a ClickPesa webhook with a wrong `checksum` → 401, no Books Payment Event → AC-7, AC-23
- [x] Post a valid one while the status query says `SUCCESS` with the right TZS amount → checkout `Paid`, the site gets ClickPesa, Yearly, `auto_renews` 0, the order reference, and a year of `paid_until`; the customer site unlocks within a minute → AC-7, AC-8, AC-13
- [x] Post the same webhook again → `{"result":"duplicate"}`, nothing changes → AC-7
- [ ] A status answer 1 TZS short, or in USD → checkout `Mismatch`, nothing pushed, one email to `books_ops_email` with the payer → AC-10
- [x] Stop the customer site and make a payment → the row shows `Failing`, `next_push_on` 1 minute later; start it again → the sweep pushes and the row returns to `Synced` → AC-13

## Value sourcing (control site)
- [x] `paid_until` for a payment on trial day 10 is `trial_ends_on` plus 1 year (the year starts the day after the trial) → AC-8
- [ ] A payment at 22:30 UTC on a site in `Africa/Dar_es_Salaam` counts as the next day; with an empty or bad `time_zone` it counts as the UTC day → AC-8
- [x] `plans` lists a `test_only` plan only for a site with `allow_test_plans`, and then instead of the real one → AC-2
- [x] The ClickPesa link amount is the plan's whole TZS amount, and the email sent is the row's `owner_email` → AC-3
- [ ] The push `issued_at` is the control site's clock at send time, ending `+00:00` → AC-13

## Acceptance-criteria coverage
- AC-1: the command steps and the first three control site steps · AC-2: the echo steps · AC-5: the refusal step · AC-21: the facts, echo and refusal steps · task 3: the golden vectors
- Control site: AC-1 and AC-2 by the signed call steps · AC-3 and AC-6 by the checkout and `go` steps · AC-5 by the `return_url` step · AC-7, AC-8, AC-10 by the webhook steps · AC-13 by the push steps · AC-22 (per site limit only) by the 31 call step
- Not yet covered: AC-4, AC-9, AC-11, AC-12, AC-14 to AC-20, AC-23 in full (later milestones); receipts (AC-19) and the push alerts (AC-13) come with Milestone 3

# Verify: billing control site, Milestone 2 (PayPal) · spec 0008 · updated 2026-11-19
_Steps derived from spec 0008 AC-4, AC-5, AC-9 to AC-11, AC-17 and AC-21. Covers build plan tasks 8 to 10. Task 11 (the sandbox run) is the "PayPal sandbox" section below._

## Commands (rarebooks_control)
- [ ] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_paypal` → 22 tests pass → AC-4, AC-5, AC-9, AC-10, AC-11, AC-17
- [ ] `bench --site <control site> run-tests --app rarebooks_control` → 71 tests pass → all of Milestones 1 and 2

## Commands (this repo)
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_clock` and `...test_subscription_control` → pass, including `test_a_paypal_subscription_made_in_the_trial_starts_the_day_after_it` and `test_a_paypal_subscription_waiting_to_start_refuses_checkout` → AC-21
- [ ] `cd frontend && yarn test` → passes, including the two spec 0008 AC-21 tests in `subscription.test.mjs` → AC-21
- [ ] `yarn test:ui tests/ui/subscription-lock.spec.ts` with `BOOKS_FILTER_TEST_BENCH` and `BOOKS_FILTER_TEST_SITE` set → 21 pass, including "a PayPal subscription waiting to start", desktop and phone → AC-21

## PayPal sandbox (build plan task 11, needs `paypal_mode` sandbox, client id, secret and `paypal_webhook_id` on a staging control site)
_Run 2026-11-19 from the dev container against the real sandbox (product `PROD-5ET01816UD968420X`, plans `P-0RM04323S95070247NL7IDCY` Monthly USD 9 and `P-5VE281007K242924ENL7IDDA` Yearly USD 90). Webhooks can't reach the container, so the unticked steps need the staging control site._
- [x] On a staging customer site on trial day 10 (company outside Tanzania), Subscribe Monthly → the `go` link lands on PayPal's sandbox approve page; the Books Checkout holds the subscription id → AC-4
  - 2026-11-19, from this container through `billing.new_checkout` (no staging customer site): CHK-00237 holds `I-HNVYD5E7LPM1` and PayPal's approve link
- [x] The subscription PayPal created has `start_time` = 00:00 the day after the trial in the site's zone, as UTC, and `custom_id` = the site → AC-4
  - Trial ends 2026-11-23 in Africa/Dar_es_Salaam: sent and stored `2026-11-23T21:00:00Z`, `custom_id` the site. **But** PayPal set `next_billing_time` to `2026-11-23T10:00:00Z`, which is 13:00 on the trial's last day in Dar es Salaam: PayPal bills on the UTC date of `start_time`, at its own time of day. So the first charge lands a day early for a zone east of UTC. Needs `/architect` (AC-4)
- [x] Approve it → PayPal sends `BILLING.SUBSCRIPTION.ACTIVATED`; the site row shows PayPal, Monthly, `auto_renews` 1, the subscription id, and no `paid_until`. Write down the status and `billing_info` PayPal shows before `start_time` (spec follow up) → AC-9
  - Applied through `check_paypal` (no webhook can reach this container). Before `start_time` PayPal shows `status` `ACTIVE`, no `last_payment`, `cycles_completed` 0, `outstanding_balance` 0.0. AC-9's "ACTIVE with no payment yet" rule holds; the spec follow up can close
- [ ] The customer site's Subscription page says "Your PayPal subscription starts on {day after the trial}.", shows no Subscribe, and on day 22 to 25 no prompt banner shows → AC-21
- [ ] Subscribe again from a second browser while the first is ACTIVE → "You already have an active PayPal subscription…" and no new checkout → AC-5
- [x] A lapsed site (no trial, `paid_until` in the past) subscribes → no `start_time`, PayPal charges at approval, and `PAYMENT.SALE.COMPLETED` sets `paid_until` to the next billing day minus 1, and the lock lifts within a minute → AC-4, AC-9, AC-13
  - `I-21LF4BU4PK4U`: no `start_time` sent; charged USD 9.0 at 2026-11-19T05:01:25Z; next billing 2026-12-18T10:00:00Z; `paid_until` 2026-12-17, pushed, one receipt; a second check changed nothing. Note: PayPal's next charge is 13:00 on 18 December in Dar es Salaam, so the site reads as `grace` for part of each renewal day until the payment is applied. The lock lift on a real customer site is still to check on staging
- [x] Cancel, then suspend and expire a sandbox subscription → `auto_renews` 0, `paid_until` unchanged, a push goes out each time → AC-9, AC-23
  - Cancel (`I-HNVYD5E7LPM1`) and suspend (`I-21LF4BU4PK4U`) at PayPal, then `check_paypal`: `auto_renews` 0, `paid_until` unchanged, one push each. Expiry not run: a sandbox subscription can't be made to expire on demand. The webhook delivery of these events is still to check on staging
- [ ] Post a PayPal webhook with a changed body or bad headers → 401, no Books Payment Event → AC-9, AC-23
- [ ] Refund the sandbox sale → event outcome `Refund`, one email to `books_ops_email`, the site unchanged → AC-10

## Value sourcing (PayPal)
- [ ] `start_time` is 12:00 Pacific on the day after the trial whatever the site zone: a trial ending 2026-11-23 sends `2026-11-24T20:00:00Z`, and PayPal's first `next_billing_time` falls on 24 November (about 10:00 UTC, 13:00 in Dar es Salaam) → AC-4 (amended 2026-11-19, build plan task 11a)
- [ ] `start_time` uses `paid_until` + 1 when it is later than the trial end, and is left out when that day is not later than the site's today in its zone → AC-4 (amended 2026-11-19)
- [ ] `paid_until` is the smaller of (next billing day in the site zone) and (payment day on the Pacific calendar plus one period, no minus 1): a charge at 2026-11-19T05:01Z with the next at 2026-12-18T10:00Z gives 18 December in Dar es Salaam, and the site reads `active`, not `grace`, on the morning of 18 December; a moved `next_billing_time` with the same `last_payment.time` grants no days → AC-9 (amended 2026-11-19)
- [ ] The money check uses the Books Plan found by `paypal_plan_id` (a disabled plan too): 8.99 USD or 9.00 EUR on a 9 USD plan is `Mismatch` with an ops email naming the subscriber → AC-9, AC-10
- [ ] Of two live subscriptions, the newer by PayPal `create_time` is cancelled, whichever event arrives first → AC-11
- [ ] `subscription_starts_on` is trial day 21 plus 1 in the site's zone, and is empty once `paid_until` is set, for ClickPesa, or with `auto_renews` off → AC-21

## Acceptance-criteria coverage
- AC-4: the checkout and `start_time` steps · AC-5: the `already_subscribed` step · AC-9: the activation, payment, cancel and verify steps · AC-10: the refund and mismatch steps · AC-11: the two subscription step · AC-17: the `test_paypal` command (unknown site, removed site, no checkout) · AC-21: the starts on steps · AC-23: the sandbox cancel, suspend, expiry and bad signature steps
- Not yet covered: the return page (AC-12) and receipts (AC-19) come with Milestone 3; the `Dropping` removal case check needs spec 0007's Books Removal Case on the control site (task 15)

# Verify: billing control site, Milestone 3 (reliability) · spec 0008 · updated 2026-11-19
_Steps derived from spec 0008 AC-10, AC-12, AC-13, AC-16, AC-18 and AC-19. Covers build plan tasks 12 to 15, except the `being_removed` refusal, which waits for spec 0007's Books Removal Case on the control site._

## Commands (rarebooks_control)
- [ ] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_reliability` → 18 tests pass → AC-10, AC-12, AC-13, AC-16, AC-18, AC-19
- [ ] `bench --site <control site> run-tests --app rarebooks_control` → 89 tests pass → Milestones 1 to 3
- [ ] `bench --site <control site> execute rarebooks_control.reconcile.hourly` and `...reconcile.daily` → run with no error; `scheduler_events` lists `push.sweep`, `reconcile.hourly` and `reconcile.daily` → AC-16, AC-18

## Control site, by hand (staging, with the scheduler on)
- [ ] Stop a customer site and make a payment → the row is `Failing`; leave it down past 6 hours (or set `failing_since` back) → exactly one email to `books_ops_email`, sent at once; later retries send none → AC-13
- [ ] Make a customer site answer 400 to the push → one email at once; the next hourly retry sends none → AC-13
- [ ] Start the customer site again → the sweep pushes, the row returns to `Synced` and the streak fields clear → AC-13
- [ ] Approve a PayPal sandbox subscription that charges at approval → the return page applies the payment before the webhook arrives, then 302s to the site's Subscription page; the webhook that follows changes nothing and sends no second receipt → AC-12, AC-19
- [ ] Pay a ClickPesa checkout and come back through its return → the `books_checkout` cookie finds the checkout, the site unlocks, the browser lands on the Subscription page → AC-12
- [ ] Open `/api/method/rarebooks_control.billing.returned` in a fresh browser → "You can close this page and go back to your books." with HTTP 200 → AC-12
- [ ] Turn the ClickPesa webhook off, pay, and wait for the hourly job → the payment is applied once; the webhook turned back on adds nothing → AC-16
- [ ] A ClickPesa checkout older than 24 hours turns `Expired`; a payment on it found by the hourly job still buys the year → AC-16
- [ ] A PayPal renewal with its webhook missed is applied by the daily job → AC-16
- [ ] A receipt for a site with `language` `sw` is in Swahili, for `fr` or empty in English; each names the company, plan, amount and currency, billing period, paid until date and reference, and says it is not a tax invoice → AC-19
- [ ] A Payment Event older than 90 days has an empty `raw_payload` after the daily job and keeps every other field → AC-18
- [ ] A day with a `BILLING.SUBSCRIPTION.PAYMENT.FAILED` event sends one queued digest to `books_ops_email`; a quiet day sends none → AC-10

## Value sourcing (Milestone 3)
- [ ] The 6 hour alert counts from `failing_since`, the start of the current streak, and `failing_alerted` keeps it to one per streak → AC-13
- [ ] The return page finds the checkout from PayPal's `subscription_id` first, else the cookie token's hash; an older cookie from a reused checkout finds nothing → AC-12
- [ ] Reconcile windows: ClickPesa `Created` or `Expired` under 48 hours, PayPal unpaid checkouts under 7 days plus every renewing PayPal site → AC-16
- [ ] The receipt language reads `sw`, `sw-TZ` and `sw_TZ` as Swahili, anything else as English; the amount is the provider's confirmed amount → AC-19
- [ ] `billing_state()` counts a `Created` checkout under 24 hours, or one `Paid` in the last 24 hours, as a recent checkout → spec 0007

## Acceptance-criteria coverage
- AC-10: the digest steps · AC-12: the return page steps · AC-13: the push alert and sweep steps · AC-16: the reconcile and expiry steps · AC-18: the retention step · AC-19: the receipt steps · spec 0007: the `billing_state` step
- Not yet covered: `being_removed` (AC-5), until spec 0007's Books Removal Case exists on the control site

# Verify: billing control site, task 11a (PayPal billing dates) · spec 0008 · updated 2026-11-19
_Steps derived from spec 0008 AC-4, AC-9 and AC-21 as amended 2026-11-19 (the sandbox run). Covers build plan task 11a._

## Commands (rarebooks_control)
- [ ] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_paypal` → 25 tests pass, including `UnitTestPayPalDates` (noon Pacific in winter and summer, the site's today gate, Monthly and Yearly, a lapsed renewal, no `next_billing_time`) → AC-4, AC-9
- [ ] `bench --site <control site> run-tests --app rarebooks_control` → 92 tests pass → Milestones 1 to 3 so far

## Commands (this repo)
- [ ] `...test_subscription_clock` and `...test_subscription_control` → pass, including `test_a_paypal_first_payment_missing_after_its_day_is_overdue` and the two day refusal test → AC-21
- [ ] `cd frontend && yarn test` → passes, including "after its start day a missing first PayPal payment gets its own note" → AC-21
- [ ] `yarn test:ui tests/ui/subscription-lock.spec.ts` with `BOOKS_FILTER_TEST_BENCH` and `BOOKS_FILTER_TEST_SITE` set → 23 pass, including "a missing first PayPal payment says so", desktop and phone → AC-21

## PayPal sandbox (the check task 11a asks for before the rule is relied on)
_2026-11-19: created from this container with `start_time` `2026-11-24T20:00:00Z` (a trial ending 23 November in Dar es Salaam). PayPal shows no `billing_info` until a buyer approves, so both wait for a sandbox buyer._
- [x] Approve Monthly `I-1X9M6LU63YXN` with a sandbox buyer, then read it → `next_billing_time` on 24 November (about 10:00 UTC), not the 23rd → AC-4
  - 2026-11-19, approved by you: `ACTIVE`, `next_billing_time` `2026-11-24T10:00:00Z`, 24 November (13:00 in Dar es Salaam). The noon Pacific rule holds for Monthly
- [x] Approve Yearly `I-D3EMHU4N44BH` the same way → `next_billing_time` on 24 November → AC-4
  - 2026-11-19, approved by you: `ACTIVE`, `next_billing_time` `2026-11-24T10:00:00Z`, 24 November (13:00 in Dar es Salaam). The noon Pacific rule holds for Yearly
- [ ] Let both charge on 24 November and check the charge day step below, then cancel them → housekeeping
- [ ] Once the first charge lands (or on a lapsed site charged at approval), `paid_until` is PayPal's next charge day itself, and the customer site reads `active`, not `grace`, on that morning → AC-9

## Value sourcing (task 11a)
- [ ] `start_time` ignores the site zone for the hour (always 12:00 Pacific) but uses it for the today gate: at 04:00 UTC on 19 November a trial ending the 18th sends none for Dar es Salaam and `2026-11-19T20:00:00Z` for New York → AC-4
- [ ] In summer the same rule gives 19:00 UTC (Pacific daylight time): a trial ending 30 June 2027 sends `2027-07-01T19:00:00Z` → AC-4
- [ ] The payment date is read in `America/Los_Angeles`, `next_billing_time` in the site zone: a charge at 2026-11-19T05:01Z (18 November Pacific) with the next at 2026-12-18T10:00Z gives 18 December → AC-9
- [ ] With trial day 22 as the charge day: on day 22 the note says "starts on" and no prompt banner shows; on day 23 to 25 the note says "Your first PayPal payment hasn't arrived…", the prompt banner shows, plans stay hidden and `start_checkout` refuses with that text; on day 26 the lock comes as normal → AC-21

## Acceptance-criteria coverage
- AC-4: the `start_time` unit tests, the sandbox approvals and the two Value sourcing `start_time` steps · AC-9: the `paid_until` unit tests, the integration tests on realistic 10:00 UTC charge times, the charge day step · AC-21: the clock, refusal, node and browser tests and the day 22 to 26 step
- Not yet covered: the charge day step waits for the 24 November sandbox charge


# Verify: billing control site, Milestone 4 (operator tools and hardening) · spec 0008 · updated 2026-11-19
_Steps derived from spec 0008 AC-13 to AC-15, AC-20 and AC-22. Covers build plan tasks 16 to 18. The `rotate_secret` instruction reaches a bench only once spec 0007's `report_sites` exists on the control site (its Milestone 4); until then `removal.rotation_instructions(bench)` is what it will send._

## Commands (rarebooks_control)
- [ ] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_operator_tools` → 19 tests pass → AC-13, AC-14, AC-15, AC-20, AC-22
- [ ] `bench --site <control site> run-tests --app rarebooks_control` → 92 tests pass → Milestones 1 to 4

## Commands (this repo)
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_rotation` → 4 tests pass → AC-15

## Control site, by hand (staging)
- [ ] As a Billing Manager, change `paid_until` on a Books Hosted Site and save → a Version shows the change, `push_status` goes Pending then Synced, the customer site shows the new date → AC-14, AC-13
- [ ] Set provider ClickPesa with billing period Monthly and save → refused with "A ClickPesa site is billed yearly…" → AC-14
- [ ] `provider_reference` is read only in the form; change `provider` and it becomes editable; saving a new reference without a provider change (through the API) is refused → AC-14
- [ ] Press Push now → "Push queued", a push reaches the customer site within a minute → AC-14
- [ ] Sign in as a Removal Manager or System Manager → no Push now or Rotate secret button; `POST /api/method/rarebooks_control.billing.push_now` answers 403; billing fields are read only → AC-20
- [ ] Press Rotate secret → the form says a rotation is waiting and the button is gone; no secret shows in the form, the Version list or the error log → AC-15
- [ ] While pending, a `get_state` signed with the old secret and one signed with the new secret both answer 200, each signed with the secret it came with → AC-15
- [ ] Run `bench books-removal-run` on the hosting bench (once `report_sites` sends `rotate_secret`) → the site's `site_config.json` holds the new `books_control_secret`, the log says "rotate_secret done" and never shows the secret, the row's `pending_secret` is empty, and a push lands (maybe after one retry in the first minute) → AC-15, AC-13
- [ ] After the swap, a call signed with the old secret gets 401; `secret_rotated` again gets 409 `no_rotation` → AC-15
- [ ] A fresh control site install: sign in as any desk user, Administrator included → asked to set up an authenticator app (System Settings shows two factor on, method OTP App) → AC-20
- [ ] Send 21 badly signed calls in one hour (any mix of `get_state` and webhooks) → exactly one email to `books_ops_email`; the 22nd and later send nothing more that hour → AC-22
- [ ] Desk shows a Billing workspace with Hosted Sites, Plans, Checkouts, Payment Events and Benches; the Hosted Site list shows and filters by Push Status → AC-14

## Value sourcing (Milestone 4)
- [ ] The pending secret is 64 hex characters from `secrets.token_hex(32)`, new on each rotation, and is sent only to the site's own bench → AC-15
- [ ] The failure count is per UTC hour: 20 failures at 10:59 and 20 at 11:01 send no email; 21 in one hour send one → AC-22
- [ ] A per bench limit, not per IP: 120 `secret_rotated` calls a minute from one bench pass, the 121st gets 429, another bench is unaffected → AC-22

## Acceptance-criteria coverage
- AC-13: the push after an edit and after the swap · AC-14: the edit, ClickPesa period, reference and Push now steps · AC-15: the rotation steps · AC-20: the role and two factor steps · AC-22: the signature alert and per bench limit steps
