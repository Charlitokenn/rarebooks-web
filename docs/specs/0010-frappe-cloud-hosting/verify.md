# Verify: Hosting on Frappe Cloud · spec 0010 · updated 2026-11-20
_Steps come from the spec 0010 acceptance criteria. `/check verify` runs them; `/test` locks the ones that last. Milestones 1 and 3 so far; add the drop (Milestone 2) and cleanup steps as you get to them._

## UI / manual
- [ ] On the control site, open Books Removal Settings: mode is `off`, Require Approval is on, Max Drops Per Day is 5. A System Manager can read it but not save it; a Removal Manager can save it. → AC-9
- [ ] Set mode to `live` with Books Bench Group empty, then save → refused with "Set the Books Bench Group before turning removal on." → AC-9
- [ ] With an open `dry_run` case that has an export, change mode from `dry_run` to `live` and save → the case is `Cancelled` and its R2 object is deleted; the next round sends the owner a real warning. → AC-9
- [ ] In the workspace, the Registry card links to Removal Settings and has no Hosting Benches link. → AC-9

## Commands
- [ ] `bench --site <customer> run-tests --app frappe_books --module frappe_books.tests.test_subscription_remote` → 16 tests OK → AC-2, AC-3, AC-4, AC-5
- [ ] `bench --site <control> run-tests --app rarebooks_control --module rarebooks_control.tests.test_removal` → 35 tests OK → AC-1, AC-3, AC-4, AC-9
- [ ] POST a signed `control_ping` to a hosted customer site → 200, the answer is signed with the site's secret, has no `message` wrapper, and echoes `issued_at`. → AC-2
- [ ] POST the same body with a wrong signature, an `issued_at` 6 minutes old, a naive `issued_at`, or another `site` → signed 401 echoing `issued_at`, with no detail. → AC-2
- [ ] On a locked customer site (`set_hosted_phase` locked), call `removal_report`, `control_ping`, `start_export`, `mark_export_sent` and `clear_removal` → all answer 200; `mark_export_sent` writes both hold fields and `clear_removal` empties them. → AC-5
- [ ] `start_export` with an `upload_url` that is `http://`, on another host, on `r2.cloudflarestorage.com.evil.com`, or with user info → signed 400, no job queued. → AC-3
- [ ] `start_export` with a good body → one job on the `long` queue with id `books-export:<case>:<attempt_id>`, timeout 7200, deduplicated. → AC-3
- [ ] Run `removal.export_job` with `expires_at` 1.5 hours away → no upload; `step_failed` with step `export` and error `link_expiring`. → AC-4
- [ ] Run the export job on a locked site against a real R2 presigned URL → one PUT, the object's size in R2 equals the `bytes` sent to `export_ready`, `sites/<site>/books-removal/<case>/` is gone afterwards, and the Books Subscription row is unchanged. → AC-4, AC-5
- [ ] Make the upload fail → `step_failed` error text holds no part of the upload URL's query string and no `books_control_secret`. → AC-4, AC-13
- [ ] Mode `off`: run `rarebooks_control.removal.run_round` → no job queued, `last_run_on` set. → AC-1
- [ ] Mode `live` with one site `config_status` Active, one Pending and one Removed → one job, `removal:<active site>`. → AC-1
- [ ] A site with `config_status` Failed and an open case whose billing state is paid → the round cancels the case without calling the site. → AC-1
- [ ] Four sites due for export in the same UTC hour → three get `start_export`, the fourth stays `Scheduled` with `attempts` 0. → AC-3
- [ ] `start_export` that can't connect → the case goes back to `Scheduled`, `attempts` 0, and the hour's slot is given back. → AC-3
- [ ] Back date `export_claimed_on` of an `Exporting` case by 6 hours 1 minute, then run the site → `attempts` 1, a new `attempt_id`, the old R2 object is not deleted. → AC-3
- [ ] `export_ready` with another `attempt_id`, or a size R2 doesn't show → 409, nothing deleted in R2. An R2 timeout during the HEAD → signed 503; the job's retry then gets 200. → AC-4
- [ ] The 61st `export_ready` or `step_failed` from one site within a minute → signed 429. → AC-17
- [ ] Dry run: a site taken through export and hold → owner emails go to `books_ops_email`, the export is still uploaded, and the site never gets `mark_export_sent` or `clear_removal`. → AC-1

