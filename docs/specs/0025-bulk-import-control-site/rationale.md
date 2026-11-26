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

Decisions settled by recommendation during writing:
- **Format checks run in Python on the control site, and the form only paints the cells**. The rule in `AGENTS.md` is that business rules live in Python and the client only mirrors them. The runner up was checking in JS for instant feedback, which would put a third copy of the rules in the browser.
- **The dry run uses an unsaved Data Import with a temporary file path**. Frappe's `Importer` accepts a `file_path`, so the preview writes nothing to the database or to the site's files. The runner up was saving a Data Import and rolling back, but that leaves a private file behind on disk.
- **The CSV sends ISO dates and plain numbers**. The grid accepts the site's format and converts, so Frappe's Data Import never has to guess a date format. The runner up was sending the site's own format, which relies on Frappe's guess on every row.
- **A 4 MB cap on the CSV body, besides 5,000 rows**. Long text columns can make 5,000 rows large, and the body travels in one signed call. The runner up was the row cap alone.
- **Drafts never finished are cleared 30 days after their last change too**. Otherwise an abandoned draft would hold customer data forever, which is against the retention answer. The runner up was clearing finished imports only.
- **A Ready Books Signup counts as part of "claimed"**. A pool site whose sign up is still Preparing has an owner email but no finished setup. Spec 0014 AC-20 already waits for Ready before removal applies. The runner up was `owner_email` alone.
- **The site's endpoints answer 409 on a locked site and stay out of `ALLOWED_METHODS`**. That keeps the lock whole, as you chose. A job that hits the lock mid import fails in Frappe's read only transaction and reports Failed.
