# Review, v16-dashboard-features (push daily summary amend), 2026-11-28

**Reviewed by**: Claude Sonnet (author on Claude Opus)
**Scope**: 9 files, branch vs version-16 line (only the amend since 3eeb12c plus the uncommitted scope tick)
**Verdict**: Approve with nits

## Summary
Adds the AC-15 daily low stock summary: an hourly job gated on the 08:00 site hour, its own switch, a hidden last-sent date, a `SendReport` so the day is recorded only when a push reached a device, and a migration patch. It matches the spec closely (gating order, one grouped query, ordering, 40 character cut, tag, link, record-only-on-sent). The `.ok` change keeps the subscription retry behaviour; no other caller of `send_job`/`send_now` relied on the old bool. No blockers or majors. A few minors around polish and cost.

## Minor
### 🟡 Name cut can leave a double space, `frappe_books/notifications/events.py:~250`
**Problem**: `row.name[:40]` is joined with a space, so a name whose 40th character is a space gives "…Very Long  0 Unit" (confirmed by the session's runtime check).
**Why it matters**: cosmetic on a lock screen only; the spec says "cut to 40 characters" so it is not a violation.
**Suggested fix**: strip trailing whitespace after the cut (and add a test for it).

### 🟡 Ledger aggregate runs before the cheap exits, `events.py:~190-198`
**Problem**: `_low_items()` (left join plus group by over the whole ledger) runs every hour from 08:00 until midnight on a site that has push on but no device or a failing key, before `send_now` finds no recipients.
**Why it matters**: up to 16 full ledger scans a day per such site on a shared hosted fleet. The spec accepts retrying hourly, but not the order.
**Suggested fix**: check for recipients (or at least any device row) before the query, or skip the query when no Manager device exists. Optionally limit the query result, since only the count and top three are used (count needs the full set, so keep the aggregate but avoid it on the no-device path).

### 🟡 New strings not in the .po catalogs, `events.py` ("Low stock items: {0}", "+{0} more")
**Problem**: not in `frappe_books/locale/*.po`. Checked: the AC-5/AC-6/AC-7 strings are not there either, so this is a pre-existing gap for the whole push module, not specific to this amend.
**Why it matters**: these push texts always render in English until the catalogs are regenerated.
**Suggested fix**: regenerate the catalogs once for the push module (separate task), or note it in the spec Consequences.

## Nits
- ⚪ `events.py` `_low_items`: every low row is loaded and `as_decimal`-converted though only three are shown; fine at shop scale.
- ⚪ `events.py` `_summary_due`: `is_locked()` (which may read the clock) is evaluated every hour before the cheap hour check; reordering the hour test first would skip it before 08:00.
- ⚪ `sending.py` `SendReport`: `send_job` is also the RQ job, so the pickled result is now a NamedTuple instead of a bool; harmless, nothing reads it.

## Strengths
- Gating, ordering, tag and link follow AC-15 and the value table exactly; the day is stored only when `sent > 0`, with a dead-token-only run correctly retried.
- `SendReport.ok` preserves the subscription "refused everything, retry" semantics (no truthy-tuple trap), and the totals query agrees with `_stock_on_hand` (no ledger row counts as 0).
- Patch is in `[post_model_sync]`, reuses `store_default_events`, and the fresh install path already calls it; the migrated-site first-summary-tomorrow case is tested.

## Test coverage
Strong: one-a-day and 07:59/08:00/09:00/next-day, single versus multi item, cut names, tie order, exactly three items, at-level, no devices, every send refused, switch off, locked, push off, item dropped while push off, and the migration patch. Gap: the trailing space cut. (A partial success recording the day is covered by `test_a_partial_success_records_the_day`.)
