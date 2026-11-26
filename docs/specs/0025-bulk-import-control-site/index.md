# 0025. Bulk import into one hosted site from the control site

**Date**: 2026-11-26
**Status**: Proposed

## Summary

You get a spreadsheet style grid on the control site. You pick one claimed hosted site and one document type the site's Import Wizard imports, then paste or type rows into the site's own columns. The control site checks every cell's format, then the site runs a dry run (Frappe's own preview, which writes nothing). Only when both pass can you import, and the rows go into that one site only, through Frappe's Data Import (the engine the Import Wizard already uses), so the site's own controller rules still decide what saves. Rows that fail can be fixed and sent again without importing anything twice.

## Requirements

**User stories**:
- As a Billing Manager, I want to paste a customer's data (accounts, parties, items, invoices) into a grid and load it into their site, so I can set them up without logging into their site and running the wizard by hand.
- As a Billing Manager, I want every wrong cell marked before anything is sent, so a bad sheet never half lands on a customer's books.
- As a Billing Manager, I want to fix only the rows that failed and send them again, so nothing that already saved is imported twice.

**Acceptance criteria**:
- **AC-1**: Only a Billing Manager can read, create or edit a Books Bulk Import, in desk and over the API. Every whitelisted method in `bulk_import.py` calls `frappe.only_for("Billing Manager")`. No role, System Manager included, can read one otherwise, and no role can delete one.
- **AC-2**: The site picker offers only eligible sites. A site is eligible when it is `status` Active and `config_status` Active, has an `owner_email`, has `pool_status` blank or Claimed, has a Ready Books Signup (if a Books Signup points to it), and has no open Books Removal Case (`removal.open_case` is empty). The same rule is checked again on save, before the dry run and right before sending.
- **AC-3**: Picking a site fetches its columns through the signed `import_columns` call. The type picker then shows exactly the types that site's Import Wizard offers (the four stock types only when the site has inventory on). For each type, the grid shows the wizard's template columns in the wizard's order: the name column first, then parent fields, then child table fields labelled `Field (Table)`. A required parent column is marked.
- **AC-4**: You can paste a block copied from Google Sheets or Excel into the grid at any cell, add rows, load a CSV whose headers match the column labels (unknown headers are named and ignored), and download a blank template CSV with the site's headers.
- **AC-5**: Check runs the format rules on the control site first, for every cell: required parent fields on a document's first row, Int, Float, Currency and Percent in the site's number format or plain `1234.50`, Date and Datetime in the site's date format or ISO (`2027-01-31`, `2027-01-31 14:05:00`), Check as `1`, `0`, `Yes` or `No`, Select as one of the field's options, and Data within 140 characters. Rows are grouped into documents by the name column, as in the wizard. Each wrong cell is marked in red with its reason. The site is not called until every cell passes.
- **AC-6**: When the formats pass, the site runs a dry run (`preview_import`), which writes nothing on the site (no Data Import, no File, no file on disk). Its warnings are shown on the grid rows they name (and the column, when the warning names one). Status becomes Checked only when there are no blocking warnings. Import is enabled only while the status is Checked. Any change to the rows, the site, the type or the Submit switch puts the status back to Draft.
- **AC-7**: Import sends the rows to the picked site only. The site creates a Data Import named `CTRL-<import name>-<attempt>`, running as Administrator, with import type Insert New Records, `submit_after_import` from the Submit switch (always off for `Books Expense`, spec 0004 AC-12), and starts it on its own background queue. No other site is called.
- **AC-8**: A start sent again with the same name (a double click, or a resend after a lost answer) answers with the Data Import already there and starts nothing new.
- **AC-9**: While the form is open on an import in status Importing, it refreshes every 5 seconds through the control site, which calls the site's signed `import_report`. A job every 5 minutes refreshes every import still Importing, so closing the tab loses nothing. The import ends in Success, Partial Success or Failed, with `success_count`, `failed_count` and a result per grid row (the saved document's name, or the reason it failed).
- **AC-10**: After Partial Success or Failed, the rows that saved are locked (read only, never sent again). Check and Import send only the failed rows, as the next attempt. No grid row is ever imported twice.
- **AC-11**: Refusals change nothing on the site. A locked site answers a signed 409 `site_locked` to every import call before any write. A site no longer eligible at send time sets the status to Refused, with the reason in `last_error` and the rows kept. A call with a bad or missing signature, a stale `issued_at`, or another site's name gets a signed 401 and imports nothing. A site that cannot be reached leaves the status Checked with `last_error` set; sending again is safe by AC-8.
- **AC-12**: An import over 5,000 grid rows, or a CSV body over 4 MB, is refused on the control site with a message, before any call to the site.
- **AC-13**: Imports only insert. A row naming a record that already exists on the site fails that row with the site's reason. Nothing on the site is ever updated or deleted from the control site.
- **AC-14**: 30 days after `finished_on` (or 30 days after the last change, for one never finished), a daily job clears `rows`, `results`, `sent_rows` and `columns` and sets `rows_cleared_on`. The site, type, owner, dates, status and counts stay. When a site reaches Removed (`removal.mark_removed`), the rows of all its imports are cleared the same way, at once.
- **AC-15**: The site's list of importable types and its column rules are pinned against the wizard. A Python test fails CI when the types in `getImportableSchemaNames` (`frontend/src/importer.ts`) and the site's list differ. A second Python test compares the column keys `import_columns` gives for each type with a committed fixture taken from the wizard's Save template.
- **AC-16**: Every Books Bulk Import keeps track changes. The site's Data Import name carries the control site import's name. Customer row values and secrets never go into an Error Log, an alert or `last_error`. Every user facing message is translated (`_()` in Python, `__()` in desk JS).

