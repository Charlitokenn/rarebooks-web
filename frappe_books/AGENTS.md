# frappe_books (Frappe app)

## Overview

The server side of Books: 65 `books_*` DocTypes with their controllers, plus plain Python modules for accounting, inventory, commerce (POS, pricing, loyalty) and reports. It owns every business rule; the Vue app in `frontend/` only renders and calls into it.

## Key files

| File | Owns |
|---|---|
| `hooks.py` | Routes for `/books`, app permission, install and test hooks, scheduler, `sqlite_search`, API flags |
| `frappe_books/doctype/books_*/` | One DocType each: `.json`, `.py` controller, optional `.js`, `test_*.py` |
| `frappe_books/report/`, `print_format/`, `workspace/` | "Books " script reports, print formats, the workspace |
| `accounting/`, `inventory/`, `commerce/` | Shared domain logic the controllers call (ledger, settlement, stock posting, FIFO valuation, POS, pricing, loyalty) |
| `reports/` | Dashboard, financial statements, General Ledger, GST and stock queries; `filters.py` and `periods.py` helpers |
| `accounting/money.py` | Decimal helpers (`as_decimal`, `rounded`) for every amount |
| `permissions.py` | App tile permission and the preview permission check |
| `meta.py` | `get_books_meta`: all model meta in one request for the frontend |
| `search.py` | Frappe's SQLite search index (`BooksSearch`) behind the search palette |
| `setup.py`, `setup_service.py`, `coa.py`, `data/` | Install, setup wizard, charts of accounts, country info |
| `www/books.py`, `pwa/` | Serves `/books` and its service worker |
| `tests/accounting.py` | `before_tests` helpers plus `make_account`, `make_party`, `make_item`, `make_invoice` |

## Commands

```bash
bench --site <site> run-tests --app frappe_books
bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_dashboard
```

## Conventions

- DocType folders are `books_<snake_name>`, DocType names are `Books <Title>`.
- Controllers keep Frappe's auto generated typing block; let Frappe regenerate it rather than editing by hand.
- Whitelisted methods must have type annotations (`require_type_annotated_api_methods = True`), or Frappe refuses them. Requests send a JSON body (`use_json_request_body = True`).
- Server filled values come from a whitelisted `preview` method that fills and does not save. Mapped documents come from a whitelisted mapper in the source DocType's controller.
- Labels, placeholders (use `placeholder`, not `description`), options, defaults and required live in the DocType JSON.
- Shared logic goes in the domain modules (`accounting/`, `inventory/`, `reports/`), not copied between controllers.
- Reports read through `frappe.get_list` with dict aggregate fields (`{"SUM": "debit"}`, `{"SUB": [...], "as": "balance"}`) and link filters like `"account.root_type"`, so the caller's read rights apply. See `reports/dashboard.py`. No raw SQL, and no `ignore_permissions` in reports.
- Tests use `frappe.tests.IntegrationTestCase` (or `UnitTestCase` when no database is needed).
- Patches are listed in `patches.txt` by section and named for what they do, for example `patches/grant_cashier_core_permissions.py`.

## Gotchas

- Ledger reports filter `reverted: 0`. A reversal marks the old `Books Ledger Entry` reverted and adds a mirror row that is also reverted (`accounting/ledger.py`).
- The invoice `date` is a Datetime, the ledger `posting_date` is a Date. Bound an invoice period with `reports/filters.py` `datetime_conditions`, so a sale late on the last day still counts.
- Invoice totals in base currency use `base_grand_total`; a row converts with the invoice's `exchange_rate`.
- `Sum` comes back as a Decimal on MariaDB: wrap it with `as_decimal` and `rounded` before comparing or returning.
- There are no `doc_events`; the search index updates through Frappe's `sqlite_search` hook.
- The test site must have the setup wizard completed (`books_setup_wizard.complete_setup`) before the Playwright tests run.
- No ERPNext doctypes exist. Do not add links, checks or fallbacks for them.

## Agent skills

- [frappe-app-dev](../.agents/skills/frappe-app-dev/): `frappe/skills`, building Frappe apps: doctypes, controllers, hooks (it may describe a newer Frappe; v16 behavior wins)
- [mariadb-query-optimization](../.agents/skills/mariadb-query-optimization/): `mariadb/skills`, MariaDB query tuning for the reports

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
