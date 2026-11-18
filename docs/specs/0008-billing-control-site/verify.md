# Verify: billing control site · spec 0008 · updated 2026-11-18
_Steps derived from spec 0008 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. So far this covers only this repo's half of Milestone 1 (tasks 3 to 5). The control site steps come once `rarebooks_control` exists._

## Commands (this repo)
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_registration` → 6 tests pass → AC-1
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_control` → 43 tests pass, including `IntegrationTestSpec0008Contract` and `UnitTestSigningVectors` → AC-2, AC-5, AC-21, task 3
- [ ] `bench books-register-site <site> --owner-email a@example.com --site-url http://x.example.com` → prints `stopped: --site-url must start with https://`, exits 1, makes no call → AC-1
- [ ] `bench books-register-site <site> --owner-email not-an-email --site-url https://x.example.com` → stops before any call → AC-1
- [ ] With `config/books-runner.json` holding no `export_storage`, `books-register-site` still gets as far as calling the control site (it doesn't need the R2 keys) → AC-1

## Against the control site (once `register_site` and `get_state` exist)
- [ ] Run `books-register-site` for a new site → the site's `site_config.json` gets `books_control_url` and a 64 hex `books_control_secret`, and the secret never appears in the output → AC-1
- [ ] Run it again → prints `already registered, nothing changed`, and the secret is the same → AC-1
- [ ] Run it for a site registered on another bench, or a `Removed` one → prints `answered HTTP 409`, and the config is unchanged → AC-1
- [ ] Open /books/subscription as a Books Manager with `?checkout=returned` → the `get_state` body the control site stores carries `trial_ends_on`, `time_zone`, `language` and `company_name` → AC-21
- [ ] Make the control site answer `get_state` with any `issued_at` other than the request's → the page shows "Couldn't reach billing. Try again." and the state is unchanged → AC-21
- [ ] Make `create_checkout` answer a signed 409 with each of `plan_not_offered`, `already_subscribed`, `being_removed` → Subscribe shows that code's message, and no payment pending note appears → AC-5, AC-21
- [ ] The same 409 unsigned, or a signed 500 → "Couldn't reach billing. Try again." → AC-21, spec 0005 AC-16

## Value sourcing
- [ ] `trial_ends_on` sent equals the Subscription page's trial end date, in the site's time zone (set System Settings to `Africa/Dar_es_Salaam`, then to an empty zone, and compare) → AC-21
- [ ] `time_zone` and `language` follow System Settings; `company_name` follows Books Accounting Settings; an empty value is sent as `null` → AC-21
- [ ] `state.issued_at` must be the request's own `issued_at`, not just a fresh one: an answer one second off is refused → AC-2, AC-21
- [ ] `register_site` sends `--owner-email` and `--site-url` exactly as given (trailing `/` removed), never `get_url()` → AC-1
- [ ] Copy `frappe_books/tests/signing_vectors.json` into `rarebooks_control` and check its `signed_response` gives the same headers → task 3

## Acceptance-criteria coverage
- AC-1: the command steps and the first three control site steps · AC-2: the echo steps · AC-5: the refusal step · AC-21: the facts, echo and refusal steps · task 3: the golden vectors
- Not yet covered: AC-3, AC-4, AC-6 to AC-20, AC-22, AC-23 (control site, later milestones)
