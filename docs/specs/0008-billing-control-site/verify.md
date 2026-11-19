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
- [ ] On a staging customer site on trial day 10 (company outside Tanzania), Subscribe Monthly → the `go` link lands on PayPal's sandbox approve page; the Books Checkout holds the subscription id → AC-4
- [ ] The subscription PayPal created has `start_time` = 00:00 the day after the trial in the site's zone, as UTC, and `custom_id` = the site → AC-4
- [ ] Approve it → PayPal sends `BILLING.SUBSCRIPTION.ACTIVATED`; the site row shows PayPal, Monthly, `auto_renews` 1, the subscription id, and no `paid_until`. Write down the status and `billing_info` PayPal shows before `start_time` (spec follow up) → AC-9
- [ ] The customer site's Subscription page says "Your PayPal subscription starts on {day after the trial}.", shows no Subscribe, and on day 22 to 25 no prompt banner shows → AC-21
- [ ] Subscribe again from a second browser while the first is ACTIVE → "You already have an active PayPal subscription…" and no new checkout → AC-5
- [ ] A lapsed site (no trial, `paid_until` in the past) subscribes → no `start_time`, PayPal charges at approval, and `PAYMENT.SALE.COMPLETED` sets `paid_until` to the next billing day minus 1, and the lock lifts within a minute → AC-4, AC-9, AC-13
- [ ] Cancel, then suspend and expire a sandbox subscription → `auto_renews` 0, `paid_until` unchanged, a push goes out each time → AC-9, AC-23
- [ ] Post a PayPal webhook with a changed body or bad headers → 401, no Books Payment Event → AC-9, AC-23
- [ ] Refund the sandbox sale → event outcome `Refund`, one email to `books_ops_email`, the site unchanged → AC-10

## Value sourcing (PayPal)
- [ ] `start_time` follows the site's `time_zone`: Dar es Salaam gives 21:00Z the day before; an empty or bad zone gives 00:00Z → AC-4
- [ ] `start_time` uses `paid_until` + 1 when it is later than the trial end, and is left out when the day is not more than 5 minutes ahead → AC-4
- [ ] `paid_until` is the smaller of (next billing day in the site zone minus 1) and (payment day plus one period minus 1); a moved `next_billing_time` with the same `last_payment.time` grants no days → AC-9
- [ ] The money check uses the Books Plan found by `paypal_plan_id` (a disabled plan too): 8.99 USD or 9.00 EUR on a 9 USD plan is `Mismatch` with an ops email naming the subscriber → AC-9, AC-10
- [ ] Of two live subscriptions, the newer by PayPal `create_time` is cancelled, whichever event arrives first → AC-11
- [ ] `subscription_starts_on` is trial day 21 plus 1 in the site's zone, and is empty once `paid_until` is set, for ClickPesa, or with `auto_renews` off → AC-21

## Acceptance-criteria coverage
- AC-4: the checkout and `start_time` steps · AC-5: the `already_subscribed` step · AC-9: the activation, payment, cancel and verify steps · AC-10: the refund and mismatch steps · AC-11: the two subscription step · AC-17: the `test_paypal` command (unknown site, removed site, no checkout) · AC-21: the starts on steps · AC-23: the sandbox cancel, suspend, expiry and bad signature steps
- Not yet covered: the return page (AC-12) and receipts (AC-19) come with Milestone 3; the `Dropping` removal case check needs spec 0007's Books Removal Case on the control site (task 15)
