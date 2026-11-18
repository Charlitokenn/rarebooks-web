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
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_lock` → OK (spike, every write path for Books Manager and Administrator, reads and exports, allowlist, setup wizard, payment lifts the lock, unmanaged) → AC-2, AC-5, AC-6, AC-7, AC-12
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

## Open point for /architect
- AC-5 says a document save, submit, cancel or delete is refused with `SiteLockedError` (403). On Frappe 16 these take a row lock (`SELECT ... FOR UPDATE`) before any `before_*` hook runs, and MariaDB refuses that inside the read only transaction. So they come back as `InReadOnlyMode` (HTTP 503). Insert and rename do get `SiteLockedError` (403). Nothing is written in any case, and AC-8 already maps both types to the lock notice.
