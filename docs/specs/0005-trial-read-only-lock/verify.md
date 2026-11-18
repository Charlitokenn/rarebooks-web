# Verify: trial and read only lock · spec 0005 · updated 2026-11-18
_Steps derived from spec 0005 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. Milestone 1 (server thread) only; later milestones append their steps here._

Setup for a managed site: add `"books_control_url": "https://control.example.com"` to the site's `site_config.json`. To lock it, move the clock back with `bench --site <site> console`: `from frappe_books.tests.subscription import lock_site; lock_site()`.

## UI / manual
- [ ] Locked managed site, as Administrator in /app: open a Books Party, change a field, save → refused, the value is unchanged after a reload → AC-5
- [ ] Locked managed site, in /books: create a Party → refused with "This site is read only. Subscribe to make changes again." → AC-5
- [ ] Locked managed site: open the dashboard, a list, a form, a report, the search palette, the print view, download a PDF and export a list as CSV → each works → AC-6
- [ ] Locked managed site: log out, log in again, request a password reset → each works → AC-7
- [ ] Remove `books_control_url` from site_config while the clock reads day 41 → saves work again, nothing is locked → AC-2

## Commands
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_lock` → OK (spike, every write path for Books Manager and Administrator: insert and rename give `SiteLockedError` 403, set_value, submit and delete give `InReadOnlyMode` 503, nothing written; reads and exports, allowlist, setup wizard, payment lifts the lock, unmanaged) → AC-2, AC-5, AC-6, AC-7, AC-12
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_clock` → OK (days 21, 22, 25, 26, 30; Dar es Salaam at 23:30 UTC on day 25 is day 26; empty time zone is UTC; paid lifecycle; unmanaged and exempt) → AC-1, AC-2, AC-3, AC-4, AC-13, AC-14, AC-18
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_jobs` → OK (a queued job writes nothing even after a commit, a scheduled job runs, the next unlocked job in the same worker writes) → AC-9
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_state` → OK (guard, read only roles, track changes, start trial once, apply_state rules, last_synced_on forward only) → AC-1, AC-12, AC-17
- [ ] `bench --site <site> migrate` on an existing site → `tabSingles` has `trial_started_on` for Books Subscription, in UTC, and a Version row → AC-1, AC-17
- [ ] `bench --site <site> execute frappe_books.subscription.apply_state --kwargs "{'state': {'paid_until': '<a year out>'}}"` on a locked site → the next save in /books works → AC-12
- [ ] As Administrator, `PUT /api/v2/document/Books Subscription/Books Subscription` with `{"exempt": 1}` → refused, `exempt` stays 0 → AC-17

## Value sourcing
- [ ] `trial_started_on`: on a site whose System Settings time zone is Asia/Kolkata, the stored value matches UTC now, not local time → AC-1
- [ ] Today and day 1: set the time zone to Africa/Dar_es_Salaam and check the lock starts at local midnight; clear it and check the day follows UTC → AC-18
- [ ] Managed or not: only the presence of `books_control_url` turns the clock on → AC-2
- [ ] Paid, exempt, auto renew: the phase follows Books Subscription `paid_until`, `exempt` and `auto_renews` (boundary tests in the clock module) → AC-13, AC-14
- [ ] `trial_ends_on`, `lock_starts_on`, `removal_on`: day 1 plus 20, 25 and 29 days; `removal_on` is empty once paid → AC-3, AC-8
- [ ] `grace_ends_on`: `paid_until` plus 7 days → AC-14
- [ ] `payment_pending`: true for a `checkout_started_on` 23 hours ago, false at 25 hours → AC-15
- [ ] `can_subscribe`: true only for System Manager and Books Manager → AC-10
- [ ] `offered_provider` and `offered_periods`: Tanzania gives ClickPesa Yearly, any other country PayPal Monthly and Yearly, no country gives none → AC-10

