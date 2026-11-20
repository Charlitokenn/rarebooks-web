# 0010. Hosting on Frappe Cloud

**Date**: 2026-11-20
**Status**: In Progress

Replaces in part: spec [0007](../0007-trial-end-export-removal/index.md) (AC-3, AC-10, AC-15, AC-18, the runner, Books Hosting Bench, Milestone 5) and spec [0008](../0008-billing-control-site/index.md) (AC-1, AC-15, the host parts of AC-22, task 19). Every other rule in those specs still holds.

Amended by: spec [0011](../0011-archive-call-mark.md) (the archive mark, the removed `config_job`, and the Retry config, `get_state`, Rotate secret and registration failure rules). The text below already reflects it.

## Summary

Your customer sites and the control site run on a Frappe Cloud dedicated server, where you have no root login, no host cron and no database root password. So the bench command runner of spec 0007 can't run there. Instead, the control site does the hourly removal round itself: it calls each customer site over signed HTTPS, asks the site to build its own export in a background job and upload it to R2 through a short lived upload link, and finally archives the site through the Frappe Cloud API. Registration and secret rotation also go through that API, so no one types a secret or edits a config file by hand.

## Requirements

**User stories**:
- As the operator, I want removal, registration and secret rotation to run on Frappe Cloud with no server access, so the whole product lives where I host it.
- As the operator, I want a bug in the control site to be unable to archive anything except a registered customer site on my Books bench group, so one API key can't take down the wrong site.
- As a site owner, I want the same warnings, export and safety hold as before, so moving hosts changes nothing for me.

