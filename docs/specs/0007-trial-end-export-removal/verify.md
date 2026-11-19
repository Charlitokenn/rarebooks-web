# Verify: Trial end export and site removal · spec 0007 · updated 2026-11-18
_Steps derived from spec 0007 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._
_Covers Milestones 1 and 2 (customer site and runner, against stubs). The drop (Milestone 3) and the control site (Milestone 4) add their own steps when built._

Setup on a v16 test site (`<site>`), run from the bench folder:
- `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "locked"}'` for an unpaid trial on day 28.
- `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "lapsed"}'` for a site 10 days past `paid_until`.

## UI / manual
- [x] Locked trial (`locked` phase): open `/books` → banner reads "Your books are read only. Subscribe by {day 30} to keep this site. After that it is removed and a copy of your data is emailed to the owner." with the date in the System Settings date format → AC-2, AC-19
- [x] Lapsed (`lapsed` phase): banner reads "Your books are read only. Renew by {paid_until + 67 days} to keep this site. After that it is removed and a copy of your data is emailed to the owner." → AC-1, AC-2
- [x] Subscription page on a locked trial and on a lapsed site → a "Removal on" row with that same date; an open trial (`trial`, `prompt`) shows no such row → AC-2
- [x] Locked trial with the hold set: `bench --site <site> execute frappe_books.subscription.removal.mark_export_sent --kwargs '{"export_sent_on": "<now UTC ISO>", "removal_hold_until": "<now + 72h UTC ISO>"}'` → banner reads "Your books are read only. A copy of your data was emailed to the owner. This site will be removed after {date}." and a System Manager still sees Subscribe → AC-8
- [x] Same, with System Settings time zone `Africa/Dar_es_Salaam` and `removal_hold_until` at 22:30 UTC → the banner date is the next day (site time zone, not UTC) → AC-8 (Value sourcing: banner date)
- [x] All three texts at phone width (390 px): wrap without overflow, Subscribe button reachable → AC-19
- [x] Change the user language: the new texts and "Removal on" go through `t` (they show translated once a translation exists) → AC-19

## Commands
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_removal` → 38 tests OK → AC-1 to AC-3, AC-5 to AC-8, AC-11, AC-12, AC-14, AC-15, AC-18
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_clock` → OK, including the lapsed removal date and the hold date in Dar es Salaam → AC-1, AC-2, AC-8
- [x] `cd frontend && node --test tests/subscription.test.mjs` → all pass → AC-2, AC-8, AC-19
- [x] `bench books-removal-run` with no `books_removal_mode` in `sites/common_site_config.json` → one log line "books_removal_mode is off", exit 0, no network call → AC-3
- [x] Set `books_removal_mode` to `dry_run` with no `config/books-runner.json` → exit 1, "books-runner.json is missing" → AC-15
- [x] `chmod 644 config/books-runner.json` → exit 1, "must be owned by the bench user with mode 600"; `chmod 600` → it goes on → AC-15
- [x] `control_url` set to `http://...` → exit 1, "must start with https://" → AC-15
- [x] Valid secrets file, control URL pointing at nothing → exit 1, "stopped, nothing done", no site touched → AC-3, AC-15
- [x] `bench --site <site> execute frappe_books.subscription.removal.removal_status` on a locked trial → `kind: Trial`, `removal_on` = day 30, `today` the site date, `company_name` from Books Accounting Settings, `language` from System Settings → AC-1 (Value sourcing: removal_status fields)
- [x] Same on the lapsed site → `kind: Lapsed`, `removal_on` = `paid_until` + 67 days; on an exempt or active site → `removal_on` null → AC-1
- [x] Build an export by hand: `bench --site <site> console`, then `from frappe_books.subscription.removal import build_export; build_export("/tmp/books-export")` → `readable/` has a CSV per Frappe Books doctype (no `Books Subscription.csv`), child tables carry `parent`, `parenttype`, `parentfield`, `idx`, singles are `field,value`, `File.csv` lists attachments, `files/public` and `files/private` hold the uploads, `backup/database.sql.gz` exists, `README.txt` explains the restore, no `site_config.json` anywhere → AC-6
- [x] `head -c 3 "/tmp/books-export/readable/Books Sales Invoice.csv" | xxd` → `efbbbf` (byte order mark); open the CSV in Excel or LibreOffice → accents show correctly → AC-6
- [x] Run that export on a locked site → it succeeds, and Books Subscription's `modified` is unchanged → AC-18
- [ ] Restore `backup/database.sql.gz` onto a fresh v16 site (`bench --site <new> restore ...`) → it opens with the same records, and users can log in → AC-6 (README promise)
- [x] Push a newer `paid_until` while the hold is set: `bench --site <site> execute frappe_books.subscription.apply_state --kwargs "{'state': {'paid_until': '2027-12-31'}}"` → `export_sent_on` and `removal_hold_until` are empty → AC-11
- [x] Free disk check (Value sourcing): on a site whose database plus files is more than half the free disk, an `export` instruction fails with `DiskSpaceError` and a `step_failed` with step `export` → AC-12

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
- [x] `bench books-removal-run` in `dry_run` with a `drop` instruction from the stub → log "would drop {site}, case {case}", no `drop_starting` call, the site still opens → AC-14
- [ ] Mode check at that moment: change `books_removal_mode` to `off` while a run is between its report and its drop (or patch `read_mode`) → "books_removal_mode is now off", nothing dropped → AC-9
- [x] A `drop` for `../frappe-bench`, `.hidden`, `a/b.example.com` or case `archived` → "ignored an instruction", no folder touched → AC-15

