# 0007. Trial end export and site removal

**Date**: 2026-11-18 (cross checked the same day: secrets file, dry run isolation, signed answers, payment race, drop safety gates)
**Status**: In Progress

> **Amended by [spec 0010](../0010-frappe-cloud-hosting/index.md) (2026-11-20, hosting on Frappe Cloud).** The runner (`bench books-removal-run`, host cron, `books-runner.json`, the root login), Books Hosting Bench and every `bench` field are replaced: the control site now drives the round over signed HTTPS, sites build their export in a background job and upload through a presigned URL, and the drop is a Frappe Cloud API archive. Read 0010 instead of this spec for AC-3, AC-10, AC-15, AC-18, the mode and gate settings of AC-14 and AC-20, the "bench silent" alert of AC-21, the runner flow, the runner API rows and Milestone 5. Every other rule here still holds.

Decision history: [rationale.md](rationale.md).

## Summary

A hosted site that never pays is removed after day 30, and a site that paid once and then lapsed is removed 60 days after its grace ends. Before that, the owner gets warning emails. On the removal date they get a download link to a zip of all their records (readable CSV files, their uploaded files, and a database backup they can restore on their own Frappe bench). The site is dropped at least 72 hours after that email is sent. At first, each drop also waits for your approval. A site can't remove itself, so a small bench command on the hosting server (the runner) does the work, and your control site decides when. Paying before the drop cancels everything, and any failure or doubt stops the removal and alerts you instead of deleting anyway.

## Requirements

**User stories**:
- As a site owner who didn't subscribe, I want clear warnings with the date, and a full copy of my books, so losing the site never means losing my records.
- As a site owner who decides to pay late, I want paying before the drop to keep my site, so a late decision still counts.
- As the operator, I want removal to run on its own and stop on any failure or doubt, so the bench doesn't fill with dead sites and no one loses data to a bug.
- As the operator, I want to approve, pause, resume or retry any removal, cap how many happen a day, and rehearse the whole flow without dropping anything, so the first live runs hold no surprises.