## Value sourcing
- [ ] The round's sites come only from Books Hosted Site `status` Active and `config_status` Active: flip one to Pending and it gets no job. → AC-1
- [ ] Each call's secret is read fresh: change a site's `control_secret` between two calls of one job and the second call is signed with the new one. → AC-2
- [ ] `attempt_id` is a UUID4 and the key is `exports/<case>/<attempt_id>.zip`, both stored on the case before `start_export` goes out. → AC-3
- [ ] `upload_url` comes from `export_storage.upload_url(key, 21600)`, and `expires_at` is the claim time plus 6 hours in UTC with `+00:00`. → AC-3
- [ ] The run cap counts in Redis key `removal:exports:<YYYYMMDDHH>` (UTC): a new hour starts at 0. → AC-3
- [ ] "No report" for the stuck rule is `export_claimed_on` older than 6 hours while `Exporting`. → AC-3
- [ ] The job's start or refuse comes from `expires_at` minus now: 2 hours 1 minute left starts, 1 hour 59 minutes refuses. → AC-4
- [ ] The R2 host the site accepts ends in `.r2.cloudflarestorage.com`. → AC-3
- [ ] Free disk is measured on `sites/<site>/` against 2 times (database size plus `public/files` plus `private/files`): fake a small free value and the job reports `step_failed` with `DiskSpaceError`. → AC-4
- [ ] The 5,000,000,000 byte cap: lower it and the job reports `too_large` with no PUT. → AC-4
- [ ] The export job calls the control site at `books_control_url` from the site's config. → AC-4
- [ ] `export_ready`'s size check is the R2 HEAD `ContentLength` on the case's own `export_key`. → AC-4

## Milestone 3: registration and rotation (added 2026-11-20)

### UI / manual
- [ ] As a Billing Manager, open the Books Hosted Site list → a Register site button. As a Removal Manager or System Manager → no button, and calling `rarebooks_control.registry.register_site` gives 403. → AC-10
- [ ] Register site with a good Frappe Cloud site on `books_bench_group` → the row is `config_status` Pending with `config_sent_on` set; the site's Config tab on Frappe Cloud shows `books_control_url` and `books_control_secret`; no secret appears in the dialog, the answer or the Error Log. → AC-10
- [ ] Register site with an `http://` URL, a name Frappe Cloud doesn't know, a site on another bench group, the control site's own name, or an already registered site → a message, and no row and no Frappe Cloud write. → AC-10
- [ ] Within 5 minutes of registering → `config_status` Active, and the site gets its first push. → AC-11
- [ ] On an Active site, Rotate secret → `rotation_started_on` set, the form says a rotation is waiting, Frappe Cloud shows the new `books_control_secret`; within 5 minutes the rotation clears, and a call signed with the old secret gets 401. → AC-12
- [ ] On a Pending or Failed site → no Rotate secret button; Retry config is there. → AC-11, AC-12

