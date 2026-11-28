# frappe_books (Frappe app)

## Overview

The server side of Books: 68 `books_*` DocTypes with their controllers, plus plain Python modules for accounting, inventory, commerce (POS, pricing, loyalty) and reports. It owns every business rule; the Vue app in `frontend/` only renders and calls into it.

## Key files

| File | Owns |
|---|---|
| `hooks.py` | Routes for `/books`, app permission, install and test hooks, scheduler, `sqlite_search`, API flags, and the subscription lock hooks (`before_request`, `before_job`, `on_session_creation`, wildcard `doc_events`) |
| `subscription/` | Trial clock, subscription state and the read only lock ([subscription/AGENTS.md](subscription/AGENTS.md)) |
| `support_chat.py` | The tawk.to chat block in the boot (`books.support_chat`): the Secure Mode visitor hash and the support attributes; never raises, off unless all three `books_tawk_*` keys are set (spec 0009) |
| `notifications/` | Push notifications through Firebase Cloud Messaging: devices, the four event hooks, the hourly subscription push and daily low stock summary, and `fcm.py`, the only module that talks to Google; off unless all three `books_fcm_*` keys are set (spec 0026, [notifications/AGENTS.md](notifications/AGENTS.md)) |
| `frappe_books/doctype/books_*/` | One DocType each: `.json`, `.py` controller, optional `.js`, `test_*.py` |
| `frappe_books/report/`, `print_format/`, `workspace/` | "Books " script reports, print formats, the workspace |
| `accounting/`, `inventory/`, `commerce/` | Shared domain logic the controllers call (ledger, settlement, stock posting, FIFO valuation, POS, pricing, loyalty) |
| `reports/` | Dashboard, financial statements, General Ledger, GST and stock queries; `filters.py` and `periods.py` helpers |
| `accounting/money.py` | Decimal helpers (`as_decimal`, `rounded`) for every amount |
| `permissions.py` | App tile permission and the preview permission check |
| `meta.py` | `get_books_meta`: all model meta in one request for the frontend |
| `search.py` | Frappe's SQLite search index (`BooksSearch`) behind the search palette |
| `setup.py`, `setup_service.py`, `coa.py`, `data/` | Install, setup wizard, charts of accounts, country info |
| `www/books.py`, `pwa/` | Serves `/books`, its service worker and the web app manifest. The manifest is served uncached at `/books/manifest.webmanifest` (`ManifestPage`), since `/assets` is cached immutable for a year and an installed phone would never see a new name or scope |
| `demo/shop.py` | `seed(currency)`: the made up Kilima Hardware shop the marketing homepage screenshots come from (spec 0019 AC-15). Refuses any site that is not local, in developer mode and without `books_control_url` |
| `tests/accounting.py` | `before_tests` helpers plus `make_account`, `make_party`, `make_item`, `make_invoice`, and `insert_sales_invoice` (writes a submitted invoice and its rows straight to the database) |

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
- A message that warns without blocking the save is `frappe.msgprint(..., indicator="orange")` (red for something worse), so /books shows a toast that stays until closed. With no indicator it fades. When the user must act, throw instead (spec 0006).
- Shared logic goes in the domain modules (`accounting/`, `inventory/`, `reports/`), not copied between controllers.
- Reports read through `frappe.get_list` with dict aggregate fields (`{"SUM": "debit"}`, `{"SUB": [...], "as": "balance"}`) and link filters like `"account.root_type"`, so the caller's read rights apply. See `reports/dashboard.py`. No raw SQL, and no `ignore_permissions` in reports.
- Tests use `frappe.tests.IntegrationTestCase` (or `UnitTestCase` when no database is needed).
- Patches are listed in `patches.txt` by section and named for what they do, for example `patches/grant_cashier_core_permissions.py`.
- A numbered DocType adds its entry to `NUMBER_SERIES` in `series.py` (prefix, reference type, Books Defaults field), the reference type to Books Number Series, the field to Books Defaults, and a patch that gives existing sites the series (see `patches/add_expense_number_series.py`).

## Gotchas

- Ledger reports filter `reverted: 0`. A reversal marks the old `Books Ledger Entry` reverted and adds a mirror row that is also reverted (`accounting/ledger.py`).
- The invoice `date` is a Datetime, the ledger `posting_date` is a Date. Bound an invoice period with `reports/filters.py` `datetime_conditions`, so a sale late on the last day still counts.
- Invoice totals in base currency use `base_grand_total`; a row converts with the invoice's `exchange_rate`.
- `Sum` comes back as a Decimal on MariaDB: wrap it with `as_decimal` and `rounded` before comparing or returning.
- To read child table fields through a parent's `frappe.get_list`, qualify them with the table name, for example `` `tabBooks Sales Invoice Item`.amount `` (see `SALES_ITEM` in `reports/dashboard.py`).
- Rows a test writes stay visible to the later tests in its `IntegrationTestCase` class, so each dashboard test keeps its invoices in its own months of 2031.
- The only `doc_events` are the wildcard (`"*"`) lock guard from `subscription/`; the search index updates through Frappe's `sqlite_search` hook.
- The test site must have the setup wizard completed (`books_setup_wizard.complete_setup`) before the Playwright tests run.
- No ERPNext doctypes exist. Do not add links, checks or fallbacks for them.
- Support chat rollout (spec 0009): set `books_tawk_property_id`, `books_tawk_widget_id`, `books_tawk_api_key` and optionally `books_support_email` with `bench set-config -g` on the hosting bench, and turn on Secure Mode for the tawk.to property, or the hash is ignored and identities are unverified. The API key is a secret: it lives only in the bench config and is read only in `support_chat.py`, but `bench get-config` and `bench show-config` print it, so don't paste their output anywhere. The browser tests put test keys in the site's own config (`tests/support_chat.py`), so they assume no real keys in `common_site_config.json` on a test bench.
- Push rollout (spec 0026): set `books_fcm_service_account` (the Firebase service account JSON, one line), `books_fcm_web_config` and `books_fcm_vapid_key` with `bench set-config -g` on the hosting bench, all from the same Firebase project (a mismatch fails every send with `SENDER_ID_MISMATCH`). The service account key is a secret read only in `notifications/fcm.py`; `bench get-config` and `bench show-config` print it, so don't paste their output anywhere. A failed send shows in the Error Log as "Books push" with only the HTTP status and FCM error code.

## Agent skills

- [frappe-app-dev](../.agents/skills/frappe-app-dev/): `frappe/skills`, building Frappe apps: doctypes, controllers, hooks (it may describe a newer Frappe; v16 behavior wins)
- [mariadb-query-optimization](../.agents/skills/mariadb-query-optimization/): `mariadb/skills`, MariaDB query tuning for the reports

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
