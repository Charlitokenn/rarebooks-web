# 0013. Hosting on Frappe Cloud: proving a site is archived

**Date**: 2026-11-21
**Status**: In Progress

Amends: spec [0011](0011-archive-call-mark.md) (AC-2, the `Dropping` poll, and AC-11, the failed drop reconcile), spec [0010](0010-frappe-cloud-hosting/index.md) (AC-6 and AC-7, the same reads) and spec [0012](0012-custom-domains-registration/index.md) (AC-11: when the domain cleanup starts, and when its Frappe Cloud part is done). Every other rule in those specs still holds.

## Summary

The control site decides that a removal is finished when Frappe Cloud shows the site as `Archived`. A live check showed Frappe Cloud never says that to your team: about 30 seconds after an archive, the site disappears from your API key (`get` answers HTTP 403), and Frappe Cloud releases the site's own `.frappe.cloud` name (`domain_exists` answers `null`). This spec makes those two facts together the proof that a site is archived, but only for a drop the control site started, and keeps `Archived` as a second proof. The domain cleanup then starts only once a site is proven archived, and it counts a custom domain as gone once Frappe Cloud has released it. Without this spec, every real drop would end `Failed` with an alert instead of `Removed`.

## Context

The removal flow (specs 0007, 0010, 0011) ends with an archive on Frappe Cloud, the only irreversible step in the product. Three places then decide whether Frappe Cloud has finished: the read right before an archive call at the start of a drop (0010 AC-6), the hourly poll of a `Dropping` case (0010 AC-7, 0011 AC-2), and the daily reconcile of a `Failed` drop (0011 AC-11). All three read `press.api.site.get` and wait for status `Archived`. Spec 0012's domain cleanup (AC-11) starts when the archive is marked as requested, and counts the Frappe Cloud part done when Frappe Cloud shows the site archived, says it can't find it, or no longer lists the domain.

On 2026-11-21 a throwaway site, `rbdomaincheck.frappe.cloud`, went through a real archive with the control site's own client code. Right after the call, `get` answered status `Pending` and `domains` still listed both domains. About 30 seconds later, and every time after that: `get` answered HTTP 403, `domains` answered HTTP 403, `remove_domain` answered HTTP 403, and `domain_exists` answered `null` for both the custom domain and the site's own `.frappe.cloud` name. The site list (`press.api.site.all`) doesn't show archived sites with any filter. For comparison, `domain_exists("demo-site.frappe.cloud")` on a live site answers its own name. The same check confirmed the domain methods spec 0012 relies on, and the certificate on the custom domain was valid in a browser.

So with your team's key, `Archived` is never seen. As built, a real drop would count a `step_failed` on each hourly poll (a 403 is an API error), become `Failed` with an ops email after three hours, and then never be reconciled, because the daily reconcile also waits for `Archived`. Spec 0012's cleanup would retry every hour and send its 24 hour alert.

HTTP 403 means more than one thing: "this site is no longer visible to your team", "your key is wrong or revoked", and possibly "this name no longer belongs to the site", if Frappe Cloud renames a live site. The rule must fail closed: marking a live site `Removed` stops its billing, pushes and removal on the control site while the customer keeps using it. A second risk sits in spec 0012's cleanup: an archive call whose outcome is unknown counts as requested (0011 AC-1), so the cleanup can start, and delete the DNS record behind a site's primary address, while Frappe Cloud may never have received the archive. This spec doesn't change Frappe Cloud or the customer site; it only changes how the control site reads Frappe Cloud's answers.

## Requirements

**User stories**:
- As the operator, I want a drop that Frappe Cloud really finished to end `Removed` on its own, so a normal removal sends me no false alert.
- As the operator, I want a wrong or revoked Frappe Cloud key, or a renamed site, never to mark a live site removed, so no paying customer is dropped from the registry by mistake.
- As the operator, I want a site's custom domain to stay in place until the site is proven archived, then be cleaned up once Frappe Cloud has released it.