### Commands
- [ ] `bench --site <control> run-tests --app rarebooks_control --module rarebooks_control.tests.test_registry` → 18 tests OK → AC-10, AC-11, AC-12, AC-13, AC-16
- [ ] Back date a Pending site's `config_sent_on` by 61 minutes while its config is wrong, run `rarebooks_control.registry.run_pings` twice → `config_status` Failed, one email to `books_ops_email`. → AC-11
- [ ] Retry config on that site → Pending, `config_sent_on` now, Frappe Cloud shows the config again. → AC-11
- [ ] With a site holding only the new secret during a rotation, run `rarebooks_control.site_calls.call_site("<site>", "removal_report")` → succeeds on the second try with `pending_secret`. → AC-12
- [ ] Back date `rotation_started_on` by 61 minutes on a rotation the site never took, run `rarebooks_control.registry.run_pings` twice → one email; both secrets still pass `get_state`. → AC-12
- [ ] A `get_state` from a Pending site, signed with its secret → signed 409 `{"refusal": "config_pending"}`; `push.push_site` sends nothing for it. → AC-11
- [ ] Set Books Removal Settings `last_run_on` 4 hours back, run `rarebooks_control.registry.run_pings` twice → one "hasn't run for 3 hours" email that day. → AC-16
- [ ] Two `rarebooks_control.registry.ping_rotation` calls once the site holds the new secret → the first swaps, the second does nothing. → AC-12

### Value sourcing
- [ ] The secret comes from `secrets.token_hex(32)`: 64 hex characters, never returned by `register_site`. → AC-10
- [ ] "Site exists and its bench group" comes from `press.api.site.get`'s `group`: change the fake or real group and registration is refused. → AC-10
- [ ] The config written is exactly `books_control_url` (from `books_control_public_url`) and `books_control_secret`; change `books_control_public_url`, run Retry config, and the site's Config tab shows the new URL. → AC-10, AC-11
- [ ] With `books_control_public_url` set to `http://…` → registration, Retry config and Rotate secret are refused. → AC-10
- [ ] "Pending over 1 hour" is measured from `config_sent_on`; "rotation pending over 1 hour" from `rotation_started_on`; 59 minutes sends nothing, 61 sends the alert. → AC-11, AC-12
- [ ] "Done" for registration and rotation is only a verified `control_ping` signed with the new secret and naming the site: a ping answered for another site name leaves it Pending. → AC-11, AC-12
- [ ] The stale run alert reads Books Removal Settings `last_run_on`: 2 hours 59 minutes sends nothing, 3 hours 1 minute sends it. → AC-16

## Acceptance criteria coverage
- Milestone 3: AC-10 register, refusals, config written · AC-11 ping, Failed, Retry config, gating · AC-12 rotate, both secrets, swap once, 401 retry, alert · AC-16 stale run alert (the digest lines come in Milestone 4)
- AC-1: round, off, skipped site cancel, dry run steps · AC-2: ping, 401 cases, fresh secret · AC-3: start_export checks, cap, slot back, stuck rule, key and link · AC-4: link expiry, upload scrub, 503 retry, 409, disk, size cap · AC-5: locked site calls and job · AC-9: settings steps · AC-13: error scrub · AC-17: per site limit
- Not yet in this file: AC-6, AC-7, AC-8 (Milestone 2 built, steps not added yet); AC-14, AC-15, the digest part of AC-16 (Milestone 4 and 5)

## Update 2026-11-20 · Milestones 2 and 4, and spec 0011
_Steps for the drop through Frappe Cloud, the cleanup and alerts, and spec 0011's archive mark and config rules. "0011 AC-n" is spec 0011._

### UI / manual
- [ ] On a staging site in `live` with approval on, take a case to `Holding` past `hold_until`, approve it, and run the round → one `removal_report` before the archive, the case is `Dropping` with `drop_started_on` and `archive_requested_on` set, and Frappe Cloud shows the site archiving. → AC-6, 0011 AC-1
- [ ] Next hourly run while Frappe Cloud still shows the archive running → the case stays `Dropping`, no second archive in Frappe Cloud's activity. Once it shows Archived → the case and the Books Hosted Site are `Removed`. → AC-7, 0011 AC-2
- [ ] The export email and the zip's `README.txt` say the hosting provider may keep backups for a limited time; neither says no other copy exists. → AC-8
- [ ] On a Books Hosted Site form, Retry config on an Active site → `config_status` Pending, and Active again within 5 minutes. Mid rotation → it stays Active and `rotation_started_on` restarts. → 0011 AC-4
- [ ] Rotate secret is missing on a Pending or Failed site, and calling `rarebooks_control.registry.rotate_secret` there gives "use Retry config instead". → 0011 AC-6
- [ ] Desk shows no Books Hosting Bench, and the Billing workspace links Removal Settings instead. → AC-9, AC-15