**Acceptance criteria**:
- **AC-1**: A hosted site's removal date (`removal_on`, a date in the site's time zone, spec 0005 AC-18) is: day 30 (day 1 plus 29 days) for an unpaid trial site (`paid_until` empty) that has a `trial_started_on`; `paid_until` plus 67 days (grace end plus 60) for a site whose phase is `lapsed`. Every other site has no removal date and is never removed: unmanaged, exempt, `active`, `renew_soon`, `grace`, and a site `locked` with `lock_reason: no_trial_start`. On the control site a case's `removal_on` can only move later (a later report with an earlier date is ignored and logged), and it is frozen once the case leaves `Scheduled`.
- **AC-2**: The status dict's `removal_on` is set for the lapsed phase as well as the unpaid trial phases (it was trial only in spec 0005). The lock banners read: unpaid trial "Your books are read only. Subscribe by {0} to keep this site. After that it is removed and a copy of your data is emailed to the owner."; lapsed "Your books are read only. Renew by {0} to keep this site. After that it is removed and a copy of your data is emailed to the owner." where {0} is `removal_on`. These replace the trial and lapsed lock texts of spec 0005 AC-8 (the "Contact support." text and the AC-15 payment pending note are unchanged). The Subscription page shows a "Removal on {0}" row whenever `removal_on` is set and the phase is `locked` or `lapsed`.
- **AC-3**: `bench books-removal-run` (a bench command in frappe_books) does nothing but log one line while `books_removal_mode` in the bench's `common_site_config.json` is missing or `off`. In `dry_run` or `live` it reads the removal status of every site on the bench that has `books_control_url`, reports them to the control site in signed calls of at most 200 sites each, and carries out the instructions it gets back. Host cron runs it hourly under `flock`, so two runs never overlap.
- **AC-4**: The control site emails the owner (the signup email on its registry row, never an address read from the site) a warning before removal: 4, 2 and 1 days before `removal_on` for a trial site (days 26, 28 and 29), 14, 3 and 1 days before for a lapsed site. Each warning is sent at most once per case. When a run finds several due and unsent (the runner was down), it sends only the latest due one (the smallest offset whose date has come). A warning sent on or after `removal_on` says "very soon" instead of a date. Each warning states the removal date, the company name, and a Subscribe link to `{site_url}/books/subscription`, translated into the site's System Settings language.
- **AC-5**: The export starts only when all of these hold: the site's today is on or after `removal_on`, at least one warning for this case was sent 24 hours or more ago, the case is `Scheduled` (not paused, cancelled or failed), and the site is still unpaid by both its own report and the control site's billing state. A site first seen on or after its removal date gets the 1 day warning now, and its export waits the 24 hours.
- **AC-6**: The export is one zip holding: `readable/<DocType>.csv` for every DocType in module Frappe Books (each child table as its own CSV with `parent`, `parenttype`, `parentfield` and `idx`; each single as `field,value` rows), except Books Subscription; `readable/File.csv` (each uploaded file's `name`, `file_name`, `file_url`, `is_private`, `attached_to_doctype`, `attached_to_name`, `attached_to_field`, so files can be matched to records); `files/public/` and `files/private/` with every uploaded file at its path under the site's files folders; `backup/database.sql.gz` (a Frappe database backup of the site); and a `README.txt` saying what each part is, how to restore it on a Frappe 16 bench, and that stored secrets (Password fields such as email account passwords) can't be read after a restore and must be entered again. CSVs are UTF-8 with a byte order mark (so Excel opens them correctly), with one header row of fieldnames. No CSV holds a Password field value, and the zip holds no `site_config.json`. The database dump keeps Frappe's password hashes and encrypted secrets, which can't be read without the site's `encryption_key`, which is not in the zip. Every CSV is read inside one REPEATABLE READ transaction (one consistent snapshot of the database).
- **AC-7**: The runner uploads the zip to the private R2 bucket under a key unique to that attempt and reports its key, size and SHA256. The control site then emails the owner a download link: a control site URL holding a random token. For 30 days from the export email being sent, opening it redirects to a fresh R2 presigned URL valid 1 hour, and the download is counted on the case. After 30 days, or for an unknown token, it shows "This link has expired. Contact support." with HTTP 404.
- **AC-8**: Once the export email is `Sent` in the control site's Email Queue, the hold starts: `hold_until` is that sent time plus 72 hours. The runner then writes `export_sent_on` and `removal_hold_until` on the site's Books Subscription. If those site fields are empty when a run reports a `Holding` case, the control site sends them again. While both are set and the site is locked, the banner reads "Your books are read only. A copy of your data was emailed to the owner. This site will be removed after {0}." where {0} is `removal_hold_until` converted to the site's time zone and shown as a date in the user's date format. System Managers and Books Managers still see the Subscribe button.
- **AC-9**: The site is dropped only when, at that moment, all of these hold: the case is `Holding`, not paused, and `hold_until` has passed; the case was opened in `live` mode; when approval is required, a Removal Manager has approved it (AC-20); the bench isn't paused and today's drops for the bench are under the cap (AC-20); the export email is `Sent`; the R2 object exists at the recorded size (an R2 HEAD request); the control site's billing state shows the site unpaid, not exempt, not `auto_renews`, and with no checkout created in the last 24 hours; `books_removal_mode` is `live`; and the runner's own fresh read of the site shows phase `locked` or `lapsed`, `removal_on` on or before today, and `payment_pending` false. If any check fails, nothing is dropped.
- **AC-10**: Dropping calls Frappe's own drop function (the one behind `bench drop-site`) in process, with no backup, root credentials from the runner's secrets file (never on a command line), and an archived sites path unique to the case (`<bench>/books-removal/archived/<case>/`). The runner then deletes exactly that folder, so the R2 zip is the only copy left. A drop is safe to repeat: when the site's database and folder are both already gone, the runner reports it done. The case becomes `Removed` with `removed_on`, and the registry row is marked removed.
- **AC-11**: If the site is paid or made exempt at any time before the drop starts (a push, a pull, or the control site's own billing state), the next run cancels the open case: the R2 object is deleted by the control site, the link stops working, and the runner clears `export_sent_on` and `removal_hold_until` on the site. `apply_state` (spec 0005) also clears both fields whenever it applies a newer `paid_until`. Once a case is `Dropping` or `Removed`, the control site refuses `create_checkout` for that site. In the last hour before `hold_until` it also refuses, with "This site is being removed. Contact support.", so no payment starts while a drop can start.
- **AC-12**: A failed step (building the export, the upload, the drop) is reported to the control site with the error, with every secret removed from the text. The case retries on the next hourly runs. An export the runner put off because of the per run cap is reported as `deferred` and doesn't count as an attempt. An `Exporting` case with no report for 6 hours counts one attempt and is sent `export` again. After the third failed attempt it becomes `Failed`, an email goes to `books_ops_email` at once, and nothing is dropped until a Removal Manager presses Retry. A `Holding` case whose export email is in `Error`, or still not `Sent` 24 hours after it was queued, also becomes `Failed`. A failure never leads to a drop.
- **AC-13**: Only users with the Removal Manager role on the control site can Approve, Pause, Resume or Retry a case. Approve works on `Holding` cases. Pause works on `Scheduled` and `Holding` cases. Resume returns a case to `Holding` if it has an export, otherwise to `Scheduled`, and clears `paused_by` and `pause_reason`. Retry does the same for a `Failed` case and resets `attempts` to 0. A Retry of a case whose export email failed sends it again, and the hold starts again from the new sent time. Anyone else gets HTTP 403.
- **AC-14**: In `dry_run` mode the runner and control site do everything live mode does except the drop and the site writes: they open cases, export, upload and email, but every owner email goes to `books_ops_email` instead (the owner's address is shown in its body), the site fields of AC-8 are not written, and a case due for its drop stays `Holding` and logs "would drop {site}" on every run. Each case records the mode it was opened in. The first `live` report from a bench cancels every open `dry_run` case of that bench (deleting its exports), so live starts fresh with real warnings to real owners.
- **AC-15**: Every runner to control site call carries `bench` in its body and is signed with that bench's runner secret (HMAC SHA256 over the raw body in `X-Books-Signature`, with an `issued_at` within 5 minutes, as in spec 0005). The control site refuses with 401 any call with a bad signature, an unknown bench or a stale `issued_at`. Every answer is signed the same way and echoes the request's `issued_at`, and the runner acts on no answer whose signature or echo doesn't match. The runner calls only an `https://` control URL. The control site ignores, and logs, any reported site that its registry doesn't place on that bench, and one bad site entry never fails the whole call. The runner secret, the R2 keys and the database root login live in `<bench>/config/books-runner.json` (readable only by the bench user, mode 600), never in `common_site_config.json`, which every site can read through `frappe.conf`. Hosted sites keep server scripts off (`server_script_enabled` unset).
- **AC-16**: The R2 bucket deletes every export object 90 days after upload, and unfinished multipart uploads after 1 day, through lifecycle rules. The case records `delete_export_on`. The download link works only for the first 30 days.
- **AC-17**: Books Removal Case keeps track changes, and no one can delete a case. Every warning sent, every download, every approval and every status change can be read from the case and its versions.
- **AC-18**: Reading the removal status and building the export change nothing on the site except the AC-8 fields (written through the existing Books Subscription sync guard). The site's read only lock doesn't stop them, because the runner works outside a web request and outside a background job.
- **AC-19**: The new banner texts (AC-2, AC-8) and the "Removal on" row work at phone width, are translated at runtime, and show dates through the frontend's date formatter, as in spec 0005 AC-19.
- **AC-20**: Drop safety gates on the control site. While `books_removal_require_approval` is on (the default), a `Holding` case is dropped only after a Removal Manager approves it; approving records `approved_by` and `approved_on`, and still waits for `hold_until` and every AC-9 check. At most `books_removal_max_drops_per_day` drops (default 5) start per bench per control site day (UTC); the rest wait for the next day. Setting `removal_paused` on a bench's record stops every new export and drop for that bench at once.
- **AC-21**: The control site emails `books_ops_email` when: a case becomes `Failed`; a bench hasn't reported for 3 hours; a site reports `error` on 3 runs in a row; a case stays `Dropping` for more than 2 hours; or a `Holding` case is waiting for approval (one email a day listing them). A daily digest lists removals and cancellations.

## Decision

**Chosen option**: Option 2: the control site decides, and a bench command runner on the hosting server carries out the work. The customer site stays the only clock.

The runner is a bench command shipped in frappe_books and run by host cron. Each hour it reads every hosted site's removal status in process, reports it to the control site in signed calls, verifies the signed answers, and does what it is told: export, mark the site, clear the site, or drop. The control site owns the removal record, the warnings, the emails, the download link, the drop gates and the final go ahead.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`, for the banner texts only) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

There are three parts: the customer site (this app), the runner (a bench command in this app, on the hosting server), and the control site (`rarebooks_control`, built under feature 8). This spec defines all three sides of the removal contract, plus the control site's removal records. The feature 8 spec builds the control site app around them.

**Data model sketch**:

Customer site, Books Subscription (two new fields; written only by the runner under the existing `syncing()` guard in `state.py`, and cleared by `apply_state` on a newer `paid_until`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `export_sent_on` | Datetime | no | Naive UTC. When the export email was sent. Read only in the form |
| `removal_hold_until` | Datetime | no | Naive UTC. Sent time plus 72 hours. Read only in the form |

Control site, `Books Hosting Bench` (one per hosting bench; Removal Manager and System Manager read, Removal Manager writes `removal_paused`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `bench_name` | Data, unique | yes | Primary key. Equals the runner's `bench` value |
| `last_report_on` | Datetime | no | UTC, set on each valid `report_sites` |
| `last_mode` | Select: off, dry_run, live | no | From the last report |
| `removal_paused` | Check | no | The kill switch (AC-20) |

The secret is not stored here. It lives in the control site's `site_config.json` (`books_runner_secrets`).

Control site, `Books Removal Case` (autoname `RC-.#####`; `track_changes: 1`; no role may delete; Removal Manager reads and runs the actions, System Manager reads):

| Field | Type | Required | Notes |
|---|---|---|---|
| `site` | Link to the hosted site registry | yes | N cases to 1 site. At most one open case (status not `Removed` or `Cancelled`) per site, checked in `validate` |
| `bench` | Link: Books Hosting Bench | yes | N cases to 1 bench |
| `mode` | Select: dry_run, live | yes | The mode of the report that opened it |
| `kind` | Select: Trial, Lapsed | yes | |
| `removal_on` | Date | yes | The site's date. Moves only later, frozen after `Scheduled` |
| `status` | Select: Scheduled, Exporting, Holding, Paused, Dropping, Removed, Cancelled, Failed | yes | Default `Scheduled` |
| `owner_email` | Data (Email) | yes | Copied from the registry when the case opens |
| `site_url` | Data | yes | From the report |
| `site_language` | Data | no | From the report, for translating emails |
| `company_name` | Data | no | From the report, for the emails |
| `export_claimed_on` | Datetime | no | UTC, when `export` was last sent to the runner |
| `export_key` | Data | no | R2 key `exports/<case>/<attempt id>.zip` (`attempt id` is a random UUID made by the runner) |
| `export_bytes` | Int | no | |
| `export_sha256` | Data | no | |
| `export_email` | Link: Email Queue | no | The export email |
| `export_queued_on` | Datetime | no | UTC, when the export email was queued |
| `export_sent_on` | Datetime | no | UTC, the Email Queue sent time |
| `hold_until` | Datetime | no | UTC, `export_sent_on` plus 72 hours |
| `approved_by` | Link: User | no | |
| `approved_on` | Datetime | no | UTC |
| `link_token_hash` | Data | no | SHA256 hex of the download token. The token itself is never stored |
| `link_expires_on` | Datetime | no | UTC, `export_sent_on` plus 30 days |
| `download_count` | Int | no | Default 0 |
| `last_downloaded_on` | Datetime | no | UTC |
| `delete_export_on` | Date | no | Upload date plus 90 days (the lifecycle rule does the delete) |
| `drop_started_on` | Datetime | no | UTC, set when it enters `Dropping` |
| `removed_on` | Datetime | no | UTC |
| `attempts` | Int | no | Failed attempts of the current step. Reset to 0 on entering `Holding` and on Retry |
| `error_runs` | Int | no | Consecutive reports with `error` for this site. Reset by a good report |
| `last_error` | Small Text | no | |
| `paused_by` | Link: User | no | |
| `pause_reason` | Small Text | no | |
| `warnings` | Table: Books Removal Warning | no | 1 case to N warnings |

`Books Removal Warning` (child table): `offset_days` Int (required; unique within its case), `sent_on` Datetime UTC (required), `recipient` Data (required), `email` Link: Email Queue.

Registry row (built by feature 8; this spec needs these fields on it): `owner_email`, `hosting_bench` (Link: Books Hosting Bench), and `removed_on` Datetime.

**State transitions** (Books Removal Case):

| From | To | Trigger |
|---|---|---|
| (none) | `Scheduled` | a report carries a `removal_on` for a site with no open case |
| `Scheduled` | `Exporting` | `report_sites` finds the AC-5 conditions met (and the bench isn't paused) and sends `export`, setting `export_claimed_on` |
| `Exporting` | `Holding` | the export email is `Sent` (checked on each `report_sites`), after `export_ready` recorded the upload and queued the email |
| `Exporting` | `Scheduled` | `step_failed` with attempts below 3, or `deferred` (no attempt counted) |
| `Exporting` | `Failed` | the third failed attempt (a `step_failed`, or 6 hours with no report after a claim); or the export email in `Error`, or not `Sent` 24 hours after it was queued |
| `Holding` | `Dropping` | `drop_starting` passes every AC-9 and AC-20 check; sets `drop_started_on` |
| `Dropping` | `Removed` | `drop_done` |
| `Dropping` | `Dropping` | every report while `Dropping` sends `drop` again (the drop is safe to repeat) |
| `Dropping` | `Failed` | the third `step_failed` for the drop |
| `Scheduled`, `Holding` | `Paused` | Pause (Removal Manager) |
| `Paused`, `Failed` | `Holding` if `export_sent_on` set, else `Scheduled` | Resume or Retry (Removal Manager) |
| any open status but `Dropping` | `Cancelled` | the site is paid or exempt (AC-11), or a dry run case when the bench's first live report arrives (AC-14) |

`Removed` and `Cancelled` are final. A new lapse after a cancelled case opens a new case, and its warnings start again.

**Runner flow** (`bench books-removal-run`, in `frappe_books/commands.py`, exposed through the module level `commands` list that bench loads from each app):

1. Read `books_removal_mode` from `common_site_config.json`. On `off` or missing, log and exit 0. Read `<bench>/config/books-runner.json`; exit 1 if it is missing or readable by anyone other than its owner.
2. For each site in `frappe.utils.get_sites()`: `frappe.init` and `frappe.connect`, skip it unless `books_control_url` is set, call `frappe_books.subscription.removal.removal_status()`, then `frappe.destroy()`. A site that fails to open is reported with `error`, and processing goes on.
3. `POST report_sites` with the statuses in chunks of 200, plus the `deferred` cases from the previous run's log. Verify each signed answer. If the control site can't be reached or an answer fails verification, log and exit 1, doing nothing else.
4. Carry out the instructions in this order: `clear`, `mark_sent`, `export` (at most 3 per run; the rest are logged as deferred for the next report), then `drop`.
   - Each export: check free disk, open the site, build the export in `<bench>/books-removal/<case>/` inside one REPEATABLE READ transaction, zip it (ZIP64), upload it to R2 under `exports/<case>/<uuid>.zip` with a multipart upload, call `export_ready`, delete the local folder. The runner never deletes an R2 object.
   - Each `mark_sent` (live only): call `mark_export_sent` on the site with the times in the instruction.
   - Each drop: call `removal_status()` again (the AC-9 local check), call `drop_starting`, and only on a verified `proceed: true` run the drop, delete the case's archived folder, then call `drop_done`. A site whose database and folder are both gone goes straight to `drop_done`.
   - Any exception in a step calls `step_failed` with the error text after secrets are removed, then moves on.
5. Log one summary line per site to `<bench>/logs/books-removal.log`.

**API surface**:

Customer site, `frappe_books/subscription/removal.py` (plain functions called in process by the runner; none is whitelisted, and none goes in `ALLOWED_METHODS`):

| Function | Inputs | Outputs | Notes |
|---|---|---|---|
| `removal_status()` | none | `site`, `site_url`, `phase`, `today`, `removal_on`, `kind` (`Trial`, `Lapsed` or null), `paid_until`, `exempt`, `payment_pending`, `language`, `company_name`, `export_sent_on`, `removal_hold_until` | Reads `current_clock()` |
| `build_export(out_dir: str)` | target folder | `{"doctypes": int, "rows": int, "files": int, "bytes": int}` | Writes the AC-6 layout in one REPEATABLE READ transaction, read in pages of 1,000 rows ordered by `name` (stable inside the snapshot). The database dump comes from `frappe.utils.backups.new_backup` with no files and no site config |
| `mark_export_sent(export_sent_on: str, removal_hold_until: str)` | ISO UTC timestamps | none | Writes the two fields under `syncing()`. Safe to repeat |
| `clear_removal()` | none | none | Empties both fields under `syncing()`. Safe when they're already empty |
| `apply_state` (spec 0005, `state.py`) | | | Also clears both fields when it applies a newer `paid_until` |
| status dict (`clock.py`) | | adds `export_sent_on`, `removal_hold_until`; `removal_on` now set for `lapsed` too | `REMOVAL_AFTER_GRACE_DAYS = 60` beside the existing constants |

Control site, module `rarebooks_control.removal` (each runner POST is a guest method with a raw JSON body signed per AC-15, `@rate_limit(limit=120, seconds=60)`, every auth failure 401 with no detail; every answer signed and echoing `issued_at`):

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `report_sites` | POST | `bench`, `issued_at`, `mode`, `sites`: up to 200 `removal_status()` dicts (or `site` + `error`), `deferred`: list of case names | `instructions`: list of `site`, `case`, `action` (`export`, `mark_sent`, `clear`, `drop`), with `export_sent_on` and `removal_hold_until` for `mark_sent` | runner HMAC | 401 bad signature or unknown bench; a bad or unknown site entry is skipped and logged |
| `export_ready` | POST | `bench`, `issued_at`, `case`, `site`, `key`, `bytes`, `sha256` | `status` | runner HMAC | 409 when the case isn't `Exporting` (the control site deletes that object itself) |
| `step_failed` | POST | `bench`, `issued_at`, `case`, `step` (`export`, `upload`, `drop`), `error` (first 2,000 characters, secrets removed) | `status` | runner HMAC | 409 for a final case |
| `drop_starting` | POST | `bench`, `issued_at`, `case`, `site` | `proceed`: bool, `reason` | runner HMAC | none; a failed check is `proceed: false` with the reason |
| `drop_done` | POST | `bench`, `issued_at`, `case`, `site` | `status` | runner HMAC | 409 unless `Dropping` |
| `download` | GET | `token` (query) | 302 to a 1 hour R2 presigned URL | guest, `@rate_limit(limit=10, seconds=3600)` per IP | 404 expired or unknown, as AC-7 |
| `approve_case`, `pause_case`, `resume_case`, `retry_case` | POST | `case`, `reason` (pause only) | `status` | Removal Manager (`frappe.only_for`) | 403 other roles; 417 wrong status |

Emails (control site, `frappe.sendmail` through its outgoing Email Account, translated with `_()` into `site_language`): one warning template per kind (trial, lapsed), the export email (link, expiry date, size, what the zip holds, how to restore), and the ops emails of AC-21.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| `removal_status`, banner | `removal_on` (trial) | day 1 plus 29 days (`REMOVAL_DAY`, spec 0005) |
| `removal_status`, banner | `removal_on` (lapsed) | `paid_until` plus `GRACE_DAYS` (7) plus `REMOVAL_AFTER_GRACE_DAYS` (60) |
| `removal_status` | `today`, `phase`, `kind`, `payment_pending` | `current_clock()` and its status dict (spec 0005); `kind` from the phase (`locked` with a day 1 is Trial, `lapsed` is Lapsed) |
| `removal_status` | `site_url` | `frappe.utils.get_url()` on that site |
| `removal_status` | `language`, `company_name` | System Settings `language`; the Books company name from `frappe_books.settings` |
| `report_sites` | which sites belong to the bench | registry `hosting_bench` equal to body `bench` |
| case, every email | owner address | registry `owner_email`, copied at case open |
| case | `removal_on` change | the larger of the stored and the reported date, while `Scheduled` |
| warnings | which warning is due | `removal_on` minus each offset (4, 2, 1 or 14, 3, 1) compared with the reported site `today`; the latest due unsent offset |
| export check | "a warning sent 24 hours ago" | the earliest `Books Removal Warning.sent_on` on the case versus control site now (UTC) |
| export, drop and cancel checks | paid, exempt, `auto_renews`, recent checkout | the site's report and the control site's own billing state for the site (feature 8); either one showing paid or exempt is enough to cancel |
| runner | free disk check | `shutil.disk_usage` of the bench folder must exceed 2 × (database size from `information_schema` + size of the site's `public/files` and `private/files`) |
| export | R2 key | `exports/<case>/<uuid4>.zip`, the UUID made by the runner per attempt |
| hold | `hold_until`, `link_expires_on` | the Email Queue row's sent time (`modified` when its status became `Sent`) plus 72 hours, plus 30 days |
| `export_ready` | `delete_export_on` | upload date plus 90 days |
| export email | link | `{control site url}/api/method/rarebooks_control.removal.download?token=<token>`, token = `secrets.token_urlsafe(32)`, its SHA256 stored |
| banner (AC-8) | the "removed after" date | Books Subscription `removal_hold_until`, converted to the site's time zone |
| drop gates | approval required, daily cap | control site `site_config.json` `books_removal_require_approval` (default on), `books_removal_max_drops_per_day` (default 5); today's count = cases of the bench with `drop_started_on` on the current UTC date |
| drop gates | bench paused | `Books Hosting Bench.removal_paused` |
| drop check | R2 object present | an R2 HEAD on `export_key`, `ContentLength` equal to `export_bytes` |
| drop | database root login | `root_login` and `root_password` in `books-runner.json` |
| ops alerts | "bench silent", "site erroring", "stuck drop" | `Books Hosting Bench.last_report_on`, `Books Removal Case.error_runs`, `drop_started_on`, checked by an hourly scheduled job on the control site |
| dry run emails | recipient | control site `books_ops_email` in place of `owner_email` when the case `mode` is `dry_run` |
| all runner calls | runner identity, secret, control URL | `books-runner.json` (`runner_name`, `runner_secret`, `control_url`); on the control site `books_runner_secrets[bench]` in its `site_config.json` |

**Key invariants**:
- Nothing is dropped unless the case is `Dropping`, which only `drop_starting` sets, and only after every AC-9 and AC-20 check passes within the same request.
- No owner is removed without at least one warning sent to them 24 hours or more before the export. A dry run case never reaches a live drop.
- No drop happens without an export that is in R2 at its recorded size and whose email was `Sent` at least 72 hours earlier.
- A paid, exempt or auto renewing site, or one with a checkout in the last 24 hours, never gets a `drop` that passes.
- A site has at most one open case.
- The customer site is the only clock: the control site never computes `removal_on`, it stores what the site reports, and only ever moves it later.
- The runner never drops a site that it didn't just read itself in that same run, and acts on no unsigned or mismatched answer.
- The runner never deletes an R2 object, and deletes only the archived folder it named for that case.

**Security model**:
- Secrets: the runner secret, the R2 write token and the database root login live in `<bench>/config/books-runner.json` (mode 600, owned by the bench user). Frappe never loads that file, so no site can read it through `frappe.conf`. Nothing secret goes in `common_site_config.json`. Hosted sites keep server scripts off, so tenant code can't run on the server.
- Runner calls: one secret per hosting bench, separate from the per site secrets of spec 0005. Requests and answers are both signed, and the runner uses `https` only. A bench may report only the sites the registry places on it, so a leaked runner secret affects that bench's sites only.
- Removal actions on the control site: Removal Manager only, checked on the server with `frappe.only_for`. System Manager alone doesn't grant them.
- Download: an unguessable 32 byte token, stored hashed, valid for 30 days, rate limited per IP, every download counted. The R2 bucket is private with encryption at rest, and URLs are served over HTTPS only.
- R2 credentials: the runner holds a write only token for the bucket, and the control site a read and delete token. Neither can list other buckets.
- Data protection: the export holds the customer's full books (personal data of their customers and suppliers). It is kept for 90 days and then deleted by lifecycle, the archived site folder is deleted at the drop, and no other copy is kept. Audit: track changes on Books Removal Case, plus its warning rows, approvals and download count.
- Never log or report the runner secret, the R2 keys, `root_password` or a download token. Error text is scrubbed of them before `step_failed`.

**Configuration required**:
- Hosting bench `common_site_config.json`: `books_removal_mode` (`off`, `dry_run`, `live`; default `off`). Not secret.
- Hosting bench `<bench>/config/books-runner.json` (mode 600): `runner_name`, `runner_secret` (32 random bytes or more), `control_url` (`https://`), `export_storage` (`endpoint_url`, `bucket`, `access_key_id`, `secret_access_key` for the write only R2 token), `root_login`, `root_password`.
- Host crontab: `0 * * * * cd <bench> && flock -n /tmp/books-removal.lock bench books-removal-run >> logs/books-removal.log 2>&1`.
- Hosted sites: `server_script_enabled` left unset.
- Control site `site_config.json`: `books_runner_secrets` (map of bench name to secret), `books_export_storage` (the read and delete token), `books_ops_email`, `books_removal_require_approval` (default on), `books_removal_max_drops_per_day` (default 5).
- Cloudflare R2: a private bucket, a lifecycle rule that deletes `exports/` objects after 90 days, and one that aborts unfinished multipart uploads after 1 day. This needs a Cloudflare account set up before the export task.
- Hosting bench nginx with `dns_multitenant` on, so a dropped site needs no nginx change.
- Python: `boto3` for R2. Frappe 16 already depends on it for its S3 backups; check at build time, and add it to `pyproject.toml` if not.

**Critical test scenarios** (Python in this repo with a control site stub that signs its answers and a fake storage, as in spec 0005's `ControlStub`; the control site side is tested in feature 8's repo):
- Happy path: a trial site on day 30 with a warning sent 25 hours ago gets `export`, the zip is built and uploaded, the stub marks the email sent, `mark_sent` writes the site fields and the banner shows the hold text, and after the hold and an approval `drop` runs the in process drop (mocked) and `drop_done`. Verifies **AC-3**, **AC-5**, **AC-6**, **AC-7**, **AC-8**, **AC-9**, **AC-10**, **AC-20**.
- Dates: `removal_on` is day 30 for an unpaid trial, `paid_until` plus 67 for lapsed, null for `grace`, `active`, exempt, unmanaged and `no_trial_start`; Dar es Salaam time zone near midnight for the hold date. Verifies **AC-1**, **AC-2**, **AC-8**.
- Late payment: a push with a new `paid_until` arrives while the case is `Holding`; `apply_state` clears the site fields, the next run cancels the case, and no drop is ever sent. Verifies **AC-11**.
- Last moment checks: `drop_starting` says proceed, but the fresh local status shows `payment_pending`; nothing is dropped. An unsigned or mismatched `proceed` is ignored. Verifies **AC-9**, **AC-15**.
- Failure: upload fails three runs in a row; the case is `Failed`, the ops email is sent, and no further `export` or `drop` comes until Retry. A deferred export counts no attempt. Verifies **AC-12**.
- Repeat drop: the database is gone but the folder remains; the next `drop` finishes it and reports done. Verifies **AC-10**.
- Missed warnings: the first report arrives on day 30 with no warnings; only the 1 day warning is sent, and the export waits 24 hours. Verifies **AC-4**, **AC-5**.
- Export content: a site with an invoice, its items, a single setting, an attached file and a Password field yields the AC-6 layout with `File.csv`, a BOM at the start of each CSV, no password value in any CSV and no `site_config.json`. Verifies **AC-6**, **AC-18**.
- Locked site: `build_export` and `mark_export_sent` succeed on a site whose phase is `locked`. Verifies **AC-18**.
- Mode: `off` makes no call; `dry_run` reaches the drop and logs "would drop" without dropping or calling `mark_export_sent`. Verifies **AC-3**, **AC-14**.
- Secrets: the runner refuses to start when `books-runner.json` is readable by others; a `step_failed` error text never contains the root password. Verifies **AC-12**, **AC-15**.
- Auth: a runner call signed with a site secret, a stale `issued_at`, or for a site on another bench is refused or ignored. Verifies **AC-15**.
- Banner: Node tests for the new trial and lapsed lock texts and the hold text; one Playwright test with the hold fields set. Verifies **AC-2**, **AC-8**, **AC-19**.

## Build plan

Tracer Bullet: the first slice runs one real export end to end (site status, runner, signed stub control site, stub storage, banner) before warnings, drops or failure handling are added. The drop comes last, behind `dry_run` and approval, because it is the only step that can't be undone.

**Milestone 1: The thread, one export end to end (against stubs)**
1. `clock.py`: `REMOVAL_AFTER_GRACE_DAYS`, `removal_on` for lapsed, `export_sent_on` and `removal_hold_until` in the status dict. Python tests at each boundary. Satisfies **AC-1**, **AC-2**.
2. The two Books Subscription fields (JSON, read only), `removal.py` with `removal_status`, `mark_export_sent`, `clear_removal`, and the clearing in `apply_state`. Satisfies **AC-1**, **AC-8**, **AC-11**, **AC-18**.
3. `build_export` with the full AC-6 layout, `File.csv`, the snapshot transaction and the README. Tests for content, BOM, the excluded Password and site config, and a locked site. Satisfies **AC-6**, **AC-18**.
4. `frappe_books/commands.py` with `books-removal-run`: the mode switch, the secrets file and its permission check, the site loop, chunked signed `report_sites` with answer verification (reusing `control.py`'s signing helpers with the runner secret), the `export` and `mark_sent` instructions, the disk check, zip, upload through a storage interface (R2 through boto3, with a fake for tests), `export_ready`. Extend `ControlStub` for the removal calls. Satisfies **AC-3**, **AC-5**, **AC-7**, **AC-8**, **AC-15**.
5. Banner and Subscription page: the new trial and lapsed texts with their date, the hold text, the "Removal on" row; Node tests. Satisfies **AC-2**, **AC-8**, **AC-19**.

**Milestone 2: Cancel and failure paths**
6. The `clear` instruction, and tests for a late payment during `Exporting` and `Holding`. Satisfies **AC-11**.
7. `step_failed` with secret scrubbing, `deferred` reporting, the per site error report, the exit code and log line when the control site is down or an answer fails verification. Satisfies **AC-12**, **AC-15**.

**Milestone 3: The drop, behind dry run**
8. The `drop` instruction: fresh local check (with `payment_pending`), `drop_starting`, Frappe's drop function in process with the case's archived path and root credentials from the secrets file (the function and its arguments checked against Frappe 16 at build), deleting exactly that folder, the repeat safe path, `drop_done`. In `dry_run`, log "would drop" only. Tests with a mocked drop. Satisfies **AC-9**, **AC-10**, **AC-14**.
9. Phone layout of the new texts, and one Playwright test with the hold fields set. Satisfies **AC-19**, rechecks **AC-2**, **AC-8**.

**Milestone 4: Control site removal side (built in the `rarebooks_control` repo, under feature 8)**
10. Books Hosting Bench, Books Removal Case and Books Removal Warning, the Removal Manager role, the one open case check, no delete permission, track changes. Satisfies **AC-13**, **AC-17**, **AC-20**.
11. `report_sites` (registry bench check, case open and update with the "later only" date, dry run cancel on the first live report, the cancel rule, warning choice and sending, the export condition, the email sent check that starts the hold, `mark_sent` and `drop` instructions), `export_ready`, `step_failed`, `drop_starting` with every AC-9 and AC-20 check, `drop_done`, all signed both ways. Satisfies **AC-4**, **AC-5**, **AC-8**, **AC-9**, **AC-11**, **AC-12**, **AC-14**, **AC-15**, **AC-20**.
12. `download` with the token hash and the presigned redirect, the emails and their translations, dry run redirection, `create_checkout` refusals, Approve, Pause, Resume and Retry, the hourly alert job and the daily digest. Satisfies **AC-4**, **AC-7**, **AC-11**, **AC-12**, **AC-13**, **AC-14**, **AC-16**, **AC-21**.

**Milestone 5: Rollout**
13. R2 bucket, both lifecycle rules and the tokens; `books-runner.json`, the mode key and the cron line on the host; a `dry_run` cycle on the real bench with a test site taken through day 30 (using `set_hosted_phase`), the ops inbox checked; then `live` with approval on. Satisfies **AC-3**, **AC-14**, **AC-16**, **AC-20**.

## Consequences

**Positive**:
- One clock: the date a user sees in the banner is the date the export uses, because the control site only stores what the site reports, and only ever moves it later.
- No removal without a warning, an export confirmed in R2, a sent email, a 72 hour hold, your approval (at first), a daily cap, and fresh "still unpaid, no payment pending" checks on both sides. Every doubt turns into "don't drop".
- The owner leaves with data they can open in Excel and also restore on their own Frappe bench, which keeps the AGPL self hosting promise.
- `dry_run` lets you rehearse the whole flow on the real bench with no deletion and no customer email, and it can't leak into live.

**Negative / tradeoffs**:
- Production removal waits on feature 8 (the control site). Until then the runner can only run against the test stub.
- With approval on, every drop needs your click. Unapproved sites sit read only until you act, and you get a daily list of them.
- A late runner, an email outage, a pause, the cap or a pending approval pushes the real removal past the date in the banner and the warnings. The texts say the site is removed "after" that date, which stays true.
- The trial promise "removed on day 30" becomes "export on day 30, removed after day 33 at the earliest".
- The database dump includes users' password hashes, so a restored site keeps its logins. That is the owner's own data, but the zip deserves care. Stored secrets (Password fields) don't survive a restore and must be entered again.
- The hosting bench holds its database root login in `books-runner.json`, and the runner can drop any site on the bench. That file and the runner secret become high value.
- Exports are built on the hosting server's disk, so a big site briefly needs about twice its size free. The disk check fails the step instead of filling the disk.
- At most 3 exports per hourly run and 5 drops a day per bench, so a mass expiry takes hours to export and days to drop.
- Per site TLS certificates (if not a wildcard) stay on the host after the drop and fail to renew until removed.

**Neutral**:
- frappe_books gets its first bench command (`commands.py`) and its first use of R2 (boto3).
- Spec 0005 AC-8's trial and lapsed lock texts and its status dict's `removal_on` rule change; spec 0005 now points here.
- `frappe_books/subscription/AGENTS.md` gains the runner, the secrets file, the mode switch and the new config keys (for `/sync`).

## Follow-up

- [ ] Feature 8's spec must include the registry fields this spec needs (`owner_email`, `hosting_bench`, `removed_on`), the billing state lookup that AC-5, AC-9 and AC-11 read (paid, exempt, `auto_renews`, the last checkout time), cancelling any provider subscription when a site is removed, and the Milestone 4 work.
- [ ] Confirm against the installed Frappe 16 bench: the in process drop function behind `bench drop-site` and its arguments (no backup, root login, archived sites path), whether `new_backup` can skip the site config, and how to read an Email Queue row's sent time (Context7 had no entry for them).
- [ ] Decide whether to delete a dropped site's per site TLS certificate in the runner, or move the host to a wildcard certificate.
- [ ] Consider a "Removed" page on the control site (or a DNS catch all) so a removed site's URL tells visitors what happened, not a bare 404.
- [ ] Turn `books_removal_require_approval` off once a few months of drops have gone cleanly.
