# Review, v16-dashboard-features (spec 0025 bulk import), 2026-11-27

**Reviewed by**: Claude Sonnet 5.5 (author on a different model)
**Scope**: 27 files across two repos (rarebooks_control: dac85c9^..HEAD; rarebooks-web: 13c5540^..e8786ba), branch v16-dashboard-features vs its base, vendored Jspreadsheet and jSuites only checked for VERSIONS.txt, licenses and how they load
**Verdict**: Changes requested

## Summary
The change adds a Books Bulk Import DocType, grid form and signed calls on the control site, and four signed guest endpoints plus a CSV builder on the customer site. The structure follows the spec closely: Billing Manager checks on every method, signed answers, no row lock held across a site call, a fingerprint for idempotent starts, and golden cases shared by Python and node. The headline problems are two paths that can break the "no grid row is ever imported twice" rule: a stalled import is marked Failed without reading what the site already saved, and a late `check` can overwrite an Importing status. A few smaller stale write and trust gaps follow.

## Major

### 🟠 A stalled or stuck import is marked Failed without reading what the site already saved, so a retry can import rows twice, `rarebooks_control/bulk_import.py:418-432` (and `frappe_books/subscription/bulk_import.py:175-177`)
**Problem**: The site's `import_report` returns `logs` only when the Data Import has a finished status. Frappe's importer commits a Data Import Log and the saved document after every record, so a job that stops part way (site locked mid import, dead worker, long outage of the site) has real saved documents and logs. The 2 hour stall rule (`_stalled`, also reached from the `SiteCallFailed` branch of `_refresh`) calls `_finish(row, [], "Failed", ...)` with an empty log list. `results` stays empty for rows that did save. The next Check and Import then sends every row that has no success, as a new attempt.
**Why it matters**: For numbered documents (invoices, payments, expenses) Frappe's "Insert New Records" makes a second document, so the customer's books get duplicate invoices. Only named records (Account, Item) fail as "already exists". A site that is unreachable for 2 hours while its job ran fine ends the same way. This breaks the stated invariant that no grid row is ever imported twice.
**Suggested fix**: Before marking Failed for a stall, ask the site once more for the rows it saved. Easiest is to make `import_report` return logs for any status (paged) or add a flag for it, and have the stall path merge those logs through `_finish` before it sets Failed. When the site cannot be reached at the stall moment, do not give up: keep Importing with the reason, or set a state that needs a manual look, rather than Failed that invites a resend.

### 🟠 A late `check` can overwrite an Importing import and allow a second send of the same rows, `rarebooks_control/bulk_import.py:187-213`
**Problem**: `check` reads the doc, then calls the site (a long call), then writes with `_write(name, apply)`. `apply` only compares `checked_hash`. It never rechecks `row.status`. If a send (from a second tab or a double click on Check then Import) moved the import to Importing while the dry run was running, `apply` sets `status` back to Checked (or Draft on blocking warnings). The same applies to the `_refuse` write on 409 `site_locked` (line 194). After that, `attempt` and `site_import` match, so the next `send` counts the attempt as confirmed, uses `attempt + 1`, and sends the same rows again while attempt 1 is still running or finished.
**Why it matters**: Duplicate documents on a customer site, through ordinary double use of the form. Checked is allowed to be checked again (`_editable` only refuses Importing and Success), so the window is real.
**Suggested fix**: In `check`'s `apply` (and the `_refuse` and `_error` writers it uses) return False unless the row's status is still one of Draft, Checked or Refused. Apply the same guard in `_refresh`'s writers (see the next finding).

### 🟠 `_refresh` writers do not check that the import is still the same Importing attempt, `rarebooks_control/bulk_import.py:372-399, 435-453`
**Problem**: `_refresh` reads the doc without a lock, calls the site (up to many paged calls), then `_write`s `_finish`, `_progress` or the Failed outcome. None of these closures check `row.status == "Importing"` and `row.site_import == doc.site_import` under the lock. A form poll and a sweep job run at the same time by design.
**Why it matters**: A slow refresh that carries attempt 1's report can land after the user has edited, re-checked and sent attempt 2. It then writes attempt 1's logs with `attempt` 2 on them and sets a finished status over the running attempt 2 (and `_finish` clears `sending_since`, `finished_on`). The same stale write after `clear_for_site` also writes `results` back onto a cleared import (message text can hold customer values).
**Suggested fix**: Make every refresh writer return False unless the locked row is still Importing for the same `site_import` and `rows_cleared_on` is empty.

## Minor

### 🟡 Adopting an attempt does not compare the rows, `rarebooks_control/bulk_import.py:268-269, 291-293, 305-314`
**Problem**: After a lost `start_import` answer the attempt is unconfirmed. If the user then edits rows and checks again, `send` still adopts the site's Data Import for that attempt through `import_report` without comparing what it holds with the current rows (the 409 `ref_conflict` path adopts on purpose, but the plain unconfirmed path never asks). Results then map by row id.
**Why it matters**: A row the user just fixed is shown as saved and locked, while the site imported the old values. The operator thinks the fix landed.
**Suggested fix**: When rows changed after the claim, move to a new attempt number instead of adopting (or store the claimed hash with the unconfirmed attempt and adopt only on a match). On `ref_conflict`, tell the user clearly which rows differ rather than silently adopting.

