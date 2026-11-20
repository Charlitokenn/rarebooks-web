# 0011. Hosting on Frappe Cloud: marking the archive call and the config rules

**Date**: 2026-11-20
**Status**: In Progress
**Authorized by**: Charles Nkonoki, during /develop; ratified through /architect on 2026-11-20

Amends: spec [0010](0010-frappe-cloud-hosting/index.md) (AC-1, AC-6, AC-7, AC-10, AC-11, AC-12, AC-16, the data model, the desk actions, the Frappe Cloud client). Every other rule in spec 0010 still holds.

## Summary

Frappe Cloud's archive call gives back no job name, so the removal case can't store one. Instead, the case records the time the archive was requested, in a proper date and time field called `archive_requested_on`. A case with that time set only waits for Frappe Cloud to finish; a case without it (a crash before the save, or a clear error) may call the archive again after every check passes again. This spec also confirms four rules /develop chose for registration and secret rotation, and removes the `config_job` field, which could never be filled either.

## Context

Spec 0010 assumed two Frappe Cloud methods return a job name: `press.api.site.archive` (stored in `archive_job`) and `press.api.site.update_config` (stored in `config_job`). The press source (`press/api/site.py`, read 2026-11-20) shows neither does: `archive(name, force)` returns nothing, and `update_config` returns the site's config rows. AC-7 used an empty `archive_job` to mean "the archive call was never made", so without a value to store, the crash recovery of AC-6 and AC-7 had nothing to read.