**Acceptance criteria** (these refine the spec ACs named in brackets):
- **AC-1**: A site counts as **proven archived** on Frappe Cloud only when, in the same job, either (a) `press.api.site.get` answers HTTP 200 with status `Archived`, or (b) the Books Removal Case being checked has `drop_started_on` set, `press.api.site.get` answers HTTP 403, **and** `press.api.site.domain_exists` for the site's own name (the case's `site`, for example `x.frappe.cloud`) then answers `null`. `domain_exists` is asked only after a 403, and only for a case with `drop_started_on` set. Nothing else is proof: any other HTTP error, a timeout, a 403 on a case with no `drop_started_on`, a 403 where `domain_exists` names any site, or an error from `domain_exists` itself means "not proven".
- **AC-2** [0011 AC-2, 0010 AC-7]: Each hourly job for a `Dropping` case locks the case row, makes its one Frappe Cloud read through AC-1, then acts in this order, first match wins:
  1. Proven archived: `mark_removed` (the case `Removed` with `removed_on` now, then the Books Hosted Site `Removed`), whatever `archive_requested_on` holds and whatever the row's `config_status`.
  2. Not proven, with an error (a 403 not confirmed by `domain_exists`, any other `get` error, or an error from `domain_exists`): one `step_failed` for the drop; the third makes the case `Failed` with an ops email, as today.
  3. Any other `get` answer: the rest of 0011 AC-2's table, unchanged (`archive_requested_on` set waits; empty and Active runs every guard and the fresh report again, then calls the archive; empty and any other status waits). There is no second read before that archive call.
