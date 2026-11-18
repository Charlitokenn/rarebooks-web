# Verify: Lock hardening · spec 0007 · updated 2026-11-18
_Steps derived from spec 0007 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

Setup: a hosted site (`bench --site <site> set-config books_control_url https://control.example.com`), locked with `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "locked"}'`. Put it back with `bench --site <site> execute frappe_books.tests.subscription.unlock_self_hosted_site`.

## UI / manual
- [ ] On a site that turned read only overnight (the browser still has the open status: open /books on day 25, then run `set_hosted_phase` with `locked` without reloading), save a record → the first notice already reads "Your books are read only. Subscribe by <date> to keep your data." and the banner shows → AC-6
- [ ] Same, but make the status call fail (block `get_subscription` in the browser's dev tools) → the notice reads "This site is read only. Subscribe to make changes again." → AC-6
- [ ] On an open site, turn on Frappe's maintenance mode with reads allowed (`bench --site <site> set-config maintenance_mode 1` and `allow_reads_during_maintenance 1`), then edit and save a record → "This site is being updated and is read only for a few minutes. Try again shortly.", never "Subscribe" → AC-5
- [ ] Same with reads not allowed (`allow_reads_during_maintenance 0`) → every request answers 503 and the generic error shows (out of scope, check nothing worse happens) → AC-5
- [ ] On the Subscription page with plans shown, trigger a refused save on another tab → coming back, the plans and any billing message are still there → AC-7
- [ ] Two refused saves at once (save two forms quickly) → the Network tab shows one `get_subscription` call with `with_plans: false` → AC-6, AC-7
- [ ] Repeat the notice checks on a phone width (375px) → the text fits and the dialog stays in view → AC-5, AC-6

## Commands
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_control` → OK, including `test_two_pushes_at_once_both_answer_and_the_newer_wins`, `test_a_checkout_during_a_push_waits_and_both_save` → AC-1, AC-3
- [ ] Same module: `test_a_bad_value_still_answers_400_and_logs_once`, `test_any_other_push_failure_is_a_500_that_changes_nothing`, `test_any_other_pull_failure_is_not_logged_as_a_bad_value`, `test_a_bad_pulled_value_logs_and_gives_the_retry_state` → AC-2
- [ ] Same module: `test_a_checkout_link_must_be_https_outside_developer_mode` (http, `javascript:`, no scheme) and `test_developer_mode_accepts_a_plain_http_checkout_link` → AC-3
- [ ] Same module: `test_a_status_only_call_never_pulls` (Books Manager, Books User, Administrator, with `refresh` on) → AC-7
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_clock` → OK, including `test_an_unknown_time_zone_falls_back_to_utc` ("Mars/Olympus", "America", "../etc/passwd" give UTC days) and `test_an_unknown_time_zone_never_raises` → AC-4 (clock part)
- [ ] Leave the site hosted with `auto_renews = 1` (`set-config books_control_url ...` and `execute frappe_books.tests.subscription.store_facts --kwargs '{"auto_renews": 1}'`), then run `test_is_locked_reads_nothing_on_an_unmanaged_site` and `test_a_bad_value_answers_400_and_changes_nothing` → both pass → AC-8
- [ ] `bench --site <site> execute frappe_books.tests.subscription.clear_trial_start` → `trial_started_on` is empty and the status reads `lock_reason: no_trial_start`; `execute frappe_books.subscription.start_trial` puts it back → AC-8
- [ ] `cd frontend && node --test tests/subscription.test.mjs` → OK, including the maintenance, awaited status, fallback, shared status call and kept plans tests → AC-5, AC-6, AC-7
- [ ] `cd frontend && yarn lint && yarn typecheck` → clean

## Value sourcing
- [ ] Which push wins: two pushes with `issued_at` 30 and 10 seconds ago, sent together in either order → the stored facts and `last_synced_on` are the newer one's → AC-1
- [ ] 400 vs 500: a bad provider → 400; a database error during the save → 500, no "bad value" row, no change → AC-2
- [ ] Checkout link: `https://` always accepted; `http://` accepted only with `developer_mode` on → AC-3
- [ ] The zone: an empty `time_zone` and an unknown one both give UTC days; a real zone (Africa/Dar_es_Salaam) moves the lock to local midnight → AC-4
- [ ] Bad zone log: the Redis claim on `books_subscription_bad_time_zone` is taken once an hour (see the open AC-4 note below for the Error Log row) → AC-4
- [ ] Lock notice: `InReadOnlyMode` with a fresh `locked: false` → maintenance text; with a fresh `locked: true` → the phase's text; a failed status call → the stored status's text → AC-5, AC-6
- [ ] Plans after a status only fetch: kept from before → AC-7
- [ ] Maintenance text: translated through `t` (switch the user's language and check it is looked up) → AC-5
- [ ] `get_subscription` plans: absent with `with_plans: false` for every role; present for a manager otherwise → AC-7

## Open: AC-4, owed to /architect
Frappe's own `now_datetime()` builds `ZoneInfo(System Settings time_zone)` and raises on an unknown name, so with a bad zone Frappe itself fails every timestamped write (login's session, document saves, the Error Log row). This app's clock falls back to UTC and never raises, but "every request keeps working (login included)" and "one Error Log row an hour" can't be met from this app. Not verifiable until the spec is updated.

## Acceptance-criteria coverage
- AC-1 … concurrent push test, value sourcing "which push wins"
- AC-2 … the four split tests, value sourcing "400 vs 500"
- AC-3 … checkout during a push, the https link tests
- AC-4 … clock fallback tests only; login and the Error Log row are open (above)
- AC-5 … maintenance node test, the two maintenance manual steps
- AC-6 … awaited status, fallback and shared call node tests, the first refusal manual steps
- AC-7 … `test_a_status_only_call_never_pulls`, kept plans node test
- AC-8 … the isolation run, `clear_trial_start`, spec 0005 verify.md Milestone 6 setup line