### 🟡 Reload columns edits saved rows, `rarebooks_control/bulk_import.py:127-138`
**Problem**: `reload_columns` strips cells of gone columns from every row, including rows that already saved. It writes with the server flag, so `_keep_saved_rows` is skipped.
**Why it matters**: AC-10 says saved rows are read only. It also changes `checked_hash` inputs of nothing sendable, but the record of what was imported no longer matches.
**Suggested fix**: Keep the cells of rows with a success result, or refuse and name the gone columns.

### 🟡 Site messages are put into `msgprint` and a headline as HTML, `rarebooks_control/rarebooks_control/doctype/books_bulk_import/books_bulk_import.js:122, 127, 195, 443`
**Problem**: `frappe.msgprint(__("...{0}", [message.gone.join(", ")]))` and the CSV `unknown.join(", ")` render as HTML, as do `frm.doc.hosted_site` and `rows_cleared_on` in `set_headline`. The column labels come from the customer site's DocType meta and the CSV headers from an uploaded file. AC-16 asks for plain text. (The grid cells themselves are safe: Jspreadsheet sets `textContent` for text columns, and the UI test covers it.)
**Why it matters**: Low (a customer site would have to alter its meta, or the operator load a hostile CSV), but this is the desk of a billing role.
**Suggested fix**: Pass these values through `frappe.utils.escape_html` before `__()` formatting.

### 🟡 Site picker runs several queries per candidate, `rarebooks_control/bulk_import.py:80-92`
**Problem**: `site_query` loads every site matching the text (no limit) and calls `eligibility_refusal` (five reads) on each before slicing.
**Why it matters**: With an empty search and thousands of hosted sites, every keystroke in the link field costs thousands of queries.
**Suggested fix**: Stop once `start + page_len` eligible sites are found, or push the cheap filters (status, signup, case) into the query.

### 🟡 `clear_for_site` can block a site removal, `rarebooks_control/removal.py` (mark_removed hook) and `bulk_import.py:504-511`
**Problem**: The call runs inside `mark_removed` before its commit. Any exception in clearing an import (validation, permission, a deadlock on the import row) aborts the removal finalization.
**Why it matters**: Housekeeping of a customer's rows should not be able to stop a removal that the hourly round retries forever.
**Suggested fix**: Catch and log (without row values) inside `clear_for_site`, and let the daily job clear whatever is left, since `clear_old_rows` already skips nothing for a Removed site only by age. Add a daily pass for imports of Removed sites.

### 🟡 Name regexes accept a trailing newline, `frappe_books/subscription/bulk_import.py:33, 35, 36`
**Problem**: `^...$` with `re.match` lets `"BIMP-00001-1\n"` and a row id with a trailing newline through, so a Data Import named with a newline can be created. The caller is the trusted control site, so this is hardening only.
**Suggested fix**: Use `re.fullmatch` or `\Z`.

### 🟡 The 2 MB cap is checked after the body is parsed, `frappe_books/subscription/bulk_import.py:315-318`
**Problem**: `_verified()` reads and parses the body first, then `_refused_write` checks locked, then size. The spec says the site refuses a body over 2 MB before anything is parsed.
**Suggested fix**: Check `frappe.request.content_length` / the raw length at the start of `_refused_write` callers, before `_verified()` parses JSON, and answer 413 (signed once verified).

## Nits
- ⚪ `rarebooks_control/bulk_import.py:202-206`, `apply` returns None on a stale check, which still saves the row; return False to skip the save.
- ⚪ `rarebooks_control/bulk_import.py:297`, a 200 answer with a wrong `data_import` name is reported as "answered HTTP 200", which reads oddly.
- ⚪ `rarebooks_control/bulk_import.py:456-460`, `_status_from_counts` counts every grid row, so a blank row that survived (only the form strips blanks) would keep an import at Partial Success; `parse_rows` could drop empty rows.
- ⚪ `frappe_books/subscription/bulk_import.py:341`, a crash between creating and deleting the temporary preview file leaves it under `private/files`; a name prefix sweep would tidy it.

## Strengths
- Every control site method calls `frappe.only_for("Billing Manager")` first, then `check_permission` on the row; the DocType gives no other role access and no delete, and `validate()` stops a desk save from touching any server field.
- The send path is carefully built: a row lock only to claim and write, `sending_since` against double clicks, `site_import` as the confirmed marker, and an idempotent site start keyed by a CSV fingerprint with a signed 409 on a mismatch.
- The site side is insert only, checks `import_type` against its own list on every call, runs as Administrator only inside a restored context, answers through signed responses, and strips HTML from every row message.
- Golden CSV cases are run by both the Python builder and the node wizard test, and the template fixture is pinned by a test, so the two builders cannot drift quietly.
- No row values reach `last_error`, alerts or the Error Log, and a dedicated test proves it. The Jspreadsheet files are pinned with versions and licenses and loaded only by this form.

## Test coverage
Good coverage of the happy path, retry, lost answer, lock, bad signature, eligibility, picker search, retention, drift and the number rule, each tagged with `# covers: AC-n`. Untested and worth adding with the fixes above: a stalled import whose site holds partial logs (must not resend those rows), a `check` that returns after a send moved the import to Importing, a stale `_refresh` landing after the next attempt was sent, adopting an unconfirmed attempt after the rows were edited, and a failure inside `clear_for_site` during `mark_removed`.