### UI / manual
- [x] `bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "holding"}'`, open `/books` on desktop and at 390 px → the hold banner "Your books are read only. A copy of your data was emailed to the owner. This site will be removed after {date}." with no Dismiss, a Subscribe button in reach, and no sideways scroll; the Subscription page shows "Read only" and a "Removal on" row in the date format → AC-8, AC-19
- [x] `lapsed` phase → `get_subscription` has a `removal_on`, and the Subscription page shows it as "Removal on" (no longer null, as spec 0005 had it) → AC-2
- [x] `BOOKS_FILTER_TEST_BENCH=<bench> BOOKS_FILTER_TEST_SITE=<site> yarn test:ui tests/ui/subscription-lock.spec.ts` → all pass, the new "once the export is emailed the banner names the hold date" test included, on desktop and phone → AC-2, AC-8, AC-19

### Coverage
- AC-9 runner side (fresh local read with phase, date and `payment_pending`; mode read again; only a signed `proceed: true`): drop tests and the mode step
- AC-10 Frappe's in process drop, the case's archived path, root login from the secrets file, repeat safe: drop tests (mocked) and the three throwaway site steps (real)
- AC-14 dry run logs "would drop": drop tests and the dry run step
- AC-19 the hold text at phone width: the Playwright hold test
- Still Milestone 4: the control site half of AC-9 and AC-20, plus AC-4, AC-13, AC-16, AC-17, AC-21

## Milestone 4: control site removal side · added 2026-11-19
_Built in the `rarebooks_control` repo (`removal.py`, `removal_mail.py`, `export_storage.py`, Books Removal Case and Books Removal Warning). R2 is patched in the tests; the real bucket comes with Milestone 5._