## Acceptance-criteria coverage
- AC-1 · test_subscription_clock, test_subscription_state, migrate step · AC-2 · unmanaged tests and manual step · AC-3, AC-4 · clock tests (the banner itself is milestone 2) · AC-5 · write path tests and manual steps (see the open point below) · AC-6 · reads test · AC-7 · login, allowlist and setup wizard tests · AC-9 · job tests · AC-12 · apply_state lifts the lock · AC-13, AC-14 · clock lifecycle tests · AC-17 · guard tests · AC-18 · time zone tests
- AC-8, AC-10, AC-11, AC-15, AC-16, AC-19: later milestones

## AC-5 error types (settled by /architect, 2026-11-18)
- [ ] On a locked site, an insert or rename answers `SiteLockedError` with 403; a save, submit, cancel or delete of an existing document answers `InReadOnlyMode` with 503; nothing is written in any case → AC-5

## Milestone 2: thin UI (added 2026-11-18)
Setup: a hosted site as above. Move the clock with `bench --site <site> console`: `from frappe_books.tests.subscription import store_facts; from frappe_books.subscription.clock import utc_now; from datetime import timedelta; store_facts(trial_started_on=utc_now() - timedelta(days=N - 1))` for day N. Web workers cache `site_config.json` for up to 60 seconds after you add `books_control_url`.

### UI / manual
- [ ] Day 5, as Administrator: no banner; the sidebar shows Subscription; the page says "Free trial", 17 days left, the trial end date (day 21) and the read only date (day 26) → AC-3
- [ ] Day 22, as Administrator: every /books screen shows "4 days left to subscribe before your books turn read only." with a Subscribe button that opens /books/subscription → AC-4
- [ ] Day 22, as a Books User: the same banner says "Ask your administrator to subscribe." and has no Subscribe button → AC-4
- [ ] Day 22: dismiss the banner, reload → it stays hidden; set `localStorage.books_subscription_banner_dismissed` to yesterday's date, reload → it shows again → AC-4
- [ ] Day 27: a red banner "Your books are read only. Subscribe by {day 30 date} to keep your data." with no dismiss button, even with today's date stored in the dismissal key → AC-8
- [ ] Day 27: create a Currency → a "Read only" dialog with the banner's text, and nothing saved (SiteLockedError, 403) → AC-5, AC-8
- [ ] Day 27: change and save an existing Party → the same dialog and text (InReadOnlyMode, 503) → AC-5, AC-8
- [ ] Lapsed (`paid_until` 10 days ago): banner and refused saves say "Your books are read only. Renew to make changes again." → AC-8
- [ ] Remove `books_control_url`: no banner, no Subscription item, and /books/subscription says "This site is not on a hosted plan." → AC-2
- [ ] Day 25 at 23:50 site time, open a form, wait past midnight, then save → the lock dialog shows and the banner turns red without a reload → AC-8