/develop built Milestones 2 and 3 on an assumption: store the text `requested <UTC ISO time>` in `archive_job`. The behaviour was sound, but the field kept a name that lies ("job") and a type that hides a timestamp inside a string. Nothing is live yet (Books Removal Settings `mode` is off and the rollout in spec 0010 Milestone 5 hasn't run), so a schema fix needs no data move.

Milestone 3 also left four gaps where spec 0010's wording allowed more than one reading: what Retry config sends during a rotation, how `get_state` answers a site that isn't configured yet, whether a rotation may start on such a site, and what a failed `update_config` leaves behind at registration.

The archive is the one irreversible step in the product. Any rule here must fail closed: when in doubt, wait and alert rather than act. Every Datetime here follows the project's convention: UTC, stored naive, which holds because the control site's System Settings time zone is UTC.

## Requirements

**User stories**:
- As the operator, I want a crash or a timeout at any point of a drop to end in either a finished archive or an alert, never a lost, silent or doubled case.
- As the operator, I want a site that isn't configured yet to stay out of rotation and removal, and to show me plainly how to finish it.

**Acceptance criteria** (these refine the spec 0010 ACs named in brackets):
- **AC-1** [0010 AC-6]: The client sends `archive` with `force: false`. When the call returns a success, **or** ends in a timeout or a dropped connection after the request was sent (the outcome is unknown, so it counts as requested), the job sets the case's `archive_requested_on` to now and commits it in its own commit, retrying that save up to 3 times and logging an error with the site and case names if all fail. Only a clear error response from Frappe Cloud (an HTTP error status, or a connection that failed before the request was sent) leaves `archive_requested_on` empty and counts one `step_failed` for the drop. Nothing else is stored from the call.
- **AC-2** [0010 AC-7]: For a `Dropping` case, each hourly job first locks the case row (`for_update`) and reads `archive_requested_on`, then reads the site from `press.api.site.get`, in this order:
  1. A Frappe Cloud API error or timeout on that read counts one `step_failed` for the drop; the third makes the case `Failed` with an ops email (0010 AC-7).
  2. Status `Archived`: the case becomes `Removed` with `removed_on` set to now, and the Books Hosted Site becomes `Removed`, whatever its `config_status`. The same applies when the site is already `Archived` just before an archive call (0010 AC-7).
  3. `archive_requested_on` set, any other status (Active, Pending, Broken or anything else): wait. The archive is never called again.
  4. `archive_requested_on` empty, status Active: run every 0010 AC-6 guard and the fresh `removal_report` again, then call the archive (AC-1).
  5. `archive_requested_on` empty, any other status: wait.
  Waiting counts no attempt; a repeat archive call counts like any call. The row lock is held from the read of `archive_requested_on` until it is saved or the job decides to wait, so an hourly job and a desk Retry can't both call. A case still `Dropping` 2 hours after `drop_started_on` gets spec 0007 AC-21's alert, once per case, using that AC's own flag.
- **AC-3** [0010 AC-6]: The drop guard reads `name`, `status` and `group` from `press.api.site.get`. `group` must equal Books Removal Settings `books_bench_group` exactly (the same value Frappe Cloud returns in `group`); an empty `group` (Frappe Cloud leaves it empty unless your team owns the bench group) fails the check, so no archive.
- **AC-4** [0010 AC-11, AC-12]: Retry config always sends both `books_control_url` and `books_control_secret`, and never runs the registration checks again. With a pending rotation it sends `pending_secret` as the secret, sets `rotation_started_on` to now, and leaves `config_status` Active and `config_sent_on` unchanged; both secrets stay valid. Without a rotation it sends `control_secret`, sets `config_sent_on` to now and `config_status` Pending, on any site that isn't Removed, an Active one included (the next verified ping makes it Active again; this is how a control site domain change reaches every site).
- **AC-5** [0010 AC-11]: A `get_state` call from a site whose `config_status` isn't Active, with a valid signature, gets a 409 `{"refusal": "config_pending"}` signed with the secret that verified the request. It doesn't count toward spec 0008's signature failure alert. The customer site treats it as "unreachable" (no state change). A caller without a valid secret still gets 401.
- **AC-6** [0010 AC-12]: Rotate secret is refused with 417 "use Retry config instead" while `config_status` isn't Active, on top of 0010 AC-12's refusals (Removed, rotation already pending).
- **AC-7** [0010 AC-10]: When `update_config` fails (an error or timeout) during Register site, the row and its secret are committed with `config_status` Failed and `config_sent_on` empty, and only then does the call raise with "Frappe Cloud didn't take the config; use Retry config" (no key, secret or URL in the text, per 0010 AC-13). No ops email is sent (you see it at the desk; the digest lists it per 0010 AC-16), and the 5 minute ping job skips it until a Retry config. Retry config finishes it.
- **AC-8** [0010 AC-12]: When `update_config` fails during Rotate secret, the new `pending_secret` and `rotation_started_on` are committed, then the call raises with the same kind of message. Retry config sends the pending secret again (AC-4). The 1 hour rotation alert runs from `rotation_started_on` either way.
- **AC-9**: Books Removal Case has no `archive_job` field and Books Hosted Site has no `config_job` field. No patch copies data (no live rows exist).
- **AC-10** [0010 AC-1]: The hourly round enqueues the job for every site with a `Dropping` case, whatever its `config_status` and Books Hosted Site status. That job only does AC-2 (it calls Frappe Cloud, never the site).
- **AC-11** [0010 AC-16]: The daily digest reads `press.api.site.get` for every `Failed` case whose `drop_started_on` is set. When the site shows `Archived`, the case becomes `Removed` with `removed_on`, the Books Hosted Site `Removed`, and the digest lists it as "archived after failing". An API error leaves it for the next day.

## Options considered

### Option 1: Keep `archive_job` holding `requested <time>` (as built)

**Pros**: no schema change, already built and tested.
**Cons**: the field name says "job" and its type is text, so every reader has to know the convention; a timestamp parsed out of a string is a quiet bug source.

### Option 2: A typed `archive_requested_on` Datetime replacing `archive_job` (chosen)

**Pros**: the name and type say exactly what is stored; it matches `drop_started_on`, `removed_on` and the other case timestamps.
**Cons**: small code edits in `rarebooks_control` after Milestone 2 was ticked.

### Option 3: Keep `archive_job` and add `archive_requested_on`

**Pros**: a slot ready if Frappe Cloud ever returns a job name.
**Cons**: one field always empty today, which is exactly the problem `config_job` already has.

For the timing of the mark, writing it **before** the call (an intent mark) was weighed against writing it **after** the call. Before never repeats a call, but a crash right after the commit leaves a site that is never archived until a person steps in. After heals itself; its worst case is a second archive request for the same site under the same fresh guards.

## Decision

**Chosen option**: Option 2: `archive_requested_on` (Datetime, UTC) replaces `archive_job`, written once the archive call succeeds or its outcome is unknown; `config_job` is removed. The four Milestone 3 rules (AC-4 to AC-8) are confirmed as built, with the commit before raise and the both keys rule made explicit. The `Dropping` poll no longer depends on config status (AC-10), and the digest reconciles a failed drop that Frappe Cloud finished later (AC-11).

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`)

## Rationale

The archive call returns nothing, so the only fact you own is "this job asked Frappe Cloud to archive at time T". A Datetime says that directly, and since no live rows exist, now is the cheapest moment the field will ever be fixed. Writing it after the call keeps the crash path self healing: a repeat call only happens with the site still Active and every AC-6 guard passed again, under a row lock, so it can only ask Frappe Cloud to archive the same site twice. A timeout is treated as a request because the irreversible side may already have happened; guessing "not sent" would invite a double call, while guessing "sent" costs at most a 2 hour alert. Once the mark is set, the job never calls again, and an archive that stalls in any status is an alert, not an automatic action.

The four Milestone 3 rules share one idea: only a verified `control_ping` proves which secret a site holds. So a rotation keeps both secrets alive until that proof (AC-4, AC-8), a site without that proof is neither rotated (AC-6) nor served state (AC-5), and a failed config write is kept visible as Failed rather than hidden by a rollback that could orphan a secret already written on the site (AC-7). The signed 409 keeps a slow registration from setting off the signature failure alert, which should mean "someone has the wrong secret", not "setup isn't finished".

The runner up for the field was Option 1, kept only if the change had to touch live data; it doesn't.

## Feature design

**Data model change** (control site, `rarebooks_control`):

| Doctype | Field | Change |
|---|---|---|
| Books Removal Case | `archive_job` | Removed |
| Books Removal Case | `archive_requested_on` | New. Datetime UTC, read only. Set when the archive call succeeds or times out after sending |
| Books Hosted Site | `config_job` | Removed |

**State handling for a `Dropping` case** (each hourly job, case row locked; checked top to bottom, first match wins):

| `archive_requested_on` | Frappe Cloud read | Action |
|---|---|---|
| any | API error or timeout | `step_failed` for the drop; third makes it `Failed` with an ops email |
| any | `Archived` | case `Removed`, `removed_on`; Books Hosted Site `Removed` |
| set | any other status | wait |
| empty | Active | 0010 AC-6 guards and fresh report again, then archive (AC-1) |
| empty | any other status | wait |

In every row, a case still `Dropping` 2 hours after `drop_started_on` gets spec 0007 AC-21's alert once.

**API surface changes**:

| Method | Change |
|---|---|
| `get_state` (control site, called by customer sites) | Signed 409 `{"refusal": "config_pending"}` when `config_status` isn't Active (AC-5) |
| `retry_config(site)` | Sends both keys. During a rotation: `pending_secret`, restart `rotation_started_on`, stay Active. Otherwise: `control_secret`, `config_sent_on` now, Pending (AC-4) |
| `rotate_secret(site)` | New refusal: 417 when `config_status` isn't Active (AC-6); a failed write commits, then raises (AC-8) |
| `register_site(...)` | A failed `update_config` commits the Failed row, then raises (AC-7) |
| `providers/frappe_cloud.py` | `get_site` returns `name`, `status`, `group`; `update_config(name, rows)` sends a JSON list of `{key, value, type}` and returns nothing the caller stores; `archive(name)` sends `force: false`, returns nothing, and tells the caller apart "error response" from "unknown outcome" (timeout or reset after sending) |
| `run_round` | Also enqueues the job for sites with a `Dropping` case, whatever their config status (AC-10) |
| daily digest | Reconciles `Failed` drop cases whose site shows `Archived` (AC-11) |

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| drop | "the archive was requested" | case `archive_requested_on` |
| drop | time written | `frappe.utils.now_datetime()`, which is UTC because the control site's System Settings time zone is UTC |
| drop | "unknown outcome" | the client's own classification: a timeout or a reset after the request was sent |
| poll | site status | `press.api.site.get(name)["status"]` |
| drop guard | bench group | `press.api.site.get(name)["group"]`, compared with `books_bench_group`; empty fails |
| 2 hour alert | clock, flag | `drop_started_on`; spec 0007 AC-21's once per case flag |
| retry config | which secret | `pending_secret` when set, else `control_secret` |
| retry config | control site URL | `books_control_public_url` in the control site's `site_config.json` |
| retry config | rotation clock | `rotation_started_on` set to now during a rotation |
| `get_state` | refusal | `config_status` of the calling site's row |
| round | sites to poll for a drop | Books Removal Case `status` `Dropping`, joined to its site |
| digest | failed drops to reconcile | Books Removal Case `status` `Failed` with `drop_started_on` set |

**Key invariants**:
- An archive call is never made for a case whose `archive_requested_on` is set.
- An archive call is made only after every 0010 AC-6 guard passes in the same job, under the case row lock, the repeat call included.
- A `Dropping` case is polled every hour whatever its site's config status.
- A site's secret changes only on a verified `control_ping` signed with `pending_secret`.
- A site whose `config_status` isn't Active is never rotated and never served state.
- A desk action that fails at Frappe Cloud commits what it already wrote before it raises.

**Security model**: unchanged from spec 0010. The 409 is signed with the secret that verified the request, so it reveals nothing to a caller without a valid secret (that caller still gets 401). Error texts shown at the desk carry no key, secret or URL (0010 AC-13).

**Configuration required**: none new. The control site's System Settings time zone must be UTC (already assumed by specs 0007, 0008 and 0010; see Follow-up).

**Critical test scenarios**:
- A successful archive call sets `archive_requested_on`; the next poll with status Pending waits and makes no call. Verifies **AC-1**, **AC-2**.
- An archive call that times out after sending sets `archive_requested_on` and counts no `step_failed`; an HTTP 500 leaves it empty and counts one. Verifies **AC-1**.
- The mark save fails twice then succeeds: one mark, no second call. Verifies **AC-1**.
- A crash after the call (call succeeds, every save raises) leaves no mark and an error log; the next run with the site Active runs the guards and calls again. Verifies **AC-1**, **AC-2**.
- Two jobs for the same `Dropping` case at once: one archive call. Verifies **AC-2**.
- Mark set, status Broken past 2 hours after `drop_started_on`: one alert, no call. Verifies **AC-2**.
- `group` empty, or different from `books_bench_group`: no archive call. Verifies **AC-3**.
- Retry config mid rotation sends both keys with `pending_secret` and restarts the clock; both secrets still verify. Verifies **AC-4**.
- Retry config on a healthy Active site sends `control_secret`, goes Pending, and the next ping makes it Active. Verifies **AC-4**.
- `get_state` from a Pending site gets a signed 409 and the signature failure counter doesn't move. Verifies **AC-5**.
- Rotate secret on a Failed site gets 417. Verifies **AC-6**.
- `update_config` timeout at registration leaves a committed Failed row with no `config_sent_on`, raises a message with no secret in it, sends no email, and isn't pinged; Retry config makes it Pending. Verifies **AC-7**.
- `update_config` error at rotation keeps `pending_secret` committed; Retry config sends it. Verifies **AC-8**.
- After migrate, neither `archive_job` nor `config_job` is on its doctype. Verifies **AC-9**.
- A `Dropping` case on a site whose `config_status` is Failed is still polled and goes `Removed` when the site shows `Archived`. Verifies **AC-10**.
- A `Failed` drop case whose site later shows `Archived` becomes `Removed` at the next digest. Verifies **AC-11**.

## Build plan

Tracer Bullet: one small slice through the schema, the drop code and its tests, in `rarebooks_control`, then the round and digest edges, then the Milestone 3 checks.

1. Control site: add `archive_requested_on` to Books Removal Case, remove `archive_job` there and `config_job` from Books Hosted Site (doctype JSON only, no data patch). Satisfies **AC-9**.
2. Control site: `providers/frappe_cloud.py` tells an error response apart from an unknown outcome; the drop and the `Dropping` poll follow AC-1 and the state table under `for_update` on the case, with the retried mark save; empty or different `group` fails the guard. Satisfies **AC-1**, **AC-2**, **AC-3**.
3. Control site: `run_round` enqueues the job for every `Dropping` case whatever its config status; the digest reconciles `Failed` drop cases that show `Archived`. Satisfies **AC-10**, **AC-11**.
4. Control site: Retry config sends both keys; `register_site` and `rotate_secret` commit before raising; the ping job skips a Failed site with no `config_sent_on`. Check the existing Milestone 3 tests against AC-4 to AC-8 and add what is missing. Satisfies **AC-4**, **AC-5**, **AC-6**, **AC-7**, **AC-8**.

## Migration plan

**Strategy**: no migration needed. A field change on a system with no live rows.
**Phases**:
1. Ship tasks 1 to 4 with Books Removal Settings `mode` still off, before spec 0010 Milestone 5.
**Rollback**: revert the commit. The old `archive_job` column stays in the database (Frappe doesn't drop columns of removed fields until `bench trim-tables`), so a revert loses nothing.
**Risks**: a dev database with a `Dropping` test case loses its old mark; reset such cases by hand.

## Consequences

**Positive**:
- The case schema states plainly what you know about an archive, and crash recovery reads one typed field under a row lock.
- No automatic action follows an archive request except reading its status; every stall becomes an alert, and a late finish is reconciled.
- The registration and rotation rules now have one written reason, so later changes have something to check against.

**Negative / tradeoffs**:
- Milestone 2 and 3 code and tests in `rarebooks_control` are reopened.
- A timeout where Frappe Cloud never actually received the request leaves the site unarchived until the 2 hour alert makes you step in.
- A process kill between a successful call and the save can still send Frappe Cloud a second archive request. If Frappe Cloud refuses it, three such refusals make the case `Failed`; the digest then reconciles it once the site shows `Archived`.
- Retry config on a healthy site takes it out of rounds and `get_state` until the next ping (up to 5 minutes).
- A site whose archive stalls in a non Active status waits for you; nothing retries it.

**Neutral**:
- Spec 0010's ACs, data model, desk actions and client notes are edited to match this spec.

## Follow-up

- [ ] At spec 0010 task 5's throwaway site check, also note which status Frappe Cloud shows while an archive runs, and what a second archive call on that site returns. If it returns an error, consider treating that one error as "already archiving" instead of a `step_failed`, through `/architect`.
- [ ] The control site's System Settings time zone must be UTC: add a check in `after_install` and the daily alert next to `dormant_days` (spec 0010 AC-14), through `/architect` on spec 0010.
- [ ] A pending secret never expires, and there is no Cancel rotation action (spec 0010 AC-12). Decide an expiry or a cancel through `/architect`.
- [ ] Orphan columns: run `bench trim-tables` on the control site after the field removal, once the rollout is stable.
