# 0016. Release a sign up so its email can be used again

**Date**: 2026-11-25
**Status**: Proposed

Amends: spec [0014](../0014-self-serve-onboarding/index.md) (AC-4 and AC-9: the Worker checks a D1 row against the control site and drops it when the control site no longer knows it; AC-20: a Released request counts as Ready, so its old site still gets its Trial and Lapsed cases; the key invariant "one Books Signup per `email_key`, per `clerk_user_id` and per subdomain, ever" becomes "among requests that are not Released"). Every other rule in spec 0014 still holds.

## Summary

Today one email can hold one hosted site, ever, and the only way round it is a hand made delete on two systems. This spec adds a **Release sign up** button for Billing Managers on a Ready or Failed Books Signup. A release asks for a reason, marks the request Released and frees its email, Clerk account and subdomain, so the person can sign up again; their old site is not touched. The marketing site learns of it on its next check, with no new message: it trusts the control site's answer and drops its stale copy (its D1 row, the Worker's small local record of each sign up).

## Requirements

**User stories**:
- As a Billing Manager, I want to release a person's sign up with a reason, so they can create another site with the same email and sign in, without editing two databases by hand.
- As that person, I want to sign up again from `/dashboard/start` as if I were new, so I can get my next site with no help.
- As the operator, I want every release kept with who, when and why, and the old site billed and removed by the usual rules, so a release never becomes a free, unrecorded trial.

**Acceptance criteria**:

*Control site (`rarebooks_control`)*

