# Verify: Trial end export and site removal · spec 0007 · updated 2026-11-18
_Steps derived from spec 0007 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._
_Covers Milestones 1 and 2 (customer site and runner, against stubs). The drop (Milestone 3) and the control site (Milestone 4) add their own steps when built._

Setup on a v16 test site (`<site>`), run from the bench folder:
- `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "locked"}'` for an unpaid trial on day 28.
- `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "lapsed"}'` for a site 10 days past `paid_until`.

## UI / manual
- [x] Locked trial (`locked` phase): open `/books` → banner reads "Your books are read only. Subscribe by {day 30} to keep this site. After that it is removed and a copy of your data is emailed to the owner." with the date in the System Settings date format → AC-2, AC-19
- [x] Lapsed (`lapsed` phase): banner reads "Your books are read only. Renew by {paid_until + 67 days} to keep this site. After that it is removed and a copy of your data is emailed to the owner." → AC-1, AC-2
- [ ] Subscription page on a locked trial and on a lapsed site → a "Removal on" row with that same date; an open trial (`trial`, `prompt`) shows no such row → AC-2
- [ ] Locked trial with the hold set: `bench --site <site> execute frappe_books.subscription.removal.mark_export_sent --kwargs '{"export_sent_on": "<now UTC ISO>", "removal_hold_until": "<now + 72h UTC ISO>"}'` → banner reads "Your books are read only. A copy of your data was emailed to the owner. This site will be removed after {date}." and a System Manager still sees Subscribe → AC-8
- [ ] Same, with System Settings time zone `Africa/Dar_es_Salaam` and `removal_hold_until` at 22:30 UTC → the banner date is the next day (site time zone, not UTC) → AC-8 (Value sourcing: banner date)
- [x] All three texts at phone width (390 px): wrap without overflow, Subscribe button reachable → AC-19
- [ ] Change the user language: the new texts and "Removal on" go through `t` (they show translated once a translation exists) → AC-19

## Commands
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_removal` → 38 tests OK → AC-1 to AC-3, AC-5 to AC-8, AC-11, AC-12, AC-14, AC-15, AC-18
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_clock` → OK, including the lapsed removal date and the hold date in Dar es Salaam → AC-1, AC-2, AC-8
- [x] `cd frontend && node --test tests/subscription.test.mjs` → all pass → AC-2, AC-8, AC-19
- [x] `bench books-removal-run` with no `books_removal_mode` in `sites/common_site_config.json` → one log line "books_removal_mode is off", exit 0, no network call → AC-3
- [x] Set `books_removal_mode` to `dry_run` with no `config/books-runner.json` → exit 1, "books-runner.json is missing" → AC-15
- [x] `chmod 644 config/books-runner.json` → exit 1, "must be owned by the bench user with mode 600"; `chmod 600` → it goes on → AC-15
- [x] `control_url` set to `http://...` → exit 1, "must start with https://" → AC-15
- [x] Valid secrets file, control URL pointing at nothing → exit 1, "stopped, nothing done", no site touched → AC-3, AC-15
- [ ] `bench --site <site> execute frappe_books.subscription.removal.removal_status` on a locked trial → `kind: Trial`, `removal_on` = day 30, `today` the site date, `company_name` from Books Accounting Settings, `language` from System Settings → AC-1 (Value sourcing: removal_status fields)
- [ ] Same on the lapsed site → `kind: Lapsed`, `removal_on` = `paid_until` + 67 days; on an exempt or active site → `removal_on` null → AC-1
- [x] Build an export by hand: `bench --site <site> console`, then `from frappe_books.subscription.removal import build_export; build_export("/tmp/books-export")` → `readable/` has a CSV per Frappe Books doctype (no `Books Subscription.csv`), child tables carry `parent`, `parenttype`, `parentfield`, `idx`, singles are `field,value`, `File.csv` lists attachments, `files/public` and `files/private` hold the uploads, `backup/database.sql.gz` exists, `README.txt` explains the restore, no `site_config.json` anywhere → AC-6
- [ ] `head -c 3 "/tmp/books-export/readable/Books Sales Invoice.csv" | xxd` → `efbbbf` (byte order mark); open the CSV in Excel or LibreOffice → accents show correctly → AC-6
- [x] Run that export on a locked site → it succeeds, and Books Subscription's `modified` is unchanged → AC-18
- [ ] Restore `backup/database.sql.gz` onto a fresh v16 site (`bench --site <new> restore ...`) → it opens with the same records, and users can log in → AC-6 (README promise)
- [x] Push a newer `paid_until` while the hold is set: `bench --site <site> execute frappe_books.subscription.apply_state --kwargs "{'state': {'paid_until': '2027-12-31'}}"` → `export_sent_on` and `removal_hold_until` are empty → AC-11
- [ ] Free disk check (Value sourcing): on a site whose database plus files is more than half the free disk, an `export` instruction fails with `DiskSpaceError` and a `step_failed` with step `export` → AC-12