### Commands
- [ ] `bench --site <control> run-tests --app rarebooks_control` → 33 unit and 157 integration tests OK → AC-1 to AC-17, 0011 AC-1 to AC-11
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_remote` and `...test_subscription_removal` → OK → AC-2, AC-4, AC-5, AC-8
- [ ] `bench --help` on the customer bench lists no `books-` command, and `grep -rn "runner\|books_removal_mode\|books_runner_secrets" frappe_books rarebooks_control --include=*.py` finds nothing but the bench removal patch. → AC-15
- [ ] With the fake Frappe Cloud archive raising a read timeout → `archive_requested_on` set, `attempts` 0; with an HTTP 500 → no mark, `attempts` 1; three 500s → `Failed` and one ops email. → 0011 AC-1, AC-7
- [ ] Make every save of the mark fail (patch `removal._write_archive_mark`) → no mark and an Error Log "couldn't be marked"; set Frappe Cloud back to Active and run the job → every guard again, then one more archive. → 0011 AC-1, AC-2
- [ ] A `Dropping` case on a site with `config_status` Failed is still enqueued by `run_round` and goes `Removed` when Frappe Cloud shows Archived, with no call to the site. → 0011 AC-10
- [ ] A `Failed` case with `drop_started_on` set whose site Frappe Cloud shows Archived → `send_digest` makes it `Removed` and lists it as "archived after failing". → 0011 AC-11
- [ ] System Settings `dormant_days` 4 on the control site, run `run_round` twice → one email that day; after `after_install` it is 0. → AC-14
- [ ] The daily digest shows "Last removal run" and every site whose `config_status` isn't Active. → AC-16

### Value sourcing
- [ ] "The archive was requested" comes only from the case's `archive_requested_on`: with it set, Frappe Cloud showing Active still gives no call. → 0011 AC-2
- [ ] The time written is UTC (`signing.utc_now`): it matches the UTC clock, not the site's time zone. → 0011 AC-1
- [ ] "Unknown outcome" is the client's own split: a connect timeout or refused connection is a clear error, a read timeout or a reset after sending is unknown. → 0011 AC-1
- [ ] The bench group comes from Frappe Cloud's `group` compared exactly with `books_bench_group`: another group, an empty group, or an empty setting each stop the archive. → 0011 AC-3
- [ ] "Not the control site" comes from `frappe.local.site`: a registered site named like the control site is never archived. → AC-6
- [ ] The daily cap counts cases with `drop_started_on` on the current UTC date across all sites: six due sites with a cap of 5 start exactly 5 drops. → AC-6, AC-9
- [ ] The fresh report is a `removal_report` in the same job: `payment_pending` true, phase `active`, or `removal_on` after today each stop the archive. → AC-6
- [ ] Retry config's secret is `pending_secret` when set, else `control_secret`; its URL is `books_control_public_url`. → 0011 AC-4
- [ ] `get_state`'s refusal comes from the calling site's `config_status`: Pending or Failed gives the signed 409, and the signature failure counter doesn't move. → 0011 AC-5
- [ ] The digest's failed drops to reconcile are `Failed` cases with `drop_started_on` set; a `Failed` export case is never sent to Frappe Cloud. → 0011 AC-11

### Acceptance criteria coverage
- AC-6, AC-7, AC-8: drop, guards, poll, wording · AC-14: dormant days · AC-15: removed code · AC-16: digest lines · 0011 AC-1 to AC-11: archive mark, poll order, group, config rules, digest reconciliation
- Still owed: Milestone 5 (rollout on Frappe Cloud, AC-13 and AC-14 on the real site), which no local run can cover

