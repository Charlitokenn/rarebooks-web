# Verify: proving a site is archived · spec 0013 · updated 2026-11-21
_Steps derived from spec 0013 acceptance criteria and its Value sourcing table. `/check verify` runs these; `/test` locks the durable ones. All code is in the `rarebooks_control` repo._

## Commands (control site bench, `allow_tests` on)
- [x] `bench --site <site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_removal` → passes, including `TestArchiveProof` → AC-1 to AC-4, AC-7, AC-8
- [x] `bench --site <site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_domains` → passes, including the `TestCleanup` tests → AC-5, AC-6
- [x] `uvx ruff@0.14.10 check rarebooks_control` and `uvx ruff@0.14.10 format --check rarebooks_control` → clean
- [x] `grep -rn "start_domain_cleanup" rarebooks_control/*.py` → called only in `removal.mark_removed` (its definition is in `registry.py`) → AC-5

## The proof, against the fake (bench console with `FakeFrappeCloud` patched, or the tests above)
- [x] `get` answers `Archived` → `site_archived` returns `("status", ...)`, and `domain_exists` isn't called → AC-1
- [x] `get` answers 403, the case has `drop_started_on`, `domain_exists(site)` answers `null` → `("released", None)` → AC-1
- [x] `get` answers 403 on a case with no `drop_started_on` (the drop start read) → raises the client's `HTTP 403` text, `domain_exists` never called → AC-1, AC-3
- [x] `get` answers 403 and `domain_exists` names the site itself, or `theirs.frappe.cloud` → raises "the site's name is still held", and the text never contains `theirs` → AC-1, AC-8
- [x] `get` answers 403 and `domain_exists` times out, or answers HTTP 500 → "domain_exists failed (no answer)" or "(HTTP 500)" → AC-8
- [x] `get` answers 500, 404, or times out → the client's own text, `domain_exists` not called → AC-1

## Value sourcing (one step per row)
- [x] proof (a) site status: set the fake site's `status` to `Archived`, then `Suspended` → only `Archived` proves → AC-1
- [x] proof (b) "we started this drop": the same 403 plus released name on a `Holding` case (drop start) fails a step, on a `Dropping` one it removes → AC-1, AC-3
- [x] proof (b) "hidden from the team": a 403 proves, a 404 with the name released doesn't → AC-1
- [x] proof (b) "name released": `domain_exists` is asked for the case's `site` (check `cloud.calls` holds `("domain_exists", "<case site>")`), not the custom domain → AC-1
- [x] poll, drop start: the case read is the locked Books Removal Case of that site; a site not registered is refused by `cloud_refusal` before any archive → AC-2, AC-3
- [x] poll `archive_requested_on`: with the mark lost and proof (b), the case goes `Removed` with no second archive call → AC-2
- [x] removal `removed_on`: the case and the Books Hosted Site get `removed_on` in UTC, within a minute of the poll → AC-2
- [x] log line: a proof (b) removal logs "<case> of <site> is removed: 403 and name released"; a proof (a) removal logs no such line → AC-7
- [x] error text: `last_error` after a held name reads "press.api.site.get answered HTTP 403 and the site's name is still held" → AC-8
- [x] reconcile cases: only `Failed` cases with `drop_started_on` set are read; a `Failed` case that never started its drop is not → AC-4
- [x] cleanup start: `_write_archive_mark` leaves `domain_status`, `domain_step` and `domain_step_started_on` untouched; `mark_removed` sets Cleanup and Working, and a repeat keeps the start time → AC-5
- [x] cleanup full domain: `domain_exists` is asked for `<subdomain>.<books_site_domain>` (for example `old.rarebooks.cc`) → AC-6
- [x] cleanup holder: `OLD.FRAPPE.CLOUD.` counts as our site and waits; `theirs.frappe.cloud` counts as done → AC-6
- [x] cleanup listed and primary: listed not primary → one `remove_domain`, done at the next sweep; primary → waits with no `remove_domain`; `domains` answering 403 or 404 → waits → AC-6

## Poll and digest, end to end against the fake
- [x] A `Dropping` case after `finish_archive` → next hourly poll makes the case and the row `Removed`, and the archive was called once → AC-2
- [x] `get` 403 with the name still held, three polls → `Dropping`, `Dropping`, `Failed`, one ops email, the row stays `Active` → AC-2, AC-8
- [x] Two `Failed` drops, one after `finish_archive`, one hidden with its name still held → the digest removes only the first, lists "(archived after failing)", sends only the digest → AC-4

## Live (rollout, spec 0010 Milestone 5, before the first real drop)
- [ ] Wrong key check: as the operator, outside the proxy that injects the real key, call `press.api.site.get` and `press.api.site.domain_exists` for a live site with a deliberately wrong key → both fail with an error, neither answers `null` → AC-9 (2)
- [ ] One throwaway site with a subdomain through a `live` drop → `Removed` by proof (b) within two hourly runs after the archive call, with the "403 and name released" log line, then its domain cleanup finishes (`domain_cleaned_on` set, no CNAME left in Cloudflare) → AC-9 (1), AC-5, AC-6

## Acceptance-criteria coverage
- AC-1: proof steps, value sourcing proof rows · AC-2: poll steps, `archive_requested_on` row · AC-3: drop start rows · AC-4: digest step, reconcile row · AC-5: grep step, cleanup start row, live drop · AC-6: cleanup rows, live drop · AC-7: log line row · AC-8: error text steps · AC-9: live steps