## Acceptance-criteria coverage
- AC-1 removal dates: clock tests, `removal_status` commands, banners
- AC-2 new texts and "Removal on" row: UI steps 1 to 3, Node tests
- AC-3 mode switch, chunks, one call with no sites, control site down: runner commands and tests
- AC-5 export only when told: the runner acts only on a signed `export` instruction (the conditions themselves are the control site's, Milestone 4)
- AC-6 zip layout: manual export, BOM check, restore
- AC-7 key, size, SHA256 reported: runner tests (the download link is Milestone 4)
- AC-8 hold fields and hold banner: UI steps 4 and 5, `mark_sent` tests
- AC-11 clear on payment: `apply_state` command, `clear` tests
- AC-12 `step_failed` scrubbed, deferred: runner tests, disk check step
- AC-14 dry run writes no site fields: runner tests
- AC-15 secrets file, https, signed answers with echo, own sites only: runner commands and tests
- AC-18 export changes nothing: locked site export step
- AC-19 phone width, translation, date formatter: UI steps 6 and 7 (the Playwright hold test is Milestone 3, task 9)
- AC-4, AC-9, AC-10, AC-13, AC-16, AC-17, AC-20, AC-21: not built yet (Milestones 3 and 4)

## Milestone 3: the drop, behind dry run · added 2026-11-18
_The runner side of the drop. The control site's `drop_starting` gates (approval, cap, kill switch, R2 HEAD, billing state) are Milestone 4; here the stub answers for them._

### Commands
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_removal` → 53 tests OK, including the 15 in `IntegrationTestRemovalDrop` → AC-9, AC-10, AC-12, AC-14, AC-15
- [ ] A real drop on a throwaway site (Frappe's drop is mocked in the tests): `bench new-site drop-test.localhost --install-app frappe_books`, set its `books_control_url`, lock it past day 30 (`set_hosted_phase` with `locked`, then move `trial_started_on` back 40 days), put `root_login` and `root_password` in `config/books-runner.json`, then call `Runner(...).do_drop({"site": "drop-test.localhost", "case": "RC-99999", "action": "drop"})` from `bench console` with `drop_starting` patched to answer `proceed: true` → the database and its users are gone (`SHOW DATABASES`, `SELECT user FROM mysql.user`), `sites/drop-test.localhost` is gone, `books-removal/archived/RC-99999` doesn't exist, and nothing else under `archived/` changed → AC-10
- [ ] Repeat that `do_drop` call → it goes straight to `drop_done` ("already gone"), with no error → AC-10
- [ ] Repeat safe after a crash: on a second throwaway site, drop only its database by hand (`DROP DATABASE`), keep the folder, then `do_drop` → the database user and folder are removed and `drop_done` is called ("finished an earlier drop") → AC-10
- [ ] `bench books-removal-run` in `dry_run` with a `drop` instruction from the stub → log "would drop {site}, case {case}", no `drop_starting` call, the site still opens → AC-14
- [ ] Mode check at that moment: change `books_removal_mode` to `off` while a run is between its report and its drop (or patch `read_mode`) → "books_removal_mode is now off", nothing dropped → AC-9
- [ ] A `drop` for `../frappe-bench`, `.hidden`, `a/b.example.com` or case `archived` → "ignored an instruction", no folder touched → AC-15

### UI / manual
- [x] `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "holding"}'`, open `/books` on desktop and at 390 px → the hold banner "Your books are read only. A copy of your data was emailed to the owner. This site will be removed after {date}." with no Dismiss, a Subscribe button in reach, and no sideways scroll; the Subscription page shows "Read only" and a "Removal on" row in the date format → AC-8, AC-19
- [x] `lapsed` phase → `get_subscription` has a `removal_on`, and the Subscription page shows it as "Removal on" (no longer null, as spec 0005 had it) → AC-2
- [ ] `BOOKS_FILTER_TEST_BENCH=<bench> BOOKS_FILTER_TEST_SITE=<site> yarn test:ui tests/ui/subscription-lock.spec.ts` → all pass, the new "once the export is emailed the banner names the hold date" test included, on desktop and phone → AC-2, AC-8, AC-19

### Coverage
- AC-9 runner side (fresh local read with phase, date and `payment_pending`; mode read again; only a signed `proceed: true`): drop tests and the mode step
- AC-10 Frappe's in process drop, the case's archived path, root login from the secrets file, repeat safe: drop tests (mocked) and the three throwaway site steps (real)
- AC-14 dry run logs "would drop": drop tests and the dry run step
- AC-19 the hold text at phone width: the Playwright hold test
- Still Milestone 4: the control site half of AC-9 and AC-20, plus AC-4, AC-13, AC-16, AC-17, AC-21