### Commands
- [x] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_removal` → 40 tests OK → AC-1, AC-4, AC-5, AC-7 to AC-9, AC-11 to AC-15, AC-17, AC-20, AC-21
- [x] `bench --site <control site> run-tests --app rarebooks_control` → 132 tests OK, spec 0008's included → spec 0008 AC-5, AC-17
- [x] A runner call signed with a site secret, with an `issued_at` 6 minutes old, or naming an unknown bench → 401 with an empty signed body, and no case opened → AC-15
- [x] `report_sites` naming a site that the registry puts on another bench, plus one entry that is not a dict → no case for that site, an Error Log row for each, and the other sites in the same call still get their cases → AC-15
- [x] One runner run against a control site on a real test bench (`bench books-removal-run` in `dry_run`, a test site moved to day 26 with `set_hosted_phase`) → a Books Removal Case `Scheduled` in `dry_run`, one warning row with offset 4, and the email in the Email Queue goes to `books_ops_email` with the owner's address in its first line → AC-4, AC-14

### Value sourcing (one step each)
- [x] `removal_on`: report a later date while `Scheduled` → it moves; report an earlier date → it stays and an Error Log row says so; after `Exporting` no date moves → AC-1
- [ ] Which warning: first report on the removal day itself with no warning sent → only the 1 day warning, worded "very soon"; a lapsed site 14 days out → offset 14 → AC-4
- [ ] Owner address: change the site's `owner_email` on the site after the case opens → emails still go to the address copied at case open (the registry's, never the site's) → AC-4
- [ ] Email language: a site reporting `language: sw` → the warning reads in Swahili ("itaondolewa"); `sw_TZ` too; `fr` → English → AC-4
- [x] "A warning 24 hours ago": with the earliest warning 23 hours old → no `export`; at 25 hours → `export`, case `Exporting` with `export_claimed_on` → AC-5
- [x] Paid by the site's own report: the site reports phase `active` with no `removal_on` → the open case is `Cancelled` → AC-11
- [x] Paid by the control site: set `paid_until` to today on the registry while the site still reports `locked` → the case is `Cancelled`; a `paid_until` 8 days back (past grace) → it stays open → AC-11
- [x] Hold and link times: mark the export email `Sent` in Email Queue → `hold_until` is its sent time plus 72 hours and `link_expires_on` plus 30 days, and `mark_sent` carries both as `+00:00` timestamps → AC-7, AC-8
- [x] `delete_export_on`: after `export_ready` → upload day plus 90 days → AC-16
- [x] Download link: open `/api/method/rarebooks_control.removal.download?token=<token from the email>` → 302 to a presigned R2 URL, `download_count` goes up by one; a wrong token or one past `link_expires_on` → 404 "This link has expired. Contact support." → AC-7
- [ ] Daily cap: `books_removal_max_drops_per_day` 1 and two due cases → the first `drop_starting` says proceed, the second "the bench reached today's drop cap"; the next UTC day the second passes → AC-20
- [ ] Approval: with `books_removal_require_approval` on, a due case gets no `drop` until Approve; with it off in `site_config.json`, `drop` comes with no approval → AC-20
- [ ] Kill switch: tick `removal_paused` on the bench → no new `export` and every `drop_starting` says "removal is paused for the bench" → AC-20
- [x] R2 HEAD: delete the object in the bucket, or change its size → `drop_starting` refuses → AC-9
- [x] Billing gates: `exempt`, `auto_renews` or a Books Checkout `Created` in the last 24 hours on the registry → `drop_starting` refuses, the case stays `Holding` → AC-9
- [ ] Checkout freeze: `hold_until` 59 minutes away → the customer site's Subscribe shows the `being_removed` message; 2 hours away → checkout works → AC-11

### UI / manual (control site desk)
- [x] As a Removal Manager open a `Holding` case → Approve and Pause buttons; Pause asks for a reason; a `Paused` case shows Resume, a `Failed` case shows Retry → AC-13
- [x] As a System Manager or Billing Manager → no buttons, and calling `rarebooks_control.removal.approve_case` gives 403 → AC-13
- [x] Retry a case whose export email went to `Error` → a new export email with a new link, the case `Holding`, and the hold starts from the new sent time → AC-12, AC-13
- [x] The case's Version list shows each status change, approval and download; no role sees Delete → AC-17
- [x] Hourly job with a bench silent for 4 hours and a case `Dropping` for 3 hours → one email each to `books_ops_email`; run it again → no second email → AC-21
- [x] Daily job → one email listing unapproved `Holding` cases, and the digest of the day's removals and cancellations → AC-21

### Coverage
- AC-4, AC-5, AC-7, AC-8, AC-11, AC-12, AC-13, AC-14, AC-17, AC-20, AC-21: `test_removal.py` and the steps above
- AC-9 and AC-20 control site half: `TestDropGates` (every gate) and the value steps
- AC-15 control site half: `TestRunnerAuth`
- AC-16: `delete_export_on` here; the lifecycle rules are Milestone 5
- Not here: a real R2 bucket, Resend delivery and a full live cycle (Milestone 5, Rollout)

## Milestone 5: rollout · added 2026-11-19
_The helpers are in `frappe_books/subscription/rollout.py` (`bench books-removal-setup-bucket`, `bench books-removal-check`). Everything below runs on your Cloudflare account and the hosting server, so tick it there._

### Commands
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_rollout` → 19 tests OK → AC-3, AC-15, AC-16
- [ ] With an R2 admin token in `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`: `bench books-removal-setup-bucket --endpoint-url https://<account id>.r2.cloudflarestorage.com --bucket <bucket>` → two `ok` lines; run it again → the same two lines, and the R2 dashboard shows each rule once → AC-16
- [ ] In the R2 dashboard: the bucket is private (no public access, no r2.dev URL), and its lifecycle shows `exports/` deleted after 90 days and multipart aborted after 1 day → AC-16
- [ ] The runner's token can upload but not change the lifecycle (`bench books-removal-setup-bucket` with the runner's keys → `FAIL ... AccessDenied`); the control site's token can HEAD and delete → AC-7, AC-9
- [ ] On the host, as the bench user: `bench books-removal-check` → every line `ok`, with the cron line it found echoed → AC-3, AC-15
- [ ] `bench books-removal-check --upload-probe` → `ok R2 upload: wrote exports/preflight/...`, and the object shows in the bucket → AC-7, AC-16
- [ ] `chmod 644 config/books-runner.json` then `bench books-removal-check` → `FAIL secrets file`; set it back to 600 → AC-15

### Dry run cycle on the real bench
- [ ] Set `books_removal_mode` to `dry_run`, take a test site to day 26 with `set_hosted_phase`, wait for the next hourly run → a Books Removal Case `Scheduled` in `dry_run`, and the warning arrives in the `books_ops_email` inbox with the owner's address in its first line → AC-4, AC-14
- [ ] Move the test site to day 30 → the export zip reaches R2 under `exports/<case>/`, the ops inbox gets the download link, the link downloads the zip, and the site's `export_sent_on` stays empty → AC-7, AC-14
- [ ] After the 72 hour hold → `logs/books-removal.log` shows "would drop {site}" each hour, the site still opens, the case stays `Holding` → AC-14
- [ ] `logs/books-removal.log` holds no runner secret, R2 key, root password or download token → AC-15

### Going live
- [ ] Before the switch, `books_removal_require_approval` is on and `books_removal_max_drops_per_day` is set low on the control site → AC-20
- [ ] Set `books_removal_mode` to `live` → the first live report cancels every open `dry_run` case of the bench and deletes its exports → AC-14
- [ ] The first real case due for its drop waits for a Removal Manager's Approve, and the daily digest lists it → AC-20, AC-21

### Coverage
- AC-16 lifecycle rules: `UnitTestLifecycleRules` and the bucket steps above
- AC-3 cron line and AC-15 host checks: `UnitTestPreflight`, `UnitTestCronLine` and the host steps
- AC-14 and AC-20 on the real bench: the dry run and going live steps
