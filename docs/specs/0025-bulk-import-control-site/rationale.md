# 0025. Bulk import from the control site: rationale

## Context

Setting up a new customer today means signing into their site and running the Import Wizard, one document type at a time, from CSV files. You, the operator, do this for customers who send their data as a spreadsheet. It works, but it means a login on every customer site, and an error only shows up after the file is uploaded.

The control site (`rarebooks_control`, spec 0008) already holds the registry of hosted sites and talks to each one over a signed HTTPS contract (spec 0010): HMAC with a per site secret, an `issued_at` window, and signed answers that echo it. It does not have `frappe_books` installed, so it doesn't know the Books DocTypes or their fields. The Import Wizard builds its columns in TypeScript in the browser from the site's DocType meta, and hands the file to Frappe's Data Import, which checks it, saves each document in its own commit, and logs each one.

Forces at play: this writes into customers' books, so it must never hit the wrong site or import a row twice. It must respect the read only lock (spec 0005) and the removal flow (spec 0007). It must not add a second source of truth for which fields a document has. And customer data on the control site should be kept as briefly as possible. Without this, customer setup stays manual, and every one needs a login on the customer's site.

## Options considered

### Option 1: Control site form, columns from the site, rows into the site's Data Import

A Books Bulk Import DocType on the control site holds the grid (Jspreadsheet), the checks and the history. You pick the site first. The site gives its columns through a signed call, runs a dry run, and imports through Frappe's Data Import under a name tied to the control site's import.

**Pros**:
- The site's own controller rules and Frappe's tested importer do the saving, exactly as the wizard does.
- The columns match the target site's version and settings (inventory on or off).
- Reuses the signed contract, secrets, rotation and `destinations.post`. No new host or credential.

**Cons**:
- The column rules exist twice (TypeScript in the wizard, Python on the site), so they need a drift test.
- The control site holds customer data until it is cleared.

### Option 2: A reference site for columns, pick the target last

The columns come from one fixed site named in settings, and you pick the target at the end, as first described.

**Pros**:
- Matches the order you first described: fill, check, then pick the site.
- One schema call, cached.

**Cons**:
- The target can differ from the reference (inventory off, older or newer Books), and that's only caught at send time, as failed rows.
- One more setting to keep pointing at a healthy site.

### Option 3: A copy of the columns kept on the control site

A static, versioned map of every importable type's columns, shipped with `rarebooks_control`.

**Pros**:
- No site call to start a grid.
- Works while the site is unreachable.

**Cons**:
- Goes stale every time a Books DocType changes, and the control site deploys on its own schedule.
- A third place the rules live.

### Option 4: All or nothing with a custom importer on the site

The site imports the whole batch in one transaction, or nothing.

**Pros**:
- No partial results to reason about.

**Cons**:
- Replaces Frappe's tested Data Import with custom code that has to mirror its parsing.
- One large transaction can time out, and it holds locks across thousands of documents.
- The wizard behaves differently, so the same file gives a different outcome in each place.

## Rationale

Option 1 is the only one where what the grid shows is what the target site accepts. Picking the site first costs one signed call and means a site with inventory off never offers Stock Movement, and a site a release ahead shows its new fields. Options 2 and 3 move that mismatch to send time, when it lands as failed rows on a customer's books, which is the failure this feature exists to prevent.

Saving through Frappe's Data Import keeps one importer for both the wizard and the control site. Each document commits on its own and is logged, which gives the keep what saved, retry the failed rows behaviour for free. Naming the Data Import `CTRL-<import>-<attempt>` makes a resend after a lost answer safe, because Frappe names are unique. That's the idempotency key the contract needs, with no new table on the site. Option 4 buys a cleaner story at the cost of rewriting a tested importer, and a long transaction on a shared server.

Jspreadsheet CE was chosen for the grid over Frappe DataTable plus a handwritten paste handler, and over a plain table. Pasting a block from Google Sheets, moving with the arrow keys and marking cells are the whole job, and Jspreadsheet does them out of the box. It is vendored and pinned (no CDN, no build step on the control site). The runner up, Frappe DataTable, ships with Frappe, but its multi cell paste would be code we own. The rules about sites (claimed, Active, no open removal case, not locked) come from how the rest of the control site treats a site that is still being built or being taken down: pushes, removal and `get_state` already skip pool sites with no owner.

Decisions settled by recommendation during writing, and after the cross check:
- **The site builds the import CSV, and the control site only checks structure**. The wizard's CSV has rules beyond dates and numbers: the `docstatus` column, grouping by name, blank parent cells on following rows, and the names it doesn't send. Frappe's preview already checks dates, numbers, Select options, required cells and missing Link values. So the site builds the CSV in one Python function, pinned to the wizard by shared golden cases, and the control site paints the site's warnings. The runner up was format rules on the control site, which would have been a third copy of the rules with no test.
- **The dry run runs Frappe's `Importer` on an unsaved Data Import with `console=True` and a temporary file**. That is the only way Frappe reads a plain path. The file is deleted before the call answers, so nothing stays in the database or on disk. The runner up was saving a Data Import and rolling back, but that leaves a private file behind.
- **The attempt number goes up only after the site confirms a start, and the site keeps a fingerprint of each attempt's CSV**. A lost answer then never becomes a second import, and a changed resend under the same name is refused. The runner up was a status lock on the control site alone, which can't tell a lost answer from a failed start.
- **Track changes is off, and each status change adds a comment instead**. Frappe's Version record copies changed Long Text fields, which would keep customer rows long after the 30 day clearing. The runner up was writing the big fields with `db_set` to keep them out of Versions, which is easy to get wrong in a form save.
- **2,000 rows and 2 MB per import**. The dry run runs inside one signed call with a 30 second limit, and a 5,000 row preview with Link lookups can pass it. The runner up was an asynchronous dry run, which is kept as a deferred follow up.
- **`import_report` still answers on a locked site, and there is a 2 hour stall rule**. A job stopped by the lock can't write its own status, so the control site needs to read it, and to give up on it. Reading leaves the lock whole.
- **Drafts never finished are also cleared 30 days after their last change**. Otherwise an abandoned draft would hold customer data forever, which goes against the retention answer.
- **A Ready Books Signup counts as part of "claimed"**. A pool site whose sign up is still Preparing has an owner email but no finished setup. Spec 0014 AC-20 already waits for Ready before removal applies.
- **Numbers are written in the site's format, with no thousands separator, by both builders** (settled 2026-11-27, during the build). Frappe's importer reads a number cell both plain and in the site's format, and warns when the two disagree. Plain output, what the wizard wrote, is misread on a `#.###,##` site whenever a value has exactly three decimals (`1.234`, `12.500`), so the wizard already had that bug. The site's format with no grouping can never be read two ways. A cell the person typed ambiguously is sent as typed, so the dry run marks it rather than guessing. The runner up was plain output in both builders, which keeps the wizard as it was but leaves the three decimal case broken in both. Keeping a different rule in each builder was rejected, since the shared golden fixture could then not cover numbers at all.
- **The number format is the importing user's, as Frappe's importer reads it, and the fixture feeds grid text with its own formats** (from the cross check, 2026-11-27). Frappe's importer reads numbers in `frappe.locale`'s format for the user the import runs as, which can differ from System Settings when a Language record sets one, so both builders take that same format: Administrator's on the site, the logged in user's in the wizard. The wizard never sees typed text (it holds parsed values), so cases about text sent as typed are marked `site_only`. Trailing zeros are trimmed in both builders so the CSV text matches exactly. The two formats with no decimal separator get a plain `.`, the only spelling of a fraction Frappe still reads for them.