- **AC-3** [0010 AC-6]: At the start of a drop, before `Dropping` and `drop_started_on` are saved, the read of the site right before the archive call accepts proof (a) only. `Archived` there means no archive call and the case goes `Removed` (0011's existing rule, safe to repeat). A 403 there counts one `step_failed` (through `drop_failed`), as any API error there does today: no archive call, no `Removed`. This read stays after `drop_refusal` and the fresh report, as now.
- **AC-4** [0011 AC-11]: The daily digest's reconcile of each `Failed` case with `drop_started_on` set uses AC-1. Proven archived: `mark_removed`, and the digest lists it as "archived after failing". Anything else, error or not, leaves it for the next day, with no alert.
- **AC-5** [0012 AC-11]: The domain cleanup starts only in `mark_removed`, in the same transaction that makes the Books Hosted Site `Removed`. Setting `archive_requested_on` no longer starts it. The start rule is otherwise 0012's: a row with a `subdomain`, no `domain_cleaned_on` and `domain_step` not already Cleanup gets `domain_step` Cleanup, `domain_status` Working and `domain_step_started_on` now, with no outside call; a repeat changes nothing. The 24 hour cleanup alert runs from that start.
- **AC-6** [0012 AC-11]: The cleanup sweep counts the Frappe Cloud part of a domain cleanup as done when `domain_exists(<subdomain>.<books_site_domain>)` answers `null`, or names a site other than the row's `site` (compared ignoring case and a trailing dot). While it names the row's `site`, the sweep calls `remove_domain` for it when `domains(site)` lists it as not primary, and otherwise waits (including while `domains` answers 403). Any error waits for the next hourly sweep. A 404 is no longer "done". The site's archive proof isn't asked for this part, and the Cloudflare part's rules are unchanged. The sweep and the `Dropping` poll are independent: neither reads the other's result, so their order in the hourly round doesn't matter.
- **AC-7**: A case made `Removed` by proof (b) logs one info line, written by the caller (the poll or the reconcile), naming the case, the site and "403 and name released", so you can tell it apart from proof (a) in the logs. No new email: a normal removal is reported by the existing daily digest.
- **AC-8**: A "not proven" error carries a text that tells the cases apart, for the case's `last_error` and the ops email: "get answered HTTP 403 and the site's name is still held", "get answered HTTP 403 and domain_exists failed" (with its HTTP status or "no answer"), or the client's own text for any other error. No text names the site holding a name, since it may belong to another team, and none carries a key, secret or config value (0010 AC-13).
- **AC-9**: Before the first live drop of spec 0010's rollout: (1) one throwaway site with a subdomain goes through the real drop in `live` mode, reaches `Removed` by proof (b) within two hourly runs after the archive call, and its domain cleanup then finishes; (2) a read only call of `get` and `domain_exists` with a deliberately wrong key (run by the operator, outside the proxy that injects the real key) shows both fail with an error and neither answers `null`.

## Options considered

### Option 1: Keep waiting for `Archived`

Keep 0011's rule and ask Frappe Cloud support whether archived sites can be shown to the team.

**Pros**:
- No code change; the most explicit signal there could be.

**Cons**:
- Frappe Cloud doesn't send it today, so every real drop ends `Failed` with an alert and stays that way, and every removal needs you by hand.
- Depends on a vendor change with no date.

### Option 2: HTTP 403 plus the site's own name released, for drops we started (chosen)

Treat a 403 from `get` as proof only for a case whose drop the control site started, and only when `domain_exists` for the site's own `.frappe.cloud` name answers `null` in the same job. Keep `Archived` as a second proof.

**Pros**:
- Two facts, plus our own record that we started the drop. A wrong or revoked key can't fake the released name, and a renamed live site can't reach proof (b) unless we had started dropping it.
- Works for every site, custom domain or not, because Frappe Cloud stores each site's own name as a domain and releases it at archive.
- Already seen on the live API, within about 30 seconds of the archive.

**Cons**:
- Rests on behaviours Frappe Cloud doesn't document: archived sites turning 403 for the team, and their names being released.
- A site archived by hand before any drop started doesn't close itself.
- One extra API call on each poll that gets a 403.

### Option 3: HTTP 403 plus a key check

Treat a 403 as proof when a call for another site (the control site itself) succeeds in the same job, which shows the key works.

**Pros**:
- Doesn't depend on how Frappe Cloud releases names.

**Cons**:
- A 403 can also mean the site moved to another team or was renamed; a working key elsewhere doesn't rule those out.
- No positive sign that the archive happened, only that the key works.

### Option 4: The released name alone

Count `domain_exists(site)` answering `null` as proof, whatever `get` answers.

**Pros**:
- One call, the simplest rule.

**Cons**:
- A single fact. If Frappe Cloud ever releases or renames a live site's name for another reason (a rename, a migration), a live site would count as removed.

## Decision

**Chosen option**: Option 2: HTTP 403 plus the site's own name released, for drops we started, with `Archived` kept as a second proof

A site counts as archived when `get` shows `Archived`, or, for a case whose drop the control site started, when `get` answers 403 and `domain_exists` for the site's own name answers `null` in the same job. The `Dropping` poll and the daily reconcile use that rule, the read at drop start accepts `Archived` only, and spec 0012's cleanup starts once a site is proven archived and counts a custom domain gone once Frappe Cloud has released it.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`)

## Rationale

The rule has to fail closed, because marking a live site `Removed` stops its billing, pushes and removal on the control site while the customer keeps using it. A 403 alone can't carry that weight: it also means a revoked key, and maybe a renamed site. The released name is a separate fact that a broken key can't produce, since an unauthorized `domain_exists` call fails instead of answering `null` (AC-9 checks that before the first live drop). Limiting proof (b) to cases with `drop_started_on` set closes the rename gap: a renamed site can release its old name, but the control site only accepts that as an archive when it had itself started dropping that exact site. Option 3 was the runner up: it shows the key works, but not that the archive happened. Option 4 drops the second fact for one saved call, which is a poor trade on the one irreversible step.

Keeping `Archived` as a second proof costs nothing. It keeps every existing test and the 0011 table valid, and it covers Frappe Cloud showing archived sites to teams again later. A 403 without the released name still counts a `step_failed`, as any API error does today. The window between the 403 and the released name is under a minute against hourly polls, so a real archive clears it on the next poll. A revoked key still reaches `Failed` with an ops email after three hours, which is the alert you want for that case, and the daily reconcile finishes a case that failed during the window. Marking a `Dropping` case `Removed` when the proof holds without `archive_requested_on` (a mark save that failed) extends 0011's existing rule; the price of the `drop_started_on` limit is that a site someone archived by hand before any drop started waits for you instead of closing itself.

Moving the cleanup start to `mark_removed` fixes a real hazard: 0011 counts an archive with an unknown outcome as requested, so the old start could delete the DNS record behind a still running site's primary address if Frappe Cloud never got the call. Waiting for the proof costs at most one hourly run of name exposure, which is small next to breaking a live customer's address. For the Frappe Cloud part of the cleanup, `domain_exists` answers the real question directly ("is this name still held by our site?"), so one rule covers an archived site and a live one whose domain was removed by hand.

## Feature design

**Data model**: no change. No field is added, removed or retyped, and no data is moved.

**The proof** (AC-1), checked top to bottom, first match wins:

| `get(site)` | Case has `drop_started_on` | `domain_exists(site)` | Result |
|---|---|---|---|
| HTTP 200, status `Archived` | any | not asked | proven archived, proof `"status"` |
| HTTP 200, any other status | any | not asked | not archived; the status is used as before |
| HTTP 403 | no | not asked | not proven (an error for the caller) |
| HTTP 403 | yes | `null` | proven archived, proof `"released"` |
| HTTP 403 | yes | names any site | not proven: "the site's name is still held" |
| HTTP 403 | yes | error or timeout | not proven: "domain_exists failed" |
| any other error or timeout | any | not asked | not proven (the client's own error) |

**State handling for a `Dropping` case** (replaces the top two rows of 0011's table; the others stay):

| `archive_requested_on` | Frappe Cloud read | Action |
|---|---|---|
| any | proven archived (`"status"` or `"released"`) | `mark_removed`; for `"released"`, one info log line (AC-7) |
| any | not proven error | `step_failed` with the AC-8 text; the third makes it `Failed` with an ops email |
| set | any other status | wait |
| empty | Active | 0010 AC-6 guards and a fresh report again, then archive |
| empty | any other status | wait |

The 2 hour `Dropping` alert (spec 0007 AC-21) is unchanged: it fires on a case still `Dropping` 2 hours after `drop_started_on`, whatever the reads answered, once per case with its own flag, and `Removed` ends it.

**Domain cleanup** (replaces 0012 AC-11's start rule and its Frappe Cloud done rule):

| Moment | Action |
|---|---|
| `archive_requested_on` set | nothing for the domain (it used to start the cleanup) |
| `mark_removed` | start the cleanup (AC-5) |
| sweep: `domain_exists(fqdn)` `null`, or names another site | Frappe Cloud part done |
| sweep: names the row's `site`, `domains` lists it not primary | `remove_domain`; done at a later sweep once `domain_exists` answers `null` |
| sweep: names the row's `site`, listed as primary, or `domains` fails | wait for the next sweep |
| sweep: `domain_exists` error or timeout | wait for the next sweep |

**API surface**: no new endpoint and no new Frappe Cloud method. The client already has `get_site`, `domain_exists` and `FrappeCloudError.status` (spec 0012). Where the code lives:

| Code | Change |
|---|---|
| `providers/frappe_cloud.py` | A `FORBIDDEN = 403` constant next to `NOT_FOUND`. |
| `removal.py` | A new `site_archived(site: str, drop_started: bool) -> tuple[str \| None, dict \| None]`. It returns `("status", cloud)` for proof (a), `("released", None)` for proof (b), and `(None, cloud)` for an HTTP 200 that isn't `Archived`. It raises `FrappeCloudError` with the AC-8 text for anything not proven. `poll_drop` calls it with `drop_started=True` and writes the AC-7 log line. The drop start read calls it with `drop_started=False`. |
| `removal.mark_removed` | Starts the domain cleanup (AC-5), as now. `_write_archive_mark` no longer calls `start_domain_cleanup`. |
| `removal_mail.reconcile_failed_drops` | Uses `site_archived(case.site, drop_started=True)` and writes the AC-7 log line. |
| `registry._remove_cloud_domain` | Follows the cleanup table; its `get_site`, `NOT_FOUND` and `Archived` checks go. `registry._check_bench_group` keeps failing on a 403, which is the right fail closed answer for the forward domain steps. |
| `tests/control.py` `FakeFrappeCloud` | Gains `own_names` (the site names `domain_exists` answers with their own name for, filled by `add`) and `finish_archive(name)`: from then on `get`, `domains` and `remove_domain` for that name answer 403, the name leaves `own_names` and its `domain_rows` are dropped, and any `errors` override still wins. |

**Locking**: the poll keeps 0011's case row lock across its read. With a 403 that is two outside calls (`get`, then `domain_exists`, each with the client's 30 second timeout) under the lock, which is accepted: the lock only stops a desk Retry and a second job on the same case. The lock order stays case row, then Books Hosted Site row (inside `mark_removed`). The reconcile does the same per case.

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| proof (a) | site status | `press.api.site.get(site)["status"]` |
| proof (b) | "we started this drop" | case `drop_started_on` is set |
| proof (b) | "the site is hidden from your team" | HTTP status 403 from `press.api.site.get(site)`, read from `FrappeCloudError.status` |
| proof (b) | "the site's name was released" | `press.api.site.domain_exists(site)` answering `null`, where `site` is the case's `site` |
| poll, drop start | which case, which site | the locked Books Removal Case and its `site`, always a registered Books Hosted Site whose bench group was checked at registration (spec 0010 AC-10) |
| poll | whether the archive was asked for | case `archive_requested_on` (0011) |
| removal | `removed_on` | now, UTC (0011's convention) |
| log line (AC-7) | which proof | the first value `site_archived` returns |
| error text (AC-8) | why not proven | the branch of the proof table that matched, and `domain_exists`'s HTTP status |
| reconcile | which cases | Books Removal Case `status` `Failed` with `drop_started_on` set (0011 AC-11) |
| cleanup start | when | `mark_removed` making the Books Hosted Site `Removed` |
| cleanup | full domain | `subdomain` + `.` + `books_site_domain` (spec 0012) |
| cleanup | who holds the domain | `press.api.site.domain_exists(fqdn)`, compared with the row's `site` ignoring case and a trailing dot |
| cleanup | listed and primary | `press.api.site.domains(site)` (spec 0012) |

**Key invariants**:
- A case is marked `Removed` only on proof (a), or on proof (b) for a case with `drop_started_on` set; never on a 403 alone, a timeout, or any other error.
- `domain_exists` is asked about the site's own name only after `get` answered 403 in the same job, for a case with `drop_started_on` set.
- No archive call is made for a site that is proven archived.
- Every 0011 invariant still holds: no archive call from a set `archive_requested_on`, and every call only after every guard passes under the case row lock.
- A custom domain's DNS record and Frappe Cloud domain are never removed before the site is proven archived (the cleanup starts only in `mark_removed`).
- The Frappe Cloud part of a domain cleanup is never done while `domain_exists` names the row's own `site`.

**Security model**: unchanged from specs 0010 and 0011. The rule only reads Frappe Cloud with the existing team key. Error texts and log lines name the method, the HTTP status, the case and the site, never a key, secret, config value or another team's site (AC-8).

**Configuration required**: none new.

**Tests that change** (in `rarebooks_control/tests/`):
- `test_removal.py`: the tests where `get` answers `Archived` (around lines 706, 895, 905 and 948) stay valid as proof (a). Add the proof (b) and "not proven" cases, using `finish_archive`.
- `test_domains.py`: the cleanup tests that rely on `Archived`, on a 404 meaning done, and on cleanup starting at the archive mark (`test_the_archive_mark_starts_cleanup_and_the_sweep_runs_with_mode_off`, `test_a_foreign_record_is_left_alone_and_a_site_frappe_cloud_cant_find_counts_as_gone`, and the ones calling `self.archived()`) move to `finish_archive`, the `domain_exists` done rule, and a start in `mark_removed`. `TestLabel`'s clash tests use `elsewhere`, and the fake's `own_names` must not make a free label look taken.
- Any assertion on the exact sequence of `("get", name)` calls in the fake: check it again, since a 403 now adds a `("domain_exists", name)` call.

**Critical test scenarios**:
- `get` answers `Archived`: proven (a), `mark_removed`, and `domain_exists` isn't called. Verifies **AC-1**, **AC-2**.
- `finish_archive` on a `Dropping` case: the next poll marks the case and the row `Removed` and logs the "403 and name released" line. Verifies **AC-1**, **AC-2**, **AC-7**.
- `get` answers 403 and `domain_exists` names the site (a revoked key, a renamed site, or the half minute window): one `step_failed` with "the site's name is still held"; three in a row make the case `Failed` with one ops email; the case and the row are never `Removed`. Verifies **AC-1**, **AC-2**, **AC-8**.
- `get` answers 403 and `domain_exists` times out: one `step_failed` with "domain_exists failed", not `Removed`. Verifies **AC-1**, **AC-8**.
- `get` answers 500: one `step_failed`, and `domain_exists` isn't called. Verifies **AC-1**, **AC-2**.
- A `Dropping` case with no `archive_requested_on` (a failed mark save) whose site then shows proof (b): `Removed`, and no archive call. Verifies **AC-2**.
- At drop start, `get` answers 403 with the name released: one `step_failed`, no archive call, no `Removed`. `get` answers `Archived`: `Removed`, no archive call. Verifies **AC-3**.
- A `Failed` case whose site later shows proof (b) becomes `Removed` at the next digest and is listed as "archived after failing"; one that shows a 403 with the name still held stays `Failed` and sends nothing. Verifies **AC-4**.
- Setting `archive_requested_on` leaves a site's domain fields untouched; `mark_removed` starts the cleanup, and a repeat doesn't restart its clock. Verifies **AC-5**.
- Domain cleanup: `domain_exists(fqdn)` `null` is done; held by another site is done; held by our site (in any letter case) and listed not primary calls `remove_domain` and is done at the next sweep; held and primary waits; `domains` 403 waits; an error waits; a 404 from `get` is not done. Verifies **AC-6**.
- No error text, `last_error` or log line holds a key, a secret or another team's site name. Verifies **AC-8**.
- The rollout drop and the wrong key check. Verifies **AC-9**.

## Build plan

Tracer Bullet: the proof first, through the poll and its tests (the path every real drop takes), then the other readers, then the cleanup start and done rules, then the live checks in the rollout. All tasks are in the `rarebooks_control` repo.

1. `FakeFrappeCloud` gains `own_names` and `finish_archive`. Add `FORBIDDEN`, `removal.site_archived` per AC-1 and AC-8, and use it in `poll_drop` with the AC-7 log line. Tests for the proof table and the poll. Satisfies **AC-1**, **AC-2**, **AC-7**, **AC-8**.
2. The drop start read calls `site_archived(..., drop_started=False)`: `Archived` goes `Removed` with no archive call, a 403 counts one `step_failed`. Satisfies **AC-3**.
3. `reconcile_failed_drops` uses `site_archived(case.site, drop_started=True)` with the log line. Satisfies **AC-4**, **AC-7**.
4. Spec 0012 cleanup: `_write_archive_mark` stops starting it, `mark_removed` keeps starting it, and `registry._remove_cloud_domain` follows the cleanup table. Move the cleanup tests listed above. Satisfies **AC-5**, **AC-6**.
5. Rollout: in spec 0010 Milestone 5, before the first real drop, run the wrong key check, then take one throwaway site with a subdomain through a live drop and check it reaches `Removed` by proof (b) and its domain cleanup finishes (this also closes spec 0012 task 12's archive check). Satisfies **AC-9**.

## Consequences

**Positive**:
- A real drop ends `Removed` on its own, so a normal removal needs no one and sends no false alert.
- A revoked or wrong key, or a renamed site, still can't mark a live site removed; they show up as `Failed` drops and an ops email, as before.
- A drop that failed partway is finished by the daily reconcile, so stuck cases clear themselves.
- A site's custom domain is never removed while the site might still be running.

**Negative / tradeoffs**:
- The rule rests on Frappe Cloud behaviours that aren't documented: archived sites turning 403 for the team, and their names being released. A change to either shows up as `Failed` drops and a 24 hour cleanup alert, never as a wrong `Removed`, because the rule fails closed. AC-9 checks them again before the first live drop.
- A site archived by hand before any drop started doesn't close itself: its open case waits at the drop start's fresh report check (the site can no longer answer) and never reaches the Frappe Cloud read, so you close it by hand (see Follow-up).
- If another team takes a released `.frappe.cloud` name before the poll sees the proof, `domain_exists` names their site, so the case stays not proven and ends `Failed`; you close it by hand. The window is about one hour.
- The custom domain stays in DNS for up to one more hourly run after the archive than before.
- A poll that gets a 403 makes one extra API call, and holds the case lock for up to two client timeouts.
- A 403 without the released name counts a `step_failed` even during the half minute archive window, so a case can show one attempt it didn't really fail.

**Neutral**:
- No schema change and no data move. Spec 0010 AC-6 and AC-7, spec 0011 AC-2 and AC-11, and spec 0012 AC-11 carry an "amended by spec 0013" note.
- Spec 0012's build task 1 (confirm the domain methods live) is answered by the 2026-11-21 check recorded in Context, apart from `retry_add_domain`, which the check never needed to call.

## Migration plan

**Strategy**: no migration needed. A read rule change, with no schema change and no live drops yet (Books Removal Settings `mode` is off).
**Phases**:
1. Ship tasks 1 to 4 with `mode` still off, before spec 0010 Milestone 5.
2. Run task 5 in the rollout before any real drop.
**Rollback**: revert the commit; the rule goes back to waiting for `Archived` alone, and the cleanup back to starting at the archive mark.
**Risks**: none for live data while `mode` is off. A dev database with a site in domain Cleanup started by an archive mark keeps it; the sweep finishes it under the new done rule.

## Follow-up

- [ ] A "Mark removed" desk action for a `Failed` case (Removal Manager, with a reason), for the cases this rule leaves to you: a site archived by hand before its drop, or a released name taken by another team. Decide its checks and what it writes through `/architect`.
- [ ] Ask Frappe Cloud support whether archived sites can be shown to the owning team (status `Archived` in `get` or in the site list). If they can, proof (a) becomes the main path and proof (b) stays as a backstop.
- [ ] `retry_add_domain` (spec 0012 AC-7) is still unchecked on the live API, because the certificate never broke. Watch the first `Broken` certificate in the logs.