## Decision

**Chosen option**: Option 1: a Books Bulk Import form on the control site, columns read live from the picked site, rows sent over the signed site call contract into the site's own Frappe Data Import.

The control site owns the grid, the format checks, the eligibility rule and the history. The site owns the column list, the dry run and the import, all through four new signed guest endpoints beside `remote.py`.

**Implementation skills**: `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch** (control site, `rarebooks_control`):

Books Bulk Import, named `BIMP-.#####`, track changes on, module Rarebooks Control. Billing Manager: read, write, create. No other role. No delete for anyone.

| Field | Type | Required | Notes |
|---|---|---|---|
| `hosted_site` | Link → Books Hosted Site | yes | N imports to 1 site. Link query `bulk_import.site_query` lists eligible sites only (AC-2) |
| `import_type` | Data | yes | A site DocType name, for example `Books Sales Invoice`. Must be in `columns` |
| `submit_after_import` | Check | | Forced to 0 for `Books Expense` in `validate()` |
| `status` | Select, read only | yes | Draft · Checked · Importing · Success · Partial Success · Failed · Refused. Default Draft |
| `columns` | Long Text, hidden | | JSON from `import_columns` for this type: column list, `date_format`, `number_format` |
| `columns_fetched_on` | Datetime, read only | | |
| `rows` | Long Text, hidden | | JSON list of grid rows, each a list of cell strings in `columns` order |
| `row_count` | Int, read only | | Set on save, kept after clearing |
| `attempt` | Int, read only | | 0 until the first send, then +1 per send |
| `sent_rows` | Long Text, hidden | | JSON: grid row indexes in the order of the last sent CSV, so a Data Import Log row maps back to a grid row |
| `site_import` | Data, read only | | The site's Data Import name for the current attempt |
| `success_count`, `failed_count` | Int, read only | | Totals across all attempts |
| `results` | Long Text, hidden | | JSON map: grid row index → `{success, docname, message, attempt}` |
| `checked_on`, `sent_on`, `finished_on` | Datetime, read only | | |
| `last_error` | Small Text, read only | | A translated reason, never row values or secrets |
| `rows_cleared_on` | Datetime, read only | | Set by the retention job or the removal hook |

`sent_rows` is a small internal addition to the model confirmed in the conversation: the site's Data Import Log names file rows, so the control site has to remember which grid row became which file row.

On the site (`rarebooks-web`) there is no new DocType: Frappe's Data Import and Data Import Log hold the import, named `CTRL-BIMP-00012-2` (import plus attempt).

**State transitions** (Books Bulk Import `status`):

```
Draft ──check passes──▶ Checked ──send──▶ Importing ──report──▶ Success
  ▲                        │                  │                 Partial Success ─┐
  │                        │                  └──report──▶      Failed ──────────┤
  │                        └──not eligible──▶ Refused                            │
  └──── any edit (rows, site, type, Submit) from Checked or Refused ◀────────────┘
                                   retry: edit failed rows, check again
```

- Draft → Checked: only through `check` (AC-5, AC-6).
- Checked → Importing: only through `send`, after the eligibility check and a 2xx from `start_import` (AC-7).
- Checked → Refused: the site is no longer eligible, or answers 409 `site_locked` (AC-11).
- Importing → Success, Partial Success or Failed: only from an `import_report` with a finished status (AC-9).
- Partial Success or Failed → Draft: an edit of a failed row; then Checked → Importing again with `attempt` + 1 (AC-10).
- Success is final. Edits are refused.

