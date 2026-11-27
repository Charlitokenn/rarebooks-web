# Verify: Bulk import from the control site · spec 0025 · updated 2026-11-27
_Steps derived from spec 0025 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

You can run these on the control site (`control.localhost`) with one claimed, Active test site (`books-test.localhost`) that has its control secret set. Each step is a recommendation; skip any that doesn't fit your setup.

## UI / manual
- [ ] Sign in as a System Manager and open `/app/books-bulk-import` → permission error. As a Billing Manager → the list opens, and there is no Delete action → AC-1
- [ ] New Books Bulk Import, open the site picker → only eligible sites are listed. An unclaimed pool site, a Removed site and a site with an open removal case are missing → AC-2
- [ ] Pick the site → the type picker lists the wizard's types (the stock types only when inventory is on there). Pick Books Sales Invoice → the name column comes first, required columns carry `*`, and child columns read `Field (Table)` → AC-3
- [ ] Copy a 3 row by 4 column block from Google Sheets and paste it at a cell in the middle → the cells land there, new rows are added past the end, and every row gets an id → AC-4
- [ ] Paste a block wider than the grid → an orange alert says the extra columns were left out, and no new columns appear → AC-4
- [ ] Rows menu, Download Template → the CSV opens in Excel with the site's headers, non ASCII labels readable → AC-4
- [ ] Rows menu, Load CSV with a file saved by Excel on a comma decimal locale (`;` separated, with a BOM), one header with ` *` and one unknown header → rows load, the unknown header is named and ignored → AC-4
- [ ] Check with a bad date, an unknown Select option and an unknown account → each is marked on its own row and column, the status stays Draft and Import is not offered → AC-5, AC-6
- [ ] Fix them and Check → Checked and Import appears. Edit one cell and save → back to Draft. Save with no change → stays Checked → AC-6
- [ ] Import → status Importing, the form refreshes every 5 seconds, then Success with a docname per row. On the site, `CTRL-BIMP-xxxxx-1` exists and no other site got a call → AC-7, AC-9
- [ ] Import invoices where 2 of 3 fail on an unknown item → Partial Success. Try to edit or delete the saved row → refused. Sort the grid → each result stays on its row. Fix the failed rows, Check, Import → attempt 2 sends only those rows, ending 3 saved, 0 failed → AC-9, AC-10
- [ ] While Importing, try Rows, Reload Columns, or edit a cell → no buttons for it, and a save is refused → AC-10
- [ ] Reload Columns on a Draft import after the site drops a column → the gone column is named, other cells are kept, status Draft → AC-3
- [ ] Lock the site (`set_hosted_phase` locked, then lapsed) and Check → Refused with the reason, rows kept. Unlock and Check again → Checked → AC-11

## Commands
- [ ] `bench --site control.localhost run-tests --module rarebooks_control.tests.test_bulk_import` → 25 tests pass → AC-1 to AC-14
- [ ] `bench --site books-test.localhost run-tests --app frappe_books --module frappe_books.tests.test_subscription_bulk_import` → the site side passes (signature, lock, type list, drift guard, golden CSV cases) → AC-3, AC-8, AC-11, AC-13, AC-15, AC-17
- [ ] `cd frontend && yarn test` → the golden CSV cases pass through the wizard's builder → AC-17
- [ ] In `bench --site control.localhost console`, set an Importing import's `last_progress_on` 3 hours back, then call `bulk_import.refresh(name)` → Failed with the 2 hour reason → AC-11
- [ ] Make the site answer `import_report` with 502 → the import stays Importing and `last_error` says HTTP 502, with no row values in it → AC-11, AC-16
- [ ] Set a finished import's `finished_on` 31 days back, run `bulk_import.clear_old_rows()` → `rows`, `results`, `columns` are empty, counts and status kept, and Check, Import, Refresh and edits are refused. An Importing one is skipped → AC-14
- [ ] Mark a site Removed with `removal.mark_removed` → all its imports are cleared at once → AC-14
- [ ] `select count(*) from tabVersion where ref_doctype='Books Bulk Import'` → 0 → AC-14
- [ ] Try 2,001 rows, or a body over 2 MB → refused before any site call → AC-12

## Value sourcing
- [ ] Eligible sites: flip each of `status`, `config_status`, `owner_email`, `pool_status`, the Books Signup status and an open removal case one at a time → the site drops out of the picker and `send` refuses it → AC-2
- [ ] Type list: turn inventory off on the site, Reload Columns → the four stock types are gone → AC-3
- [ ] Number format: on a `#.###,##` site, `1.234,5` and `1234.5` are both written `1234,5`, and `1.234` is marked by the dry run → AC-17
- [ ] Owner: a record imported on the site shows Administrator as its owner, and the Books Bulk Import comment names the Billing Manager → AC-7, AC-14
- [ ] Submit: Submit on for Sales Invoice gives submitted invoices; for Books Expense it is forced off → AC-7
- [ ] Retry set: after a Partial result, the next `start_import` body holds only rows with no success → AC-10
- [ ] Retention clock: a never finished import uses `modified` + 30 days, a finished one `finished_on` + 30 days → AC-14

## Acceptance-criteria coverage
- AC-1 roles · AC-2 picker and value sourcing · AC-3 type picker, Reload Columns · AC-4 paste, template, CSV load · AC-5, AC-6 dry run and status reset · AC-7 import, owner, submit · AC-8 site tests and the lost answer test · AC-9 polling, partial · AC-10 locked saved rows, retry · AC-11 lock, stall, 5xx · AC-12 caps · AC-13 site type list · AC-14 clearing, removal, Version count · AC-15 drift guard · AC-16 no row values in errors · AC-17 golden CSV cases