### Commands
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_status` → OK (boot carries the status, unmanaged boots as unmanaged, a Books User reads it, Guest is refused, a locked site still answers `get_subscription`) → AC-2, AC-3, AC-4, AC-7
- [ ] `cd frontend && node --test tests/subscription.test.mjs` → OK (banner text per day and phase, dismissal by site day, Subscribe only for managers, lapsed and payment pending texts; a 403 `SiteLockedError` and a 503 `InReadOnlyMode` in v1 and v2 give the lock notice, another 503 stays a plain error, a Guest 403 still goes to login, a stale status is fetched again) → AC-4, AC-5, AC-8
- [ ] `cd frontend && BOOKS_FILTER_TEST_BENCH=<bench> BOOKS_FILTER_TEST_SITE=<site> yarn test:ui tests/ui/subscription-lock.spec.ts` → passes (a locked site shows the banner, refuses a save with the lock text, and Subscribe opens the page) → AC-4, AC-5, AC-8

### Value sourcing
- [ ] Dismissal day: with the browser's clock set a day ahead of the site, a banner dismissed today still hides until the site's `today` changes → AC-4
- [ ] Days left: day 23 shows 3 (26 minus the day number) → AC-4
- [ ] Day 30 date in the lock text: equals the status dict's `removal_on`, shown in the user's date format → AC-8
- [ ] Banner after a refresh: on /books/subscription the status is fetched again, and the banner follows the shared `subscriptionStatus` ref → AC-12 (fully checked with the return refresh in milestone 3)

### Coverage
- AC-2 · unmanaged boot test, manual step · AC-3 · Subscription page step · AC-4 · node banner tests, manual steps · AC-5, AC-8 · node error mapping tests, Playwright test, manual steps

## Milestone 3: the control site contract (added 2026-11-18)
Setup: a hosted site with `books_control_url` and `books_control_secret` in `site_config.json`. Until the control site exists, a small stub that signs its answers with the same secret stands in (the Python tests use `ControlStub` in `frappe_books/tests/subscription.py`). Sign a push by hand with `from frappe_books.subscription.control import sign; sign(body, secret.encode())`.

### UI / manual
- [ ] Locked site, as Administrator on a Kenya company: the Subscription page lists PayPal Monthly and Yearly with their prices, each with a Subscribe button → AC-10
- [ ] Same, on a Tanzania company: only ClickPesa Yearly is listed → AC-10
- [ ] As a Books User: the page shows no plans → AC-10
- [ ] Click Subscribe on a plan → the browser goes to the stub's checkout URL; come back to /books → the lock notice adds "Payment pending. The lock lifts as soon as your payment is confirmed." and the lock stays → AC-10, AC-15
- [ ] Have the stub answer `paid_until` a year out, then open `/books/subscription?checkout=returned` → the red banner clears without a reload, the `?checkout` query is gone, and the next save works → AC-12
- [ ] Stop the stub (or make it wait 11 seconds), then open the page → "Couldn't reach billing. Try again." with a Retry button, the banner and lock unchanged; start the stub and press Retry → plans show → AC-16
- [ ] Stub down, press Subscribe → the same message under the plans → AC-16

### Commands
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_control` → OK (a signed push lifts the lock; a missing, wrong or truncated signature, another site, a 6 minute old, naive or bad `issued_at` each answer 401; an older replay and the same push again are `ignored`; a bad provider, period or date answers 400 and changes nothing; unknown keys are ignored; a newer `paid_until` clears `checkout_started_on`; the return pull applies state; plans per country and cached; a Books User gets no plans and 403 on checkout; checkout refusals for Tanzania Monthly, no country and an active plan; timeout, refused connection and a bad response signature give the Retry state) → AC-10, AC-11, AC-12, AC-15, AC-16
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_status` → still OK (`get_subscription` now also takes a POST) → AC-2, AC-3
- [ ] `curl -i -X POST <site>/api/method/frappe_books.subscription.receive_state -H 'Content-Type: application/json' -d '{}'` 61 times in a minute → the 61st is rate limited → AC-11
- [ ] Error Log after a signed push with `"provider": "Stripe"` → one "Books billing: receive_state refused a bad value" row (it may take a scheduler tick, the insert is deferred) → AC-11
- [ ] `cd frontend && node --test tests/subscription.test.mjs` → OK (the return refresh sends `refresh: true` and clears the banner, a plain refresh doesn't, checkout sends the period and returns the link, a refused checkout carries the server message, plan prices per period) → AC-10, AC-12

### Value sourcing
- [ ] Plans: the prices and labels shown equal the stub's `plans`, and a plan the stub lists for another provider is not shown → AC-10
- [ ] Plans cache: change the stub's prices, reload the page within the hour → old prices; after `bench --site <site> clear-cache` → new prices → AC-10
- [ ] `site` sent to the control site: the stub sees `frappe.local.site`, and a push whose `site` is another name is refused → AC-11
- [ ] `return_url`: the stub receives `<site url>/books/subscription?checkout=returned` (check behind a proxy that `host_name` gives the public URL) → AC-12
- [ ] `checkout_url`: the browser lands on exactly the stub's link → AC-10
- [ ] `paid_until`: stored exactly as the push gave it; a pull with an `issued_at` older than `last_synced_on` changes nothing → AC-11, AC-12
- [ ] Secret and URL: an `http://` control URL is refused (Retry state) unless `developer_mode` is on → security model

### Coverage
- AC-10 · checkout and plans tests, manual steps · AC-11 · push tests, rate limit and Error Log steps · AC-12 · pull test, node refresh test, return step · AC-15 · checkout marks payment pending · AC-16 · unreachable tests, Retry step