**Acceptance criteria**:
- **AC-1**: An hourly scheduled job on the control site reads Books Removal Settings. While `mode` is `off` it only logs one line and sets `last_run_on`. In `dry_run` or `live` it enqueues one job per Books Hosted Site whose `status` is Active and `config_status` is Active, plus one per site with a `Dropping` case whatever its statuses, which only polls Frappe Cloud (spec 0011 AC-10) (`job_id="removal:<site>"`, deduplicated), sets `last_run_on`, and each job calls the site's `removal_report` and applies spec 0007's rules to the answer (case open and update, warnings, cancel, export, hold, drop). Within one job the calls go in this order: `clear_removal` (on a cancel), `mark_export_sent`, `start_export`, then the drop. A site that can't be reached, or whose answer fails verification, counts one `error_runs` on its open case (or is logged when it has none), and nothing else happens for that site in that run. In `dry_run`, as in spec 0007 AC-14, no site field is written (`mark_export_sent` and `clear_removal` aren't called), owner emails go to `books_ops_email`, exports are still built and uploaded (and count toward AC-3's cap), and a due drop only logs "would drop {site}". A site skipped because its `config_status` isn't Active still has its open case cancelled when the control site's own billing state shows it paid or exempt (the R2 object is deleted; the site fields are cleared at its next Active report). Each job reads the site's secrets fresh before every call.
- **AC-2**: Every control site to customer site call (`removal_report`, `start_export`, `mark_export_sent`, `clear_removal`, `control_ping`) is a guest POST to `{site_url}/api/method/frappe_books.subscription.<name>`, signed with that site's `control_secret` (or `pending_secret` during a rotation) per spec 0005: HMAC SHA256 over the raw body in `X-Books-Signature`, `issued_at` within 5 minutes. The site refuses a bad signature or a stale `issued_at` with 401 and no detail. Every answer, a 401 included, is signed with the same secret and echoes the request's `issued_at`, and the control site acts on no answer whose signature or echo doesn't match. Each site endpoint is rate limited to 60 calls a minute.
- **AC-3**: When spec 0007 AC-5's export conditions hold, the control site makes an `attempt_id` (UUID4), a key `exports/<case>/<attempt_id>.zip`, and a presigned R2 PUT URL for that key valid 6 hours, stores `attempt_id` and `export_key`, sets `export_claimed_on` and status `Exporting`, and calls `start_export` with `case`, `attempt_id`, `upload_url` and `expires_at`. At most 3 `start_export` calls are made per hourly run across all sites, counted with an atomic cache increment (`removal:exports:<UTC hour>`); a call that fails to connect gives its slot back and counts no attempt, and the others wait for the next run with no attempt counted. The site enqueues one job on the long queue (`job_id="books-export:<case>:<attempt_id>"`, deduplicated, timeout 2 hours) and answers `queued`. An `Exporting` case whose `export_claimed_on` is more than 6 hours old counts one failed attempt (spec 0007 AC-12) and gets a new `attempt_id` and URL on the next run; an older attempt's object is never deleted by the control site, the 90 day lifecycle rule removes it.
- **AC-4**: The export job first refuses to start, reporting `step_failed` with `link_expiring`, when less than 2 hours remain before `expires_at`. It then checks free disk (spec 0007's 2 times rule), builds spec 0007 AC-6's layout in `sites/<site>/books-removal/<case>/` (outside `public` and `private`, so no Frappe Cloud backup picks it up), zips it, and uploads it with one HTTP PUT to `upload_url`. A zip over 5,000,000,000 bytes is not uploaded, and the job reports `step_failed` with `too_large`. On success it calls the control site's `export_ready` with `case`, `attempt_id`, `bytes` and `sha256`; on any failure it calls `step_failed` with the error text with every secret and the upload URL removed. It deletes its folder in every case. The control site accepts `export_ready` only for an `Exporting` case with the same `attempt_id`, and only after an R2 HEAD shows `ContentLength` equal to `bytes`; then it queues the export email as in spec 0007 AC-7. An R2 error or timeout during that HEAD answers a signed 503, and the job retries `export_ready` up to 3 times (1, 5 and 15 minutes later). A 409 (another attempt, a case no longer `Exporting`, or a size mismatch) tells the job to stop; it deletes nothing in R2.
- **AC-5**: On a locked site, `removal_report`, `start_export`, `mark_export_sent`, `clear_removal` and `control_ping` still work (the two writers are in `ALLOWED_METHODS`), and the export job runs and writes nothing to the site's database. `lock_job` skips `frappe_books.subscription.removal.export_job` by name, as it skips scheduled jobs, so the job can open its own REPEATABLE READ snapshot (spec 0007 AC-6) and run `new_backup`; the job itself only writes files under its own folder. Nothing on the site changes except spec 0007 AC-8's two fields, written through the existing `syncing()` guard.
- **AC-6**: A drop starts only when every spec 0007 AC-9 and AC-20 check holds, with two changes: the mode check reads Books Removal Settings `mode` = `live`, and "the runner's own fresh read" is a `removal_report` the same job makes right before the archive call (phase `locked` or `lapsed`, `removal_on` on or before the site's today, `payment_pending` false). Then the control site reads the site from the Frappe Cloud API immediately before archiving and goes on only when it exists, its bench group equals `books_bench_group`, its Frappe Cloud status is Active (never Suspended, Broken or anything else), its name is the case's site and a Books Hosted Site, and it isn't the control site itself. The daily cap is counted while holding a row lock on Books Removal Settings, so parallel site jobs can't pass it. It sets `Dropping` and `drop_started_on` and **commits** (releasing the lock), and only then calls the Frappe Cloud archive (`force: false`) and, once it succeeds or ends in a timeout after sending (spec 0011 AC-1), sets `archive_requested_on` (UTC) and commits. A crash between the commit and that save leaves a `Dropping` case that AC-7's poll finishes or calls again. An empty bench group from the API fails the bench group check. The drop's failures use the case's `attempts` counter, which is 0 on entering `Holding`.
- **AC-7**: Every hourly job for a `Dropping` case reads the site's status from the Frappe Cloud API. `Archived` makes the case `Removed` with `removed_on`, and the Books Hosted Site `Removed`. With `archive_requested_on` empty and the site still Active (a crash before the save), AC-6's guards run again and the archive is called again. With `archive_requested_on` set, any status other than `Archived` only waits; the archive is never called twice from a set mark. The full order, the case row lock and the reconciliation of a later finish are in spec 0011 AC-2 and AC-11. A site already `Archived` when the archive is about to be called goes straight to `Removed` (safe to repeat). A Frappe Cloud API error or timeout is a `step_failed` for the drop; the third makes the case `Failed` with an ops email. A case still `Dropping` after 2 hours gets spec 0007 AC-21's alert, once per case.
- **AC-8**: Frappe Cloud takes an offsite backup when it archives a site and keeps its backups under its own retention. The export email and the zip's `README.txt` therefore don't say "no other copy is kept"; they say the hosting provider may keep backups of the site for a limited time under its own policy. No step deletes Frappe Cloud backups.
- **AC-9**: Books Removal Settings (a single on the control site, track changes, Removal Manager writes, System Manager reads) holds `mode` (off, dry_run, live; default off), `removal_paused`, `require_approval` (default on), `max_drops_per_day` (default 5), `books_bench_group` and `last_run_on` (read only). `removal_paused` stops every new export and drop at once. The pause and the daily cap are now global (spec 0007 had them per bench). Saving `mode` from `dry_run` to `live` cancels every open `dry_run` case and deletes its R2 object, so live starts with real warnings to real owners. Books Hosting Bench and every `bench` field are gone.
- **AC-10**: A Billing Manager registers a site from the Books Hosted Site list (Register site: Frappe Cloud site name, `owner_email`, `site_url`). The control site refuses, with a message and nothing written, a `site_url` that isn't `https://`, a site the Frappe Cloud API doesn't show in `books_bench_group`, the control site itself, and a site already registered (an Active one is left unchanged; a Removed one stays Removed; spec 0008 AC-1's "a repeat returns the same secret" no longer applies, since no secret is ever returned). Otherwise it creates the row with a fresh secret (`secrets.token_hex(32)`) and `config_status` Pending, and sets `books_control_url` (the control site's `books_control_public_url`) and `books_control_secret` on the site through the Frappe Cloud API, setting `config_sent_on`.
- **AC-11**: Every 5 minutes, one job (`job_id="books-config-ping"`, deduplicated) sends a signed `control_ping` to each Pending site with its new secret, and to each site with a pending rotation with `pending_secret`. This ping is the only confirmation that a config write took effect. A verified answer sets `config_status` Active (and, for a rotation, swaps the secret, AC-12). A site still Pending 1 hour after its config was sent becomes `config_status` Failed, and `books_ops_email` gets one email; the form's Retry config button sends the config again and returns it to Pending (during a rotation it sends `pending_secret` again, restarts `rotation_started_on` and leaves the site Active). Pushes and the removal round skip a site whose `config_status` isn't Active, and its `get_state` calls get a signed 409 `{"refusal": "config_pending"}` that doesn't count toward the signature failure alert; a rotation keeps the site Active throughout. A failed `update_config` at registration commits the row as `config_status` Failed with no `config_sent_on`, then raises (no ops email; the desk shows the error); Retry config, which always sends both keys, finishes it.
- **AC-12**: Rotate secret (Billing Manager) stores a new `pending_secret` and `rotation_started_on` and writes it as `books_control_secret` through the Frappe Cloud API. While it is pending, calls signed with either secret are accepted and each answer is signed with the secret that verified its request; pushes and removal calls use `control_secret`, and a removal call answered 401 is retried once with `pending_secret`. The first verified `control_ping` signed with `pending_secret` makes it `control_secret`, clears `pending_secret` and `rotation_started_on`, and queues a push; the swap runs under `for_update` on the Books Hosted Site row and only when `pending_secret` still equals the secret that was verified. After that only the new secret works. A rotation still pending after 1 hour emails `books_ops_email` once and keeps both secrets valid until the swap or a Retry config. Rotate secret is refused while `config_status` isn't Active ("use Retry config instead"). A failed `update_config` at rotation keeps `pending_secret` committed; Retry config sends it again.
- **AC-13**: The control site calls only three Frappe Cloud methods (`press.api.site.get`, `press.api.site.update_config`, `press.api.site.archive`), from one client module, with `Authorization: token <key>:<secret>` and `X-Press-Team`, a 30 second timeout, and the key read from the control site's `site_config.json`. No key, secret or upload URL is ever logged, put in an error, or shown in desk.
- **AC-14**: The control site runs on its own Frappe Cloud bench group on the same server, holding `rarebooks_control` only; the customer bench group holds `frappe_books` only and leaves `server_script_enabled` unset. The control site's System Settings `dormant_days` is 0 (set in `after_install`), and the hourly job emails `books_ops_email` once a day while it isn't. Its scheduler is enabled, Frappe Cloud's daily offsite backups are on, and an offline copy of its `encryption_key` exists. Spec 0008 AC-22's rate limits and signature failure alert still apply.
- **AC-15**: The bench commands (`books-removal-run`, `books-register-site`, `books-removal-check`, `books-removal-setup-bucket`), `commands.py`, `runner.py`, `registration.py`, `rollout.py` and their tests are removed from this repo, and the control site's `register_site`, `report_sites`, `drop_starting`, `drop_done` and `secret_rotated` runner endpoints are removed from `rarebooks_control`. Nothing reads `books_removal_mode`, `books-runner.json` or `books_runner_secrets` any more.
- **AC-16**: The daily digest of spec 0007 AC-21 shows `last_run_on`, and lists every site whose `config_status` isn't Active. The "bench hasn't reported for 3 hours" alert is replaced by "the last run is more than 3 hours old", checked by the 5 minute config job (one email a day while it holds). A dead scheduler stops that check too; the follow-up heartbeat covers it.
- **AC-17**: Rate limits: each customer site endpoint allows 60 calls a minute; the control site's `export_ready` and `step_failed` allow 60 calls a minute per site through spec 0008's per site cache counter, checked right after the signature. Spec 0008's per bench limits are gone with the bench.

## Decision

**Chosen option**: Option 2: the control site drives everything over signed HTTPS and the Frappe Cloud API; each customer site builds its own export in a background job and uploads it through a presigned URL.

The control site is the only actor with power to remove a site, and it can archive only a registered site on your Books bench group. Customer sites hold no R2 credential and no Frappe Cloud credential, only their own site secret.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `aws-sdk-python-usage` (`aws/agent-toolkit-for-aws`, `.agents/skills/aws-sdk-python-usage/`, for the presigned PUT and HEAD) · `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

Three parts: the customer site (this repo), the control site (`rarebooks_control`), and the Frappe Cloud API. The runner is gone.

**Data model sketch**:

Control site, **Books Removal Settings** (new single; track changes; Removal Manager writes, System Manager reads):

| Field | Type | Required | Notes |
|---|---|---|---|
| `mode` | Select: off, dry_run, live | yes | Default off |
| `removal_paused` | Check | no | Kill switch |
| `require_approval` | Check | no | Default 1 |
| `max_drops_per_day` | Int | yes | Default 5 |
| `books_bench_group` | Data | yes when mode isn't off | The Frappe Cloud bench group name whose sites may be archived |
| `last_run_on` | Datetime | no | UTC, read only |

Control site, **Books Hosted Site** (spec 0008), changed:

| Field | Change |
|---|---|
| `hosting_bench` | Removed |
| `config_status` | New. Select: Pending, Active, Failed. Default Pending. Read only |
| `config_sent_on` | New. Datetime UTC. When the config was last sent through the Frappe Cloud API |
| `rotation_started_on` | New. Datetime UTC. Set with `pending_secret`, cleared at the swap. Drives the 1 hour rotation alert |

**Books Removal Case** (spec 0007), changed: `bench` removed; `attempt_id` (Data, the current upload attempt) and `archive_requested_on` (Datetime UTC, read only, set once the archive call succeeds or times out after sending; spec 0011) added. Every other field and the state machine stay as in spec 0007; `Dropping` → `Removed` now comes from AC-7, not `drop_done`.

**Books Hosting Bench**: removed (a patch deletes the doctype; no live rows exist because rollout never ran).

Customer site: no schema change.

**Hourly round** (control site, `rarebooks_control.removal.run_round`, scheduled hourly; one job per site, `removal.run_site(site)`):

1. Read settings. `off` → log and stop. Set `last_run_on`.
2. For each Active site with `config_status` Active, enqueue `run_site` (deduplicated).
3. `run_site`: call `removal_report`; verify; apply spec 0007's case rules (open, later only date, cancel, warnings, export condition, email sent check, hold).
4. Instructions now become direct calls in the same job: `clear_removal`, `mark_export_sent` (live only), `start_export` (the per run cap of 3 is a cache counter `removal:exports:<run hour>`), and the drop (AC-6).
5. For a `Dropping` case, read the Frappe Cloud status (AC-7).

**API surface**:

Customer site, `frappe_books/subscription/remote.py` (new; guest, `@frappe.whitelist(allow_guest=True, methods=["POST"])`, `@rate_limit(limit=60, seconds=60)`, raw body signed per AC-2, every answer signed and echoing `issued_at`; exposed by short path from `frappe_books.subscription`):

| Endpoint | Key inputs | Key outputs | Notes | Key errors |
|---|---|---|---|---|
| `removal_report` | `issued_at` | spec 0007's `removal_status()` dict | Read only | 401 |
| `start_export` | `issued_at`, `case`, `attempt_id`, `upload_url` (must be `https://` on the R2 endpoint host), `expires_at` (ISO UTC) | `{status: "queued"}` | Enqueues `removal.export_job` | 401; 400 bad URL |
| `mark_export_sent` | `issued_at`, `export_sent_on`, `removal_hold_until` | `{status}` | In `ALLOWED_METHODS` | 401 |
| `clear_removal` | `issued_at` | `{status}` | In `ALLOWED_METHODS` | 401 |
| `control_ping` | `issued_at` | `{site, status: "ok"}` | Proves the site has the secret | 401 |

`removal.export_job(case, attempt_id, upload_url, expires_at)` (long queue, not whitelisted, skipped by `lock_job`): AC-4, AC-5. It calls the control site through `control.call_control` (`export_ready`, `step_failed`), signed with the site secret.

Control site, `rarebooks_control.removal` (site calls; guest POST, signed with the site's secret, the per site rate limit of spec 0008):

| Endpoint | Key inputs | Key outputs | Key errors |
|---|---|---|---|
| `export_ready` | `site`, `issued_at`, `case`, `attempt_id`, `bytes`, `sha256` | signed `{status}` | 401; 409 case not `Exporting` or another `attempt_id`; 409 R2 size differs; 503 R2 error or timeout (the job retries) |
| `step_failed` | `site`, `issued_at`, `case`, `step` (`export`, `upload`), `error` (2,000 characters, scrubbed) | signed `{status}` | 401; 409 final case |

Control site desk actions (whitelisted, `frappe.only_for`):

| Method | Role | Effect | Errors |
|---|---|---|---|
| `register_site(site, owner_email, site_url)` | Billing Manager | AC-10 | 403; 417 with the refusal message |
| `retry_config(site)` | Billing Manager | Sends the config again, Pending; during a rotation sends `pending_secret`, restarts `rotation_started_on`, stays Active | 403; 417 Removed |
| `rotate_secret(site)` | Billing Manager | AC-12 | 403; 417 Removed, rotation pending, or `config_status` not Active |
| spec 0007's `approve_case`, `pause_case`, `resume_case`, `retry_case` | Removal Manager | unchanged | unchanged |

Frappe Cloud client, `rarebooks_control/providers/frappe_cloud.py`: `get_site(name)` (returns `name`, `status`, `group`; `group` is empty unless your team owns the bench group), `update_config(name, config: dict)` (sent as a JSON list of `{key, value, type}` rows; returns config rows, nothing stored), `archive(name)` (`force: false`; returns nothing). Base URL `https://frappecloud.com`.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| round | which sites | Books Hosted Site `status` Active and `config_status` Active |
| every site call | URL | Books Hosted Site `site_url` |
| every site call | secret | read fresh from the row before each call: `control_secret`, retried once with `pending_secret` after a 401 during a rotation; `pending_secret` for the rotation's `control_ping` |
| `start_export` | `attempt_id`, key | `uuid4()` on the control site; `exports/<case>/<attempt_id>.zip`, both stored on the case |
| `start_export` | `upload_url`, `expires_at` | boto3 `generate_presigned_url("put_object", ExpiresIn=21600)` with the control site's R2 read and write token (`books_export_storage`); `expires_at` = now plus 6 hours |
| run cap | exports started this run | atomic `frappe.cache.incrby("removal:exports:<UTC hour>")`, given back with a decrement when `start_export` fails to connect |
| stuck export | "no report" | case `export_claimed_on` older than 6 hours while `Exporting` |
| export job | start or refuse | `expires_at` minus now, at least 2 hours |
| `start_export` | the R2 host the site accepts | the host of `upload_url` must end in `.r2.cloudflarestorage.com` (a constant in `remote.py`) |
| export job | free disk | `shutil.disk_usage` of `sites/<site>/`, versus 2 × (database size + `public/files` + `private/files`) |
| export job | the 5,000,000,000 byte cap | a constant; below R2's single PUT limit |
| export job | the control site to call | `books_control_url` in the site's config |
| `export_ready` | size check | R2 HEAD `ContentLength` on the case's key |
| drop guard | bench group, status | `press.api.site.get(name)`: `group` (empty fails) and `status` |
| drop, poll | "the archive call was made" | case `archive_requested_on`, set to UTC now right after the call returns |
| `get_state` | config refusal | the calling site's `config_status` |
| drop guard | "not the control site" | `frappe.local.site` on the control site |
| drop | fresh status | `removal_report` in the same job, just before the archive call |
| `Dropping` → `Removed` | archived | `press.api.site.get(name)` status `Archived` |
| daily cap | today's count | cases with `drop_started_on` on the current UTC date, counted under `for_update` on Books Removal Settings |
| registration | secret | `secrets.token_hex(32)` |
| registration | site exists, its bench group | `press.api.site.get(name)` |
| registration | the config written | `{"books_control_url": <control site URL>, "books_control_secret": <secret>}` to `press.api.site.update_config` |
| registration | control site URL | `books_control_public_url` in the control site's `site_config.json` (`https`); after a domain change, Retry config sends it to every site |
| rotation alert | "pending over 1 hour" | `rotation_started_on` |
| registration alert | "Pending over 1 hour" | `config_sent_on` |
| stale run alert | "last run over 3 hours old" | Books Removal Settings `last_run_on`, read by the 5 minute config job |
| registration, rotation | done | a verified `control_ping` signed with the new secret |
| Frappe Cloud calls | credentials | control site `site_config.json`: `frappe_cloud_api_key`, `frappe_cloud_api_secret`, `frappe_cloud_team` |
| dormant check | value | control site System Settings `dormant_days` |
| export email, README | backup wording | fixed text (AC-8), translated |

**Key invariants**:
- Only the control site can start a removal, and only for a registered site in `books_bench_group` that isn't itself.
- Customer sites hold no R2 and no Frappe Cloud credential. A presigned URL works for one key for 6 hours.
- Nothing is archived before its `Dropping` row is committed, and nothing but a Frappe Cloud Active site passes the guards.
- No drop without spec 0007's full chain: a warning 24 hours before, a confirmed upload, a sent email, a 72 hour hold, approval while required, the daily cap, and fresh unpaid checks on both sides within the same job.
- The control site acts on no unsigned or mismatched answer from a site, and a site acts on no unsigned call.
- A site with `config_status` other than Active is never pushed, reported or removed.

**Security model**:
- The Frappe Cloud API key can act on every site of your team (per site limits weren't confirmed). It lives only in the control site's config, is used by one module, and is guarded by AC-6's checks. Treat it like a root password: keep it out of logs, and make a new key if it might have leaked.
- Site secrets are visible in each site's Config tab on the Frappe Cloud dashboard to your team members. Only you are on the team; adding a member grants them that.
- Both bench groups keep server scripts off, so tenant code can't read `site_config.json`.
- R2: the control site holds one read and write token for the export bucket only. Sites get presigned URLs, never a token.
- Personal data in exports: unchanged from spec 0007, plus Frappe Cloud's own backups of an archived site (AC-8).

**Configuration required**:
- Control site `site_config.json` (set on its Config tab): `frappe_cloud_api_key`, `frappe_cloud_api_secret`, `frappe_cloud_team`, `books_control_public_url`; `books_export_storage` now a read and write token. Remove `books_runner_secrets`, `books_removal_require_approval`, `books_removal_max_drops_per_day`.
- Control site: Books Removal Settings filled in; System Settings `dormant_days` 0; scheduler enabled.
- Frappe Cloud: an API key (Settings, API access); the control site on its own bench group.
- Customer sites: `books_control_url` and `books_control_secret` written by the control site (AC-10).
- Cloudflare R2: spec 0007's lifecycle rules, set once in the Cloudflare dashboard or with the `cf` CLI.

**Critical test scenarios**:
- Happy path, against a fake Frappe Cloud client and fake storage: a round reports a day 30 site, sends `start_export`, the job builds and PUTs, `export_ready` passes the HEAD check, the email is sent, `mark_export_sent` writes the fields, the hold passes, approval, fresh report, guards pass, archive, then `Archived` makes it `Removed`. Verifies **AC-1**, **AC-3**, **AC-4**, **AC-6**, **AC-7**.
- Signing: a site call with a bad signature or stale `issued_at` gets a signed 401; a site answer with a wrong echo is ignored and counts `error_runs`. Verifies **AC-2**.
- Locked site: every site endpoint works and the export job writes nothing, on a `locked` site. Verifies **AC-5**.
- Guards: the archive isn't called for a site in another bench group, a Suspended or Broken site, the control site's own name, an unregistered name, or when the fresh report shows `payment_pending`. Verifies **AC-6**.
- Crash safety: `Dropping` is committed before the archive call; a case `Dropping` with no `archive_requested_on` and the site still Active gets the archive called on the next run; one with it set and the site Pending gets no call. Verifies **AC-6**, **AC-7**.
- Stuck export: a case `Exporting` for 7 hours with no report counts one attempt and gets a new `attempt_id`; a job whose link has under 2 hours left refuses to start; an `export_ready` HEAD timeout answers 503 and the retry passes. Verifies **AC-3**, **AC-4**.
- Rotation during a round: a removal call answered 401 right after the swap succeeds on the retry; two overlapping pings swap once. Verifies **AC-11**, **AC-12**.
- Skipped site: a site with `config_status` Failed and a `Holding` case that pays is cancelled from the control site's billing state alone. Verifies **AC-1**.
- Cap under parallel jobs: six sites due on one day with a cap of 5 start exactly 5 drops. Verifies **AC-6**, **AC-9**.
- Failures: a too large zip, an expired upload URL, and three archive API errors each end where AC-4 and AC-7 say, with no secret or URL in the error text. Verifies **AC-4**, **AC-7**, **AC-13**.
- Registration: refused for http, wrong bench group, the control site and a duplicate; a good one goes Pending, then Active after a verified ping; no ping for an hour gives Failed and one email. Verifies **AC-10**, **AC-11**.
- Rotation: both secrets work while pending; the first ping with the new one swaps; afterwards the old one gets 401. Verifies **AC-12**.
- Mode: saving dry_run to live cancels open dry run cases; `off` makes no site call. Verifies **AC-1**, **AC-9**.
- Dormant: `dormant_days` 4 on the control site gives one alert a day. Verifies **AC-14**.
- Removed code: no module imports `runner`, `registration` or `rollout`, and `bench --help` lists no `books-` command. Verifies **AC-15**.

## Build plan

Tracer Bullet: Milestone 1 runs one export end to end from the control site's round to an uploaded zip, against a fake storage and a fake Frappe Cloud client, before the drop, registration or cleanup.

**Milestone 1: The thread, one export driven by the control site**
1. [x] This repo: `remote.py` with signed both ways `removal_report`, `start_export`, `mark_export_sent`, `clear_removal`, `control_ping`; the two writers in `ALLOWED_METHODS`; short path exports. Satisfies **AC-2**, **AC-5**.
2. [x] This repo: `removal.export_job` (link expiry check, disk check, build in `sites/<site>/books-removal/<case>/`, zip, size cap, PUT, `export_ready` with its 503 retries or `step_failed`, cleanup), and `lock_job` skipping it by name. Satisfies **AC-4**, **AC-5**.
3. [x] Control site: Books Removal Settings, the `bench` fields and Books Hosting Bench removed by a patch, `attempt_id` and `archive_job` on the case (`archive_job` becomes `archive_requested_on` in task 14). Satisfies **AC-9**.
4. [x] Control site: `run_round` and `run_site` replacing `report_sites` (call order, dry run rules, fresh secrets, the cancel for skipped sites), the presigned URL and `expires_at`, the atomic run cap, the 6 hour stuck export rule, `export_ready` with the HEAD check and 503, `step_failed`, both signed with site secrets and rate limited per site. Satisfies **AC-1**, **AC-3**, **AC-4**, **AC-17**.

**Milestone 2: The drop through Frappe Cloud**
5. [x] Control site: `providers/frappe_cloud.py` (get, update config, archive) with a fake for tests. Satisfies **AC-13**.
6. [x] Control site: the drop in `run_site` with the fresh report, the guards (Active status read right before), the cap under the settings row lock, commit then archive, the `Dropping` poll with the call again for a missing archive mark (`archive_requested_on` after task 14), repeat safe `Archived`. Satisfies **AC-6**, **AC-7**.
7. [x] Both repos: the backup wording in the export email and `README.txt`. Satisfies **AC-8**.

**Milestone 3: Registration and rotation through the API**
8. [x] Control site: `register_site` with `books_control_public_url`, `retry_config`, the deduplicated 5 minute ping job, `config_status` gating pushes and rounds, the 1 hour alerts and the stale run alert. Satisfies **AC-10**, **AC-11**, **AC-16**.
9. [x] Control site: rotation through `update_config`, `rotation_started_on`, the 401 retry with `pending_secret`, and the locked ping swap. Satisfies **AC-12**.

**Milestone 4: Cleanup and alerts**
10. [x] This repo: remove `commands.py`, `runner.py`, `registration.py`, `rollout.py` and their tests; update `frappe_books/subscription/AGENTS.md` notes through `/sync`. Control site: remove the runner endpoints. Satisfies **AC-15**.
11. [x] Control site: `dormant_days` in `after_install` and its daily alert, the digest's `last_run_on` and config status lines; this repo: the 60 a minute limits on the site endpoints. Satisfies **AC-14**, **AC-16**, **AC-17**.
14. [x] Control site: spec 0011's build plan (`archive_requested_on` replacing `archive_job`, `config_job` removed, the drop and poll under the case row lock, the `Dropping` poll for every config status, the digest reconciliation, and the Milestone 3 fixes and tests against its AC-4 to AC-8). Numbered 14 to keep earlier task numbers stable; build it before Milestone 5. Satisfies **AC-1**, **AC-6**, **AC-7**, **AC-10**, **AC-11**, **AC-12**, **AC-16**.

**Milestone 5: Rollout on Frappe Cloud**
12. Frappe Cloud: the control bench group on your server with `rarebooks_control`, its site, config keys, scheduler, offsite backups, the offline `encryption_key`; the API key; R2 bucket, token and lifecycle rules; Books Removal Settings. Satisfies **AC-13**, **AC-14**.
13. Register a staging site, take it through day 30 with `set_hosted_phase` in `dry_run` (ops inbox checked, no archive), then archive one throwaway site in `live` with approval on. Satisfies **AC-6**, **AC-7**, **AC-10**, **AC-11**.

## Migration plan

**Strategy**: replace directly. The runner never ran in production (spec 0007's Milestone 5 and spec 0008's rollout weren't done), so no live data or schedule moves.
**Phases**:
1. Ship Milestones 1 to 4 to both repos with `mode` off.
2. Roll out on Frappe Cloud (Milestone 5), then `dry_run`, then `live`.
**Rollback**: set `mode` off. Removal stops at once; billing is untouched.
**Risks**: a Frappe Cloud API behaviour differs from the press source (the status shown while an archive runs, what a second archive call returns); task 5 confirms them against a real throwaway site before the live archive in task 13.

## Consequences

**Positive**:
- Runs entirely on Frappe Cloud with no server access, and no database root password or runner secret exists anywhere.
- Customer sites hold no storage or hosting credentials; the riskiest power (archive) sits in one guarded module on one site.
- Works on dormant sites, because enqueued jobs still run there.
- Registration and rotation need no copy and paste of secrets.

**Negative / tradeoffs**:
- One Frappe Cloud API key can act on every site in your team. AC-6's guards limit what the code does, not what a leaked key can do.
- A removed site isn't gone without a trace: Frappe Cloud keeps backups under its own policy, so the "no other copy" promise is dropped.
- Exports run on the customer bench's long workers and are capped at about 5 GB, since a single presigned PUT can't go bigger. A larger site needs your manual help.
- The control site's own scheduler is now the only clock for removals. If it stops, nothing alerts you except the daily digest (and that also runs on the scheduler).
- The 2 to 3 week old runner code and its tests are thrown away.

**Neutral**:
- Specs 0007 and 0008 carry a note pointing here for the parts this replaces.
- The `rarebooks_control` repo changes more than this one.

## Follow-up

- [x] From the press source (2026-11-20, spec 0011): `press.api.site.get` returns `name`, `status` and `group`; `update_config` and `archive` return no job name.
- [ ] At task 5, confirm against a throwaway Frappe Cloud site: the `Archived` status value, the status shown while an archive runs, what a second archive call returns, whether `books_` keys are in Frappe Cloud's blocked key list, and whether API keys can be limited to some sites.
- [ ] Confirm that the client IP Frappe sees behind Frappe Cloud's proxy is the real caller (spec 0008's per IP rate limits on webhooks and `go` depend on it).
- [ ] Ask Frappe Cloud support how long backups of an archived site are kept, and put the answer in the export email text.
- [ ] Add an outside heartbeat (an uptime check on a control site URL that reports `last_run_on`), so a dead scheduler alerts you.
- [ ] `/sync` after the build: root `AGENTS.md` and `frappe_books/subscription/AGENTS.md` still describe the runner, the secrets file and host cron.

## References

**Project sources**:
- Spec 0005 (the signed contract), spec 0007 (removal rules), spec 0008 (control site)
- `frappe_books/subscription/AGENTS.md`, `lock.py` (`ALLOWED_METHODS`, `lock_job`)

**Practices & standards**:
- Least privilege for credentials (presigned URLs instead of storage tokens on tenants)
- Fail closed on any doubt before an irreversible step

**Links** (web verified):
- Frappe Cloud press `api/site.py` (archive, update_config, get): https://raw.githubusercontent.com/frappe/press/master/press/api/site.py
- Frappe Cloud press `Site.archive` (offsite backup by default): https://raw.githubusercontent.com/frappe/press/master/press/press/doctype/site/site.py
- Frappe scheduler `is_dormant` (`dormant_days`, Frappe Cloud only): https://raw.githubusercontent.com/frappe/frappe/develop/frappe/utils/scheduler.py
- Frappe Cloud backups (retention of live sites): https://docs.frappe.io/cloud/sites/backups