**API surface**:

Customer site (`frappe_books/subscription/bulk_import.py`, exported as `frappe_books.subscription.<name>` so `site_calls.call_site` reaches them). Each one is a guest POST checked by `remote._verified()` (signature with `books_control_secret`, the site's own name, `issued_at` inside 5 minutes), rate limited to 60 per minute, answering through `SignedCall.answer` so every answer is signed and echoes `issued_at`. None goes in `ALLOWED_METHODS`. Each one first checks the lock (`clock.current_clock()` phase locked) and answers 409 `site_locked`.

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `import_columns` | POST | none beyond `site`, `issued_at` | `types: [{doctype, schema_name, label, submittable, columns: [{key, label, fieldtype, required, options, table_label}]}]`, `date_format`, `number_format` | signed guest | 401 bad signature, 409 site_locked |
| `preview_import` | POST | `import_type: str` (req), `csv: str` (req) | `warnings: [{row, column, message}]` (`row` counts the header as 1) | signed guest | 400 unknown type or bad CSV, 401, 409, 413 body over 4 MB |
| `start_import` | POST | `import_ref: str` (req, `^BIMP-\d{5,}-\d+$`), `import_type: str` (req), `submit: 0/1` (req), `csv: str` (req) | `data_import`, `status`, `started: bool` | signed guest | 400, 401, 409, 413 |
| `import_report` | POST | `data_import: str` (req, must start with `CTRL-BIMP-`) | `status`, `total`, `success`, `failed`, `logs: [{rows, success, docname, message}]` | signed guest | 400 not a control import, 401, 404 unknown, 409 |

Control site (`rarebooks_control/bulk_import.py`, every method type annotated, POST, Billing Manager only):

| Method | Key inputs | Key outputs | Key errors |
|---|---|---|---|
| `site_query` (link query) | `txt`, standard link query args | eligible sites | |
| `load_columns` | `name: str` | `columns` for the type, `types` for the picker | site not eligible, site call failed |
| `check` | `name: str` | `status`, `cell_errors: [{row, column, message}]`, `row_warnings: [{row, column, message}]` | over 5,000 rows or 4 MB, site call failed |
| `send` | `name: str` | `status`, `site_import` | status not Checked, not eligible (Refused), site call failed |
| `refresh` | `name: str` | `status`, counts, `results` | site call failed (status stays Importing) |
| `sweep` (scheduler, every 5 minutes) | | | one failing site never stops the others |
| `clear_old_rows` (scheduler, daily) | | | |
| `clear_for_site(site)` (called from `removal.mark_removed`) | `site: str` | | |

The template CSV download and CSV load run in the browser from `columns`, with no extra call.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Site picker | eligible sites | Books Hosted Site `status`, `config_status`, `owner_email`, `pool_status`; Books Signup `status` by `hosted_site`; `removal.open_case(site)` |
| Type picker | the importable types | site `import_columns.types`: a Python list mirroring `getImportableSchemaNames`, with the stock types added when Accounting Settings `enable_inventory` is on (AC-15) |
| Grid columns | key, label, type, required, options, order | site `import_columns`, built from the DocType meta with the wizard's rules: skip hidden, virtual and read only (unless required) fields and Attach, Attach Image and layout fields; the name column first and required; child fields keyed `<table fieldname>.<fieldname>` and labelled `Field (Table)`; a numbered type's name only groups rows and is not sent |
| Format check | the date and number format | site System Settings `date_format` and `number_format`, sent in `import_columns` |
| CSV sent | the cells | `rows`, with dates turned to ISO and numbers to plain `1234.50` on the control site, so Frappe never guesses a format |
| Dry run | row warnings | Frappe `Importer.get_data_for_import_preview()` on an unsaved Data Import with a temporary file path, so nothing is written |
| Start | the Data Import name | `CTRL-` + `import_ref`, where `import_ref` = Books Bulk Import name + `-` + `attempt` |
| Start | the owner of the records | Administrator, set with `frappe.set_user` for the request; Frappe's background job runs as the user who enqueued it |
| Start | submit or draft | `submit_after_import`, forced off for `Books Expense` on both sides |
| Report | result per grid row | Data Import Log `row_indexes` (file rows, header row 1) mapped through `sent_rows`, plus `docname`, `success` and the log's message (or the last line of its exception, as `getLogMessage` in `dataImport.ts` does) |
| Retry | which rows to send | grid rows with no `results` entry, or one with `success` false |
| Retention | when to clear | `finished_on` + 30 days, else `modified` + 30 days; site removal from `removal.mark_removed` |

**Key invariants**:
- One import targets exactly one site, fixed once the status leaves Draft. `send` calls `call_site` with that `hosted_site` and no other.
- A grid row with a successful result is never in a sent CSV again.
- The site never starts a second Data Import for the same `import_ref` (Frappe names are unique; `start_import` returns the existing one).
- The status is Checked only if the stored rows, site, type and Submit are exactly what the last `check` saw. `validate()` resets it to Draft when any of them changes.
- Nothing on a customer site is written by `import_columns` or `preview_import`.
- `submit_after_import` is 0 whenever `import_type` is `Books Expense`.
- Status changes only through `bulk_import.py`, never from desk: the field is read only.

**Security model**:
- Control site: Billing Manager only (AC-1), behind the two factor sign in from spec 0008 AC-20. The rows are customer books data, so System Manager and Removal Manager get no permission on the DocType at all. Customer data on the control site is limited by the 30 day clearing and the removal hook (AC-14).
- Transport: the existing signed contract (spec 0010 AC-2): HMAC over the raw body with the site's `control_secret` (falling back to `pending_secret` during a rotation, as `call_site` does), the `issued_at` echo, and `destinations.post`, so a site URL can't point at a private address.
- Customer site: the four endpoints accept only a verified call naming this site. Everything runs as Administrator, so the records' owner shows it came from the operator, not the customer. Insert only: no update or delete path exists (AC-13). Locked sites refuse (AC-11), and none of the endpoints is added to `ALLOWED_METHODS`, so the lock stays whole.
- Logging: never log the secret, the CSV, a row value or a URL query. `last_error` and alerts carry only a translated reason and an HTTP status.
- Compliance: customer financial records pass through and rest briefly on the control site. No payment card data is involved. The audit trail is the Books Bulk Import (track changes on) plus the site's Data Import record named after it.

**Configuration required**:
- None. It reuses each site's `control_secret` and `site_url` from Books Hosted Site, and the site's `books_control_secret` and `books_control_url` from site config.
- Vendored asset: Jspreadsheet CE 5.0.4 and its jsuites dependency on the 5.x line, pinned and committed under `rarebooks_control/public/js/vendor/jspreadsheet/` (JS and CSS), loaded only by the Books Bulk Import form. Check the license file in the release before committing it (the npm registry entry shows no license field).

**Critical test scenarios**:
- Happy path: a Billing Manager picks an eligible stub site, picks Books Item, pastes 3 rows, checks, imports. The stub site's `start_import` is called once with `CTRL-BIMP-00001-1`, the report gives 3 successes, and the status is Success with 3 docnames. Verifies **AC-3**, **AC-4**, **AC-7**, **AC-9**.
- Format check: a bad date, a word in a Currency column, an unknown Select option and a missing required party on a first row each mark that cell, and the site is never called. Verifies **AC-5**.
- Dry run writes nothing: on the real site, `preview_import` with an unknown account returns a warning on row 2, and the counts of Data Import, File and files on disk are unchanged. Verifies **AC-6**.
- Status reset: editing a cell after Checked sets Draft, and `send` refuses. Verifies **AC-6**.
- Idempotent start: `start_import` twice with the same `import_ref` gives one Data Import and `started` false the second time. Verifies **AC-8**.
- Partial and retry: 2 of 3 invoices fail on an unknown item. Fixing them and sending again sends a 2 row CSV as attempt 2, and the first row is never resent. The totals end at 3 successes and 0 failures. Verifies **AC-9**, **AC-10**.
- Lost answer: `start_import` succeeds on the site but the answer times out. The status stays Checked, and sending again returns the same Data Import. Verifies **AC-8**, **AC-11**.
- Locked site: a site set locked with `set_hosted_phase` answers 409 `site_locked` to all four calls, writes nothing, and the import is Refused. Verifies **AC-11**.
- Eligibility: an unclaimed pool site, a site with an open removal case and a Removed site are missing from the picker and refused at `send`. Verifies **AC-2**.
- Signature: an unsigned call, a call signed for another site and a stale `issued_at` each get a signed 401 and no Data Import. Verifies **AC-11**.
- Caps: 5,001 rows, or a body over 4 MB, is refused with no site call. Verifies **AC-12**.
- Existing record: importing an Account whose name exists fails that row, and the existing account is unchanged. Verifies **AC-13**.
- Retention: a finished import 31 days old has its rows cleared and its counts kept. A site reaching Removed clears all its imports at once. Verifies **AC-14**.
- Drift guard: adding a type to `getImportableSchemaNames` without the Python list fails the test. Verifies **AC-15**.
- Auth/permission: a System Manager gets a permission error opening the list and calling `check`, `send` and `refresh`. Verifies **AC-1**.

## Build plan

Tracer Bullet: first one type (Books Item, no child table, no submit) goes end to end from the grid to a real site, then the thread thickens.

1. **Site: the signed import endpoints, read side.** In `frappe_books/subscription/bulk_import.py`: the importable list mirroring `getImportableSchemaNames` with the inventory rule, the column builder from DocType meta, `import_columns`, the lock 409, export from `__init__.py`. Add tests: signature, the lock, the drift guard for types and the column fixture for Books Item. Satisfies **AC-3**, **AC-11**, **AC-15**.
2. **Control site: the DocType and the thin form.** Books Bulk Import (desk, developer mode, permissions Billing Manager only), `site_query`, `load_columns`, the vendored Jspreadsheet with a plain grid on the form, the status reset in `validate()`. Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-16**.
3. **The thread: one Books Item import end to end.** The site's `start_import` (named, idempotent, as Administrator) and `import_report`. The control site's `send`, `refresh`, form polling and the `*/5` sweep. Tests against a `call_site` stub, plus one run on a real bench site. Satisfies **AC-7**, **AC-8**, **AC-9**, **AC-13**.
4. **Checks before sending.** The format rules in Python with cells marked on the grid, the site's `preview_import` (unsaved Data Import, temporary file, nothing written), ISO dates and plain numbers in the sent CSV, the caps, Checked gating Import. Satisfies **AC-5**, **AC-6**, **AC-12**.
5. **Every type, children and submit.** Child table grouping by the name column, the Submit switch with the Expense rule, the column fixtures for every type (taken from the wizard's Save template), and tests for Sales Invoice and Expense like `test_data_import.py`. Satisfies **AC-3**, **AC-7**, **AC-15**.
6. **Retry, refusals and the rest of the grid.** Locked saved rows, failed rows only as the next attempt, Refused with the reason, unreachable handling, paste from a sheet, CSV load and template download. Satisfies **AC-4**, **AC-10**, **AC-11**.
7. **Retention and removal.** The daily `clear_old_rows`, `clear_for_site` called from `removal.mark_removed`, and the tests. Satisfies **AC-14**.

## Consequences

**Positive**:
- One place to load a customer's data, with the same columns and controller rules as the wizard, so what lands on the site behaves like data entered there.
- No new transport, secret or host: it rides the signed contract that removal and onboarding already use.
- The columns come from the site itself, so a site on a newer Books version, or with inventory off, shows exactly what it accepts.

**Negative / tradeoffs**:
- The column rules now live twice: in the wizard's TypeScript and in the site's Python. The AC-15 tests catch drift in the type list and the column keys, but not every rule (a new field property the wizard starts honoring needs a fixture refresh).
- The control site briefly holds customer books data (up to 30 days), which widens what a control site breach would expose.
- A Partial result is normal: half a set of invoices can be saved while the rest wait for a fix. You need to read the results before telling the customer it's done.
- Jspreadsheet is a new vendored dependency to keep updated by hand, with no Agent Skill or MCP server for it.
- Records show Administrator as their owner, so a customer can't tell who in your team imported them, only that it came from the operator (the Books Bulk Import has the person).

**Neutral**:
- The four new site endpoints are refused on a locked site, so loading data for someone who hasn't paid waits until the lock lifts.
- Two new scheduler entries on the control site (`bulk_import.sweep` every 5 minutes, `bulk_import.clear_old_rows` daily) and one call added to `removal.mark_removed`.

## Follow-up

- [ ] Before step 4, confirm on Frappe 16 that `Importer.get_data_for_import_preview()` flags a Link value that doesn't exist on the site. If it doesn't, `preview_import` adds that check itself (a lookup per distinct Link value).
- [ ] Agent Skills and MCP servers for Jspreadsheet CE were searched (2026-11-26): none found. Nothing to install.
- [ ] Add the new endpoints to `frappe_books/subscription/AGENTS.md` and the new DocType to `rarebooks_control/rarebooks_control/doctype/AGENTS.md` once built (`/sync`).
- [ ] Deferred: an Update existing mode, an email to the site owner after an import, and a workbook with several types sent in order. None is in this spec.