- **AC-1**: A Billing Manager sees a **Release sign up** button on a Books Signup whose status is Ready or Failed, beside Retry. It opens a dialog that shows the email and the site (`hosted_site`, or "none"), and says: the old site keeps running and is not changed; the person reaches it through that site's own `/login` address, because their dashboard will show only their new request; their next sign up uses whatever email their Clerk account holds then. When Released rows already exist with the same `released_email_key`, it warns "This email was released {0} times before." (a warning, not a refusal). It asks for a reason (required, plain text, 1 to 280 characters after trimming, shown escaped). Confirming calls `release_signup` and reloads the form. No other role sees the button.
- **AC-2**: `rarebooks_control.onboarding.release_signup(signup: str, reason: str) -> dict` (POST, whitelisted, type annotated) runs `frappe.only_for("Billing Manager")`, then refuses with a translated `frappe.throw`, writing nothing: an unknown `signup` ("No sign up {0}.", `DoesNotExistError`); a reason blank or over 280 characters after trimming ("A reason is 1 to 280 characters."); status Queued, Claiming or Preparing ("Sign up {0} is still being set up. Release it once it is Ready or Failed."); status Failed with a `hosted_site` while `_cleanup_pending(hosted_site)` returns a refusal (the same message Retry gives, spec 0014 AC-18). A Ready request always passes this check, and so does a Failed one with no `hosted_site`. As with Retry, a Failed request can't be released while its Discard waits under `discard_mode` dry_run; that is intended. `frappe.only_for` lets Administrator through too.
- **AC-3**: A release reads the row `for_update`, checks AC-2 again under the lock, then in one transaction: copies `email_key`, `clerk_user_id` and `subdomain` into `released_email_key`, `released_clerk_user_id` and `released_subdomain`; sets those three to NULL; sets `released_from` to the old status, `status` Released, `released_by` the session user, `released_on` now (UTC) and `release_reason` the trimmed reason; clears `notify_status`, `notified_status`, `notify_started_on` and `notify_alerted_on`. It keeps `email`, the names, `company_name`, `time_zone`, `hosted_site`, `attempts`, `step`, every timestamp and `failed_reason`. It keeps `alerted_on` and `queue_alerted_on` as history. It saves with `row.save()`, so `validate` stores the three blanked keys as NULL, never as an empty string (MariaDB's unique index allows many NULLs but only one empty string), and the change shows in the row's version history (`track_changes`). It answers `{"status": "Released"}`. A release does not give back a slot under `max_claims_per_day` (its `claimed_on` still counts).
- **AC-4**: Releasing a row already Released answers `{"status": "Released"}` and changes nothing (a double click or a retried call is harmless).
- **AC-5**: After a release, `request_site` treats the person as new: the same email (any spelling with the same `email_key`) and the same Clerk account pass checks 1 and 3 of spec 0014 AC-9, and every other check (paused, company, time zone, subdomain rules, the daily cap) applies as before. The released subdomain is free on Books Signup; it is still taken while a Books Hosted Site holds it (spec 0012 AC-2), so a Ready request's old address stays taken.
- **AC-6**: The old site is not changed by a release: no removal case is opened or cancelled, its push, state and trial go on as before. `removal.awaits_signup` treats a Claimed site whose request is Ready **or Released** as no longer waiting, so the removal round still opens its Trial and Lapsed cases (amends spec 0014 AC-20).
- **AC-7**: A Released row is never acted on again: the sweep's claim, owner step, notice retry, 2 hour rule, missing discard and queue alert skip it; `retry_signup` refuses it ("Only a Failed sign up can be retried."); `mark_ready` leaves it (it acts only on Preparing); `fail_signup` returns at once for Released as it does for Ready and Failed, so `fail_signup_of_site` never fails a released request through its old site's `hosted_site`. `signup_status` and `owner_link` answer the released Clerk user a signed 404 (no row holds their `clerk_user_id`).

*Marketing site (`rarebooks-site`)*

- **AC-8**: `GET /api/onboarding/status`: when D1 holds a row for this Clerk user, the Worker sends `signup_status` both `clerk_user_id` and that row's `request_id` (as today). Only on a signed and verified 404 does it delete that row, with `DELETE FROM signups WHERE clerk_user_id = ? AND request_id = ?`, so a newer row written meanwhile is never removed; then it answers 404 as today, so `/dashboard` shows the start form. A 401, 429, 5xx, an unverified answer or no answer never deletes.
- **AC-9**: `POST /api/onboarding/signup`: when D1 holds a row for this Clerk user, the Worker checks Turnstile first, then asks the control site's `signup_status` with that `clerk_user_id` and `request_id`, before the hourly IP limit. A 200 answers the existing `request_id` as today; a signed and verified 404 deletes the row (by `clerk_user_id` and `request_id`, as in AC-8) and goes on as a new sign up (the hourly IP limit, then `request_site`); the control site unreachable or any other answer gives 503 "We couldn't check your earlier sign up. Try again.", keeps the D1 row, does not count toward the IP limit and creates nothing. (The control site answers 404 when no live row holds the `clerk_user_id`, or the one that does has another `request_id`, spec 0014 AC-4.)
- **AC-10**: A release sends the person nothing. A Ready or Failed notice already in flight for the released request either finds the person's D1 row by `request_id` (until the next check deletes it) or writes a row keyed `request:<id>` (spec 0014 AC-6, `ON CONFLICT DO NOTHING`) that no Clerk user reads; it never touches a newer row. The email that notice sends is the one it would have sent anyway, and is intended.

## Decision

**Chosen option**: keep the released row as Released, leave the old site alone, and let the Worker heal its D1 copy from the control site's answers.

A Billing Manager releases a Ready or Failed request with a reason; the control site blanks its three unique keys into `released_*` fields, and the Worker drops any D1 row the control site no longer recognises.

**Implementation skills**: `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `workers-best-practices` (`cloudflare/skills`, `rarebooks-site/.agents/skills/workers-best-practices/`)

## Feature design

**Data model sketch** (Books Signup, changes only):

| Field | Type | Rule |
|---|---|---|
| `status` | Select | gains `Released` (after Failed) |
| `email_key`, `clerk_user_id`, `subdomain` | Data, unique | `reqd` becomes `mandatory_depends_on: eval:doc.status!=='Released'`; `validate` turns `""` into NULL, as it does for `hosted_site`, because MariaDB's unique index allows many NULLs but one empty string |
| `released_email_key`, `released_clerk_user_id`, `released_subdomain` | Data, read only, not unique | the keys the row held, for search and audit |
| `released_from` | Select (Ready, Failed), read only | the status released |
| `released_by` | Link to User, read only | who released it |
| `released_on` | Datetime, read only | when (UTC) |
| `release_reason` | Small Text, read only | why, 1 to 280 characters |

A new "Release" section holds the new fields, shown only when status is Released (`depends_on`). `search_fields` gains `released_email_key`. The list indicator for Released is grey. No data migration: existing rows have no `released_*` values.

**State transitions** (Books Signup): Queued → Claiming → Preparing → Ready or Failed (spec 0014); Failed → Queued (Retry, spec 0014 AC-18); **Ready → Released** and **Failed → Released** (this spec, Billing Manager only). Released is final.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `rarebooks_control.onboarding.release_signup` | POST | `signup`: str (req), `reason`: str (req) | `{"status": "Released"}` | desk session, Billing Manager | 403 not a Billing Manager; 404 unknown sign up; 417 bad reason, wrong status or old site not cleaned up |
| `/api/onboarding/status` (Worker, changed) | GET | Clerk session | as spec 0014 AC-4 | Clerk | 404 now also deletes a stale D1 row |
| `/api/onboarding/signup` (Worker, changed) | POST | as spec 0014 AC-3 | `request_id` | Clerk | 503 when an existing D1 row can't be checked |

The Worker gains `deleteSignup(clerkUserId, requestId)` in `src/lib/onboarding/signups.ts` (`DELETE FROM signups WHERE clerk_user_id = ? AND request_id = ?`). No new route, secret or signed message.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Release dialog | email, site | `email`, `hosted_site` of the row |
| `release_signup` | `released_email_key`, `released_clerk_user_id`, `released_subdomain` | the row's `email_key`, `clerk_user_id`, `subdomain`, read under the lock |
| `release_signup` | `released_from` | the row's `status` under the lock |
| `release_signup` | `released_by` | `frappe.session.user` |
| `release_signup` | `released_on` | `signing.utc_now()` (UTC, as every onboarding timestamp) |
| `release_signup` | `release_reason` | the `reason` input, trimmed |
| `release_signup` (Failed) | whether the old site is cleaned up | `_cleanup_pending(hosted_site)` when `hosted_site` is set (spec 0014 AC-18) |
| Release dialog | times this email was released before | count of Books Signup rows with status Released and the same `released_email_key` (read with the form, `frappe.db.count`) |
| `awaits_signup` | whether a Claimed site still waits | Books Signup `status` in (Ready, Released) for that `hosted_site` |
| Worker status, signup | whether the D1 row is stale | the control site's signed and verified `signup_status` answer (404) for that `clerk_user_id` and `request_id` |
| Worker signup | the Clerk user and request to check | `locals.auth()` user id; D1 `request_id` |

**Key invariants**:
- Among rows that are not Released, one Books Signup per `email_key`, per `clerk_user_id` and per subdomain (the unique indexes, which skip NULL). A Released row holds none of the three.
- A Released row keeps `hosted_site`, so a site is still claimed by at most one request ever.
- A release never opens, cancels or changes a removal case, a push or a Books Hosted Site.
- A Claimed site whose request is Ready or Released gets its Trial and Lapsed cases like any hosted site.
- The D1 `signups` table is a cache of the control site: a row the control site answers a signed, verified 404 for is deleted (matched on `clerk_user_id` and `request_id`), never trusted; nothing else deletes it.
- No release on a request whose claim, owner or domain steps can still run (Queued, Claiming, Preparing).

**Security model**: only a Billing Manager calls `release_signup` (checked on the server with `frappe.only_for`, not only by hiding the button); System Manager keeps read only access; guests and the marketing site cannot release. The `released_*` fields are read only for every role, and Books Signup stays not deletable by any role. The Worker deletes only the D1 row of the signed in Clerk user, and only on a signed, verified 404 from the control site; a forged or missing answer never deletes. No personal data leaves the control site that spec 0014 didn't already send.

**Critical test scenarios**:
- Two releases: two sign ups released one after the other both save, with NULL keys (not empty strings) on both rows. Verifies **AC-3**
- Released row and its old site: a domain failure on the old site (`fail_signup_of_site`) leaves the Released row as it is. Verifies **AC-7**
- Happy path: a Ready sign up is released with a reason; the row is Released with the keys moved and the audit fields set; the same Clerk user signs up again with the same email and a new subdomain and gets a new Queued request; the old site still gets its Trial case from the removal round. Verifies **AC-1**, **AC-3**, **AC-5**, **AC-6**
- Failed release: refused while the old site's Discard is open, allowed once it is Removed and the address is cleaned up. Verifies **AC-2**
- Refusals: Queued, Claiming and Preparing are refused; a blank or 281 character reason is refused; nothing is written. Verifies **AC-2**
- Repeat: a second release answers Released and changes nothing. Verifies **AC-4**
- Released row ignored: the sweep, Retry, `mark_ready` and `fail_signup_of_site` leave it alone; `signup_status` and `owner_link` answer 404. Verifies **AC-7**
- Auth: a System Manager without Billing Manager, and a Removal Manager, get 403 and nothing changes. Verifies **AC-2**
- Worker heal: a D1 row with a signed 404 is deleted on status and on signup; a 200 keeps it; an unreachable control site, a 401 or a 5xx keeps it and answers 503 without counting toward the IP limit; a delete for an old `request_id` leaves a newer row alone. Verifies **AC-8**, **AC-9**
- Late notice: a Ready notice after the release never changes a newer row for the same person. Verifies **AC-10**

## Build plan

Tracer Bullet: the Worker heal ships first, because it is safe on its own (today a 404 already means the D1 row is stale), then the release lands end to end on the control site.

1. Worker: `deleteSignup(clerkUserId, requestId)`, the 404 heal in `status.ts`, the check after Turnstile and before the IP limit in `signup.ts`, with node tests for the decision (delete only on a signed 404 and matching `request_id`, keep on 200, 503 otherwise), satisfies **AC-8**, **AC-9**, **AC-10**
2. Books Signup schema: the Released status, the `released_*` fields and section, `mandatory_depends_on` on the three keys, `validate` turning blank keys into NULL, the list indicator and search field, satisfies **AC-3**
3. `release_signup` with its lock, refusals and idempotent repeat; `fail_signup` returning for Released; tests in `rarebooks_control/tests/test_onboarding.py` (`# covers: AC-n`), including two releases in a row, satisfies **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-7**
4. `removal.awaits_signup` counts Released as Ready, with a test that a released Ready site still gets its Trial case, satisfies **AC-6**
5. Desk: the Release sign up button and dialog in `books_signup.js` (the old site and Clerk email notes, the repeat warning), translated strings, satisfies **AC-1**
6. Staging: release a test sign up, sign up again with the same Clerk account and email, check the old site's case and the version history, satisfies **AC-1** to **AC-10**

## Consequences

**Positive**:
- Freeing an email is one click with a reason, instead of an Administrator delete plus a D1 command.
- Every release stays on record, searchable by the old email, with who, when and why.
- The Worker stops trusting a stale D1 row, which also heals any hand made delete.

**Negative / tradeoffs**:
- A release lets one person hold a second free trial; the only guard is that a Billing Manager must do it and give a reason. There is no limit per email.
- A Released row from a Ready request still points at a live site. Reading "who owns this site" now means checking Released rows too.
- The Worker makes one extra control site call when a signed in user with a D1 row opens the start form; if the control site is down, that user can't start again until it is back.
- A Ready request's old address stays taken, so the person must choose a new subdomain.

**Neutral**:
- Two deploys: the Worker first, then the control site (`bench migrate` adds the fields). No data migration.
- Spec 0014's "ever" invariant now reads "among requests that are not Released".

## Migration plan

**Strategy**: no data migration; two deploys in order.
**Phases**:
1. Deploy the Worker (build task 1). On its own it only deletes D1 rows the control site already doesn't know.
2. Deploy the control site (tasks 2 to 5); `bench migrate` adds the status option and the nullable fields.
**Rollback**: keep the schema (the Released option and the `released_*` fields) and revert only the controller and desk code, so a Released row never fails the old `reqd` rule on its next save; Released rows keep their NULL keys and their people stay free to sign up. Reverting the Worker brings back the stuck start form for released people only.
**Risks**: releasing before the Worker deploy leaves the released person stuck on the old request until it ships; the deploy order above prevents it. The new Worker sends `request_id` to `signup_status`, which spec 0014 already accepts, so the Worker can ship first safely.

## Follow-up

- [ ] Update spec 0014's key invariant and AC-20 line to point here once this ships.
- [ ] Add the Release button to the operator notes in `frappe_books/subscription/AGENTS.md` or the control repo's doctype `AGENTS.md` (`/sync`).

## Rationale

The reasoning and the options weighed are in [rationale.md](rationale.md).
