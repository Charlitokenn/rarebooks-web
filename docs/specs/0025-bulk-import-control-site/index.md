# 0025. Bulk import into one hosted site from the control site

**Date**: 2026-11-26
**Status**: Proposed

## Summary

You get a spreadsheet style grid on the control site. You pick one claimed hosted site and one document type the site's Import Wizard imports, then paste or type rows into the site's own columns. The site then runs a dry run (Frappe's own preview, which saves nothing) and marks every wrong cell. Only when it passes can you import, and the rows go into that one site only, through Frappe's Data Import (the engine the Import Wizard already uses), so the site's own controller rules still decide what saves. Rows that fail can be fixed and sent again, and nothing is ever imported twice.

## Requirements

**User stories**:
- As a Billing Manager, I want to paste a customer's data (accounts, parties, items, invoices) into a grid and load it into their site, so I can set them up without logging into their site and running the wizard by hand.
- As a Billing Manager, I want every wrong cell marked before anything is saved, so a bad sheet never half lands on a customer's books.
- As a Billing Manager, I want to fix only the rows that failed and send them again, so nothing that already saved is imported twice.

**Acceptance criteria**:
- **AC-1**: Only a Billing Manager (and the Administrator user, who passes every check in Frappe) can read, create or edit a Books Bulk Import, in desk and over the API. Every whitelisted method in `bulk_import.py` calls `frappe.only_for("Billing Manager")`. System Manager, Removal Manager and every other role get no permission on it. No role can delete one.
- **AC-2**: The site picker offers only eligible sites. A site is eligible when all of these hold: `status` Active, `config_status` Active, an `owner_email` set, `pool_status` blank or Claimed, a Ready Books Signup when one points to it, and no open Books Removal Case (`removal.open_case` is empty). The same rule is checked again on save, before the dry run and right before sending.
- **AC-3**: Picking a site fetches its columns through the signed `import_columns` call. The type picker shows the types the site's Import Wizard offers to a user who may import everything (the four stock types only when the site has inventory on). For each type, the grid shows the wizard's template columns in the wizard's order: the name column first, then parent fields, then child table fields labelled `Field (Table)`, with required parent columns marked. The columns stay fixed for the life of the import. A Reload columns action fetches them again, keeps cells by column key, names any column that is gone, and puts the status back to Draft.
- **AC-4**: You can paste a block copied from Google Sheets or Excel into the grid at any cell, add rows, load a CSV whose headers match the column labels (unknown headers are named and ignored), and download a blank template CSV with the site's headers. Each grid row carries a stable id that moves with it when rows are inserted, sorted or deleted.
- **AC-5**: Check first runs the structural rules on the control site: at least one row, every row has a name cell (it groups a document's rows), every column key is one the site gave, and the caps of AC-12 hold. It then calls the site's dry run (`preview_import`). The site builds the import CSV (AC-17) and runs Frappe's preview, which checks dates, numbers, Select options, required cells and Link values that don't exist on the site. Each warning is shown on the grid rows and column it names, and a warning that names no row is shown above the grid.
- **AC-6**: The dry run saves nothing on the site: no Data Import, no File row. Its temporary file is deleted before the call answers. The status becomes Checked only when the site reports no blocking warnings (Frappe's own `get_blocking_warnings` rule). Import is enabled only while the status is Checked. Any real change to the rows, the site, the type or the Submit switch (a different `checked_hash`) puts the status back to Draft. A save with no change does not.
- **AC-7**: Import sends the rows to the picked site only. The site checks the type against its own list, builds the CSV, and creates a Data Import named `CTRL-<import name>-<attempt>`. It runs as Administrator, with import type Insert New Records, `submit_after_import` from the Submit switch (always off for `Books Expense`, spec 0004 AC-12, and ignored for a type that can't be submitted) and `mute_emails` on, and starts it on its own background queue. No other site is called.
- **AC-8**: A start sent again with the same name and the same rows (a double click, a resend after a lost answer, or two at once) answers with the Data Import already there and its status, and starts no second import. When that Data Import is Pending with no logs and no job queued, it starts it. A start with the same name but different rows gets a signed 409 `ref_conflict`. The attempt number goes up only after the site confirms a start. Before any send, an unconfirmed earlier attempt is looked up on the site, and if it exists there, it is adopted instead of sending again.
- **AC-9**: While the form is open on an import that is Importing, it refreshes every 5 seconds through the control site, which calls the site's signed `import_report`. A job every 5 minutes queues a refresh for every import still Importing, one job per import, so closing the tab loses nothing and one slow site never holds up the others. When the site's Data Import finishes, the import ends in:
  - Success when every grid row has saved;
  - Partial Success when some have saved and some failed;
  - Failed when none has saved, or when the site's Data Import stopped (Error, Timed Out, or back to Pending with blocking warnings), with the reason.
  
  `success_count` and `failed_count` count grid rows and are always computed again from `results`.
- **AC-10**: After Partial Success or Failed, the rows that saved are locked: read only, never deleted, moved or sent again. Check and Import send only the rows without a success, as the next attempt. No edits are allowed while Importing. No grid row is ever imported twice.
- **AC-11**: The site's answers lead to a defined outcome (the table in Feature design):
  - A locked site (`clock.is_locked()`, which covers lapsed too) answers a signed 409 `site_locked` to `import_columns`, `preview_import` and `start_import` before any write. `import_report` still answers on a locked site, since it only reads.
  - A site no longer eligible at send time sets the status to Refused, with the reason in `last_error` and the rows kept.
  - A call with a bad or missing signature, a stale `issued_at`, or another site's name gets a signed 401 and imports nothing.
  - A site that can't be reached, or answers 5xx, leaves the status where it was, with `last_error` set.
  - An import with no progress for 2 hours (a job stopped by the lock, a dead worker) becomes Failed, with a reason saying so.
- **AC-12**: An import over 2,000 grid rows, or a rows body over 2 MB, is refused on the control site with a message, before any call to the site. The site refuses a body over 2 MB with a signed 413.
- **AC-13**: Imports only insert. A row naming a record that already exists on the site fails that row with the site's reason. Nothing on the site is ever updated or deleted from the control site. The site refuses any `import_type` outside its own list on every call, so Frappe's Data Import can never be pointed at User, Role or any other DocType.
- **AC-14**: The control site's copy of the rows is cleared on a schedule:
  - A daily job clears `rows`, `results` and `columns` and sets `rows_cleared_on`, 30 days after `finished_on` (or 30 days after the last change for an import never finished, never while Importing).
  - The site, type, owner, dates, status and counts stay.
  - When a site reaches Removed (`removal.mark_removed`), all its imports are cleared the same way, at once.
  - A cleared import is final: check, send, refresh and edits are refused with a message.
  
  Books Bulk Import has track changes off, so no Version record ever copies the rows. Each status change instead adds a comment naming the user, the status, the attempt and the counts.
- **AC-15**: The site's importable types and column rules are pinned against the wizard. A Python test fails CI when the types in `getImportableSchemaNames` (`frontend/src/importer.ts`) and the site's list differ, and checks that each listed DocType allows import. A second test compares the column keys `import_columns` gives for each type with a committed fixture taken from the wizard's Save template.
- **AC-16**: The site's Data Import name carries the control site import's name. Customer row values and secrets never go into an Error Log, an alert or `last_error` on the control site. Row messages from the site are shown as plain text, never as HTML. On the site, the private CSV File is deleted when its Data Import finishes. Its Data Import Log messages stay, since they are the customer's own records. Every user facing message is translated (`_()` in Python, `__()` in desk JS).
- **AC-17**: The site builds the import CSV the way the wizard's `getImportFile` does:
  - a leading `docstatus` column, with `0` on each document's first row;
  - header keys from the wizard's `getImportColumnKey` rule, so a numbered document's name and a child row's id are not sent;
  - the rows of one name brought together in grid order;
  - each parent cell taking the last non empty value among the document's rows, with blank parent cells on the following rows;
  - blank rows dropped;
  - dates read in the site's date format or ISO and written as ISO;
  - numbers read in the site's number format or plain (`1234.50`) and written in the site's format.
  
  A shared golden fixture (`frappe_books/tests/import_csv_cases.json`, grid rows in and CSV out) is run by a Python test and by a frontend node test against the wizard's builder, so the two can't drift.

## Decision

**Chosen option**: Option 1: a Books Bulk Import form on the control site, with the columns read live from the picked site, and the rows sent over the signed site call contract into the site's own Frappe Data Import.

The control site owns the grid, the structural checks, the eligibility rule and the history. The site owns the column list, the import CSV, the dry run and the import, through four new signed guest endpoints beside `remote.py`.

**Implementation skills**: `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch** (control site, `rarebooks_control`):

Books Bulk Import, named `BIMP-.#####`, track changes off, module Rarebooks Control. Billing Manager: read, write, create. No other role. No delete for anyone.

| Field | Type | Required | Notes |
|---|---|---|---|
| `hosted_site` | Link → Books Hosted Site | yes | N imports to 1 site. Link query `bulk_import.site_query` lists eligible sites only (AC-2). Can change only while `attempt` is 0 |
| `import_type` | Data | yes | A site DocType name, for example `Books Sales Invoice`, from `columns`. Can change only while `attempt` is 0. Changing the site or type clears the rows (the form asks first) |
| `submit_after_import` | Check | | Forced to 0 for `Books Expense` in `validate()` |
| `status` | Select, read only | yes | Draft · Checked · Importing · Success · Partial Success · Failed · Refused. Default Draft |
| `columns` | Long Text, hidden | | JSON from `import_columns` for this type: the columns, `date_format` and `number_format`. Fixed until Reload columns |
| `columns_fetched_on` | Datetime, read only | | |
| `rows` | Long Text, hidden | | JSON list of `{id, cells}`: `id` a uuid4 made by the form, `cells` a map of column key to text |
| `row_count` | Int, read only | | Set on save, kept after clearing |
| `checked_hash` | Data, hidden | | SHA-256 over site, type, Submit and the rows to be sent, stored by a passing `check`. `validate()` puts the status back to Draft when it no longer matches |
| `attempt` | Int, read only | | The attempt in use. A send uses `attempt` + 1 when the last attempt is confirmed, else the same `attempt` |
| `site_import` | Data, read only | | `CTRL-<name>-<attempt>`, set only once the site confirms that start. While it doesn't match the current `attempt`, that attempt is unconfirmed |
| `sending_since` | Datetime, hidden | | Set while a send is waiting on the site. A second send is refused unless it is older than 2 minutes |
| `last_progress_on` | Datetime, read only | | The last time the site's report counted more documents. Drives the 2 hour stall rule |
| `success_count`, `failed_count` | Int, read only | | Grid rows, computed from `results` |
| `results` | Long Text, hidden | | JSON map of row id → `{success, docname, message, attempt}` |
| `checked_on`, `sent_on`, `finished_on` | Datetime, read only | | `sent_on` and `finished_on` are for the latest attempt |
| `last_error` | Small Text, read only | | A translated reason, never row values or secrets |
| `rows_cleared_on` | Datetime, read only | | Set by the retention job or the removal hook. Once set, the import is final |

The cross check led to these changes from the model confirmed in the conversation: stable row ids inside `rows`, plus `checked_hash`, `sending_since` and `last_progress_on`. The `sent_rows` field was dropped, since the site now maps its file rows back to row ids itself.

On the site (`rarebooks-web`) there is no new DocType. Frappe's Data Import and Data Import Log hold the import, named `CTRL-BIMP-00012-2` (the import plus its attempt). The Data Import's `template_options` JSON also carries `control_csv_sha256` (the fingerprint for AC-8) and `control_row_ids` (the row id behind each CSV data row, in file order).

There is only one control site, so `import_ref` needs no prefix for the control site itself.

**State transitions** (Books Bulk Import `status`):

```
Draft ──check, no blocking warning──▶ Checked ──send, 2xx──▶ Importing ──report──▶ Success (final)
  ▲                                     │                       │          ──▶ Partial Success ─┐
  │                                     │                       └─stall, stop─▶ Failed ──────────┤
  │                                     └─not eligible, 409 site_locked─▶ Refused                │
  └──── a change that alters checked_hash (from Checked or Refused), or an edit of a failed row ◀┘
```

- Draft → Checked: only through `check` (AC-5, AC-6).
- Checked → Importing: only through `send`, after the eligibility check and a 2xx from `start_import`, or by adopting an unconfirmed attempt found on the site (AC-7, AC-8).
- Checked → Refused: not eligible at send, or 409 `site_locked` (AC-11). Refused → Draft by an edit, or Refused → Checked by `check` again.
- Importing → Success, Partial Success or Failed: only from an `import_report` with a finished status, or the stall rule (AC-9, AC-11).
- Partial Success or Failed → Draft: an edit of a failed row. Then Checked → Importing again as the next attempt (AC-10).
- No edits while Importing. Success, and any import with `rows_cleared_on` set, are final.

**API surface**:

Customer site (`frappe_books/subscription/bulk_import.py`, exported as `frappe_books.subscription.<name>` so `site_calls.call_site` reaches them):
- Each one is a guest POST checked by `remote._verified()`: the signature with `books_control_secret`, this site's own name, and an `issued_at` inside 5 minutes.
- Each is rate limited to 60 calls per minute and answers through `SignedCall.answer`, so every answer, an error included, is signed and echoes `issued_at`.
- None goes in `ALLOWED_METHODS`.
- Each one checks `import_type` against the site's list (AC-13).
- Each one except `import_report` answers 409 `site_locked` first when `clock.is_locked()`.

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `import_columns` | POST | none beyond `site`, `issued_at` | `types: [{doctype, schema_name, label, submittable, columns: [{key, label, fieldtype, required, options, table_label}]}]`, `date_format`, `number_format` | signed guest | 401, 409 site_locked |
| `preview_import` | POST | `import_type: str` (req), `rows: [{id, cells}]` (req) | `warnings: [{row_ids, column_key, message, blocking}]` | signed guest | 400 unknown type or bad rows, 401, 409, 413 |
| `start_import` | POST | `import_ref: str` (req, `^BIMP-\d{5,}-\d+$`), `import_type: str` (req), `submit: 0/1` (req), `rows: [{id, cells}]` (req) | `data_import`, `status`, `started: bool` | signed guest | 400, 401, 409 site_locked or ref_conflict, 413, 503 scheduler_inactive |
| `import_report` | POST | `data_import: str` (req, `^CTRL-BIMP-`), `after_log_index: int` (opt) | `status`, `total`, `processed`, and once finished `logs: [{log_index, row_ids, success, docname, message}]` (up to 500 per page, `more: bool`) and `blocking_warnings` when it went back to Pending | signed guest | 400 not a control import, 401, 404 unknown |

How the site does each call:
- **`preview_import`**:
  1. Build the CSV (AC-17) and write it to a temporary file under the site's private folder.
  2. Run `Importer(import_type, data_import=<unsaved Data Import with reference_doctype and import_type Insert New Records>, file_path=<temp>, console=True).get_data_for_import_preview()`. `console=True` makes it read a plain path.
  3. Apply `get_blocking_warnings` to mark each warning.
  4. Map file rows to row ids, and file columns to column keys.
  5. Delete the temporary file in `finally`.
- **`start_import`**:
  1. Look up `CTRL-<import_ref>`. If it exists, compare `control_csv_sha256` (409 `ref_conflict` on a mismatch), start it again if it is Pending with no logs and no queued job, and answer its status.
  2. Otherwise, as Administrator (with `frappe.set_user`, restored to Guest in `finally`), insert the Data Import with `insert(set_name=...)` so Frappe's autoname doesn't replace the name. Then insert a private File attached to it holding the CSV, set `import_file`, save, and call `start_import()`.
  3. A `DuplicateEntryError` from a start that runs at the same time is answered as the existing one.
  4. Frappe's "Scheduler is inactive" refusal is answered as a signed 503 `scheduler_inactive`.
  5. Frappe's background job runs as the user who queued it, so the records' owner is Administrator.
- **The site's doc event**: when a `CTRL-` Data Import reaches a finished status, its private File is deleted (AC-16).

Control site (`rarebooks_control/bulk_import.py`, every method type annotated, POST, Billing Manager only):

| Method | Key inputs | Key outputs | Key errors |
|---|---|---|---|
| `site_query` (link query) | `txt`, standard link query args | eligible sites | |
| `load_columns` | `name: str` | the `columns` for the type, and the `types` for the picker | site not eligible, site call failed |
| `check` | `name: str` | `status`, `warnings: [{row_ids, column_key, message, blocking}]` | over 2,000 rows or 2 MB, a row with no name, site call failed |
| `send` | `name: str` | `status`, `site_import` | status not Checked, a send already waiting, not eligible (Refused), site call failed |
| `refresh` | `name: str` | `status`, counts, `results` | site call failed (the status stays Importing) |
| `sweep` (scheduler, every 5 minutes) | | queues `refresh_job(name)` per Importing import, with a job id so it is never queued twice | |
| `clear_old_rows` (scheduler, daily) | | | |
| `clear_for_site(site)` (called from `removal.mark_removed`) | `site: str` | | |

`send` and `refresh` each take the row with `for_update` only to read and to write. The lock is never held across the call to the site (the same rule as `state.py`). `refresh` writes `results` per row id and computes the counts again, so a form refresh and a sweep job that land together give the same result. The template CSV download and the CSV load run in the browser from `columns`.

**What each site answer does**:

| Call | Answer | Books Bulk Import |
|---|---|---|
| `check` → `preview_import` | 200, no blocking warning | Checked, `checked_hash` and `checked_on` set |
| | 200 with blocking warnings | Draft, warnings painted |
| | 409 `site_locked` | Refused, reason in `last_error` |
| `send` → `start_import` | 200 | Importing, `site_import` and `sent_on` set |
| | 409 `site_locked` | Refused |
| | 409 `ref_conflict` | stays Checked, `last_error` says the site holds a different version of this attempt; `send` looks it up with `import_report` and adopts it |
| | 503 `scheduler_inactive` | stays Checked, `last_error` says the site can't run imports right now |
| any call | 400 or 413 | stays as it was, `last_error` with a translated reason (a 400 means a bug, alert ops once) |
| any call | 401 (bad secret, or a site with no secret) | stays as it was, `last_error`, ops alert through `alerts.send_ops` |
| any call | unreachable, timeout, unsigned or 5xx | stays as it was, `last_error`. A lost `start_import` answer stays unconfirmed (AC-8) |
| `refresh` → `import_report` | 404 for a confirmed attempt | Failed, the site no longer has the import |
| | no new progress for 2 hours | Failed, stall reason |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Site picker | eligible sites | Books Hosted Site `status`, `config_status`, `owner_email` and `pool_status`; Books Signup `status` by `hosted_site`; `removal.open_case(site)` |
| Type picker | the importable types | site `import_columns.types`: a Python list mirroring `getImportableSchemaNames` (as an Administrator sees it), with the stock types added when Accounting Settings `enable_inventory` is on (AC-15) |
| Grid columns | key, label, type, required, options, order | site `import_columns`, built from DocType meta with the wizard's rules. It skips hidden fields, virtual fields, read only fields that aren't required, and Attach, Attach Image and layout fields. The name column goes first and is required. Child fields are keyed `<table fieldname>.<fieldname>` and labelled `Field (Table)` |
| Dry run and import | the CSV | built on the site from `rows` and the column keys (AC-17), using System Settings `date_format` and `number_format` |
| Dry run | warnings per row and column | Frappe `Importer.get_data_for_import_preview()` plus `get_blocking_warnings`. Its file rows map to row ids through the CSV builder's row map, and its `col` to column keys through the CSV header |
| Start | the Data Import name | `CTRL-` + `import_ref`, where `import_ref` is the Books Bulk Import name, `-`, and the attempt |
| Start | the same rows or not | SHA-256 of the built CSV, kept in `template_options.control_csv_sha256` |
| Start | the records' owner | Administrator, through `frappe.set_user`, with the job queued as that user |
| Start | submit or draft | `submit_after_import`, forced off for `Books Expense` on both sides, and ignored for a type that can't be submitted |
| Report | the result per grid row | Data Import Log `row_indexes` (file rows) mapped through `template_options.control_row_ids` to row ids, plus `docname`, `success`, and the message: the log's messages, else the last line of its exception, as `getLogMessage` in `dataImport.ts` does |
| Report | the final status | the per row `results` (AC-9), plus the Data Import status for a stop |
| Stall rule | when to give up | `last_progress_on` + 2 hours |
| Retry | which rows to send | rows with no `results` entry, or one with `success` false |
| Retention | when to clear | `finished_on` + 30 days, else `modified` + 30 days, never while Importing; and the site's removal through `removal.mark_removed` |

**Key invariants**:
- One import targets exactly one site, fixed once `attempt` is above 0. `send` calls `call_site` with that `hosted_site` and no other.
- A row id with a successful result is never in a sent row set again, and that row can't be edited, moved or deleted.
- The site never runs two Data Imports for the same `import_ref`, and never runs one whose rows differ from what that ref was first sent with.
- The status is Checked only while `checked_hash` matches the current site, type, Submit and rows.
- `import_columns` and `preview_import` write nothing to the site's database. The temporary file is gone before the call answers.
- `submit_after_import` is 0 whenever `import_type` is `Books Expense`.
- The status changes only through `bulk_import.py`, never from desk (the field is read only).
- No database row lock is held across a call to the site.

**Security model**:
- **Control site**: Billing Manager only (AC-1), behind the two factor sign in from spec 0008 AC-20. The rows are customer books data, so no other role gets any permission on the DocType. Track changes is off, so the rows live only in the record itself, and the 30 day clearing and the removal hook delete them (AC-14).
- **Transport**: the existing signed contract (spec 0010 AC-2). That means an HMAC over the raw body with the site's `control_secret` (with the `pending_secret` fallback during a rotation, as `call_site` does), the `issued_at` echo, and `destinations.post`, so a site URL can't point at a private address.
- **Customer site**:
  - The four endpoints accept only a verified call naming this site, and only the site's own list of types (AC-13).
  - The import runs as Administrator, so the records' owner shows that it came from the operator, not the customer.
  - It is insert only, with no update or delete path.
  - A locked site refuses every write call. None of the endpoints is in `ALLOWED_METHODS`, so the lock stays whole, and `import_report` only reads.
- **Logging**: never log the secret, the rows, a row value or a URL query. `last_error` and alerts carry only a translated reason and an HTTP status.
- **Data left on the site**: the Data Import and its logs, which are the customer's own records. The private CSV File is deleted when the import finishes.
- **Compliance**: customer financial records pass through the control site and rest there for at most 30 days after the import. No payment card data is involved. The audit trail is the Books Bulk Import with its status comments, plus the site's Data Import named after it.

**Configuration required**:
- None new. It reuses each site's `control_secret` and `site_url` from Books Hosted Site, and the site's `books_control_secret` and `books_control_url` from site config.
- A vendored asset: Jspreadsheet CE 5.0.4 with its jsuites dependency on the 5.x line, pinned and committed under `rarebooks_control/public/js/vendor/jspreadsheet/` (JS and CSS), and loaded only by the Books Bulk Import form. Check the license file in the release before committing it, since the npm registry entry shows no license field.

**Critical test scenarios**:
- Happy path: a Billing Manager picks an eligible stub site, picks Books Item, pastes 3 rows, checks and imports. The stub's `start_import` is called once with `BIMP-00001-1`, the report gives 3 successes, and the status is Success with 3 docnames. Verifies **AC-3**, **AC-4**, **AC-7**, **AC-9**.
- Dry run on a real site: a bad date, an unknown Select option and an unknown account each come back as a warning on their own row and column. The counts of Data Import and File rows are unchanged, and no temporary file is left. Verifies **AC-5**, **AC-6**.
- Status reset: editing a cell after Checked sets Draft and `send` refuses. A save with no change keeps Checked. Verifies **AC-6**.
- The CSV builder: the golden cases cover a three row invoice whose rows are not next to each other in the grid, a numbered name that isn't sent, a `#.###,##` site with `1.234` as a quantity, and dates in the site format. They pass in both the Python and the node test. Verifies **AC-17**.
- Idempotent start: `start_import` twice, and twice in parallel, with the same ref and rows gives one Data Import. The second answer is the same Data Import with `started` false. Different rows give 409 `ref_conflict`. Verifies **AC-8**.
- Lost answer: the site starts the import but the answer times out. The status stays Checked and `attempt` stays 1. The next send finds `CTRL-BIMP-00001-1` with `import_report` and adopts it, and no second import starts. Verifies **AC-8**, **AC-11**.
- Partial and retry: 2 of 3 invoices fail on an unknown item. Fixing them sends only those rows as attempt 2, and the saved row can't be edited. The totals end at 3 saved and 0 failed. Verifies **AC-9**, **AC-10**.
- Rows moved: sorting the grid after a Partial result keeps every result on its own row. Verifies **AC-4**, **AC-10**.
- Locked site: a site set locked (and one set lapsed) with `set_hosted_phase` answers 409 `site_locked` to the three write calls and writes nothing, while `import_report` still answers. Verifies **AC-11**.
- Stall: an Importing import whose report shows no progress for 2 hours becomes Failed with the stall reason. Verifies **AC-11**.
- Eligibility: an unclaimed pool site, a site with an open removal case and a Removed site are missing from the picker and refused at `send`. Verifies **AC-2**.
- Signature: an unsigned call, a call signed for another site and a stale `issued_at` each get a signed 401 and no Data Import. Verifies **AC-11**.
- Type allowlist: `start_import` with `User` or `Role` is refused with a 400 and no Data Import. Verifies **AC-13**.
- Caps: 2,001 rows, or a body over 2 MB, is refused with no call to the site. Verifies **AC-12**.
- Existing record: importing an Account whose name exists fails that row, and the existing account is unchanged. Verifies **AC-13**.
- Scheduler off: `start_import` with the scheduler inactive answers a signed 503 and creates nothing. Verifies **AC-11**.
- Retention: a finished import 31 days old is cleared with its counts kept, then refuses `send`. An Importing one is skipped. A site reaching Removed clears all its imports at once. No Version row holds rows. Verifies **AC-14**.
- Drift guard: adding a type to `getImportableSchemaNames` without the Python list fails the test. Verifies **AC-15**.
- Auth/permission: a System Manager gets a permission error opening the list and calling `check`, `send` and `refresh`. Verifies **AC-1**.

## Build plan

The approach is Tracer Bullet: one type (Books Item, no child table, nothing to submit) goes end to end from the grid to a real site first, then the thread thickens.

1. **Site: the read side and the CSV builder.** In `frappe_books/subscription/bulk_import.py`, build:
   - the importable list mirroring `getImportableSchemaNames`, with the inventory rule;
   - the column builder from DocType meta;
   - the CSV builder of AC-17 for a type with no child table;
   - `import_columns` with the lock 409 and the type allowlist, exported from `__init__.py`.
   
   Add tests for the signature, the lock (locked and lapsed), the drift guard for types, and the column fixture for Books Item. Satisfies **AC-3**, **AC-11**, **AC-13**, **AC-15**, **AC-17**.
2. **Control site: the DocType and a thin form.** Build Books Bulk Import (desk, developer mode, Billing Manager only, track changes off, a comment on each status change), `site_query`, `load_columns`, the vendored Jspreadsheet with a plain grid and row ids, and the `checked_hash` reset in `validate()`. Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-14**, **AC-16**.
3. **The thread: one Books Item import end to end.** On the site, build `start_import` (named with `set_name`, the fingerprint, Administrator, the duplicate and scheduler answers), `import_report` with paging, and the doc event that deletes the File. On the control site, build `send` (confirmed attempts, `sending_since`, adopting an unconfirmed one), `refresh`, the form polling and the `*/5` sweep with one job per import. Test against a `call_site` stub, plus one run on a real bench site. Satisfies **AC-7**, **AC-8**, **AC-9**, **AC-13**, **AC-16**.
4. **The dry run.** Build `check` with its structural rules and the caps, and the site's `preview_import` (an unsaved Data Import, `console=True`, the temporary file deleted, blocking warnings, mapping back to row ids and column keys), with the warnings painted on the grid and Checked gating Import. Satisfies **AC-5**, **AC-6**, **AC-12**.
5. **Every type, child tables and submit.** Add child table grouping in the CSV builder, the Submit switch with the Expense rule and `mute_emails`, the column fixtures for every type (taken from the wizard's Save template), the golden CSV cases with the frontend node test, and tests for Sales Invoice and Expense like `test_data_import.py`. Satisfies **AC-3**, **AC-7**, **AC-15**, **AC-17**.
6. **Retry, refusals and the rest of the grid.** Build:
   - locked saved rows, and sending only the rows without a success as the next attempt;
   - Refused, the answer table, and the 2 hour stall rule;
   - Reload columns;
   - paste from a sheet, CSV load and template download.
   
   Satisfies **AC-3**, **AC-4**, **AC-10**, **AC-11**.
7. **Retention and removal.** Build the daily `clear_old_rows` (skipping Importing), `clear_for_site` called from `removal.mark_removed`, the final state for a cleared import, and their tests. Satisfies **AC-14**.

## Consequences

**Positive**:
- One place to load a customer's data, with the wizard's columns, the wizard's CSV shape and the site's controller rules, so what lands on the site behaves like data entered there.
- No new transport, secret or host: it uses the signed contract that removal and onboarding already use.
- The columns, the format checks and the CSV all come from the target site, so a site on a newer Books version, or with inventory off, shows and accepts exactly what it supports.

**Negative / tradeoffs**:
- The column rules and the CSV shape now live in two places: the wizard's TypeScript and the site's Python. The AC-15 and AC-17 tests catch drift in the type list, the column keys and the golden CSV cases, but not every rule. A new field property the wizard starts to honor still needs a fixture refresh.
- The control site holds customer books data for up to 30 days after an import, which widens what a control site breach would expose.
- Frappe treats a missing Link value as blocking, so one unknown Party stops the whole file at the dry run. Load in order: Accounts, Parties and Items before Invoices and Payments.
- A Partial result is normal: half a set of invoices can be saved while the rest wait for a fix. You need to read the results before telling the customer it's done.
- The 2,000 row cap means a large history goes in several imports.
- Jspreadsheet is a new vendored dependency that has to be updated by hand, and no Agent Skill or MCP server exists for it.
- Records show Administrator as their owner, so a customer can't tell which person in your team imported them. The Books Bulk Import names that person.

**Neutral**:
- A site that locks during an import leaves its job stuck, and the control site marks it Failed after 2 hours. Since nothing saved in a read only transaction, sending again after the lock lifts is safe.
- There are two new scheduler entries on the control site (`bulk_import.sweep` every 5 minutes and `bulk_import.clear_old_rows` daily), one call added to `removal.mark_removed`, and one doc event on Data Import in `frappe_books`.

## Follow-up

- [ ] Agent Skills and MCP servers for Jspreadsheet CE were searched for on 2026-11-26. None were found, so there is nothing to install.
- [ ] Add the new endpoints to `frappe_books/subscription/AGENTS.md` and the new DocType to `rarebooks_control/rarebooks_control/doctype/AGENTS.md` once they are built (`/sync`).
- [ ] Deferred: an Update existing mode, an email to the site owner after an import, a workbook with several types sent in order, and an asynchronous dry run if 2,000 rows proves too small. None is in this spec.
