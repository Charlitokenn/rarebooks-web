# Verify: Documentation links · spec 0015 · updated 2026-11-23
_Steps derived from spec 0015 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

Run these on a v16 site with a fresh `yarn build` (built assets keep the old links until then).

## UI / manual
- [x] Open a Sales Invoice form, press F1 → a new tab opens `https://rarebooks.cc/transactions/sales-invoice/`, and the docs tab has no `window.opener` → AC-2, AC-3
- [x] Same from the sidebar Documentation item on the Sales Invoice list → same page → AC-3
- [x] Documentation on the Dashboard → `/basics/dashboard/`; on the General Ledger report → `/financial-reports/general-ledger/`; on Chart of Accounts → `/getting-started/chart-of-accounts/`; on a Print template → `/settings/print-templates/`; on the Import wizard → `/getting-started/import-wizard/` → AC-3
- [x] Documentation on the GSTR-1 report → `/financial-reports/reports/` (Reports fallback) → AC-4
- [x] Documentation on a list or form with no entry (for example Account or UOM) → `/masters/master-data/` → AC-4
- [x] Documentation on a Sales Quote → `/transactions/sales-invoice/`; on an Expense → `/transactions/payments/` → AC-4
- [x] Documentation on Get started (no screen path) → `/getting-started/getting-started-with-rarebooks/`, never a 404 → AC-4
- [x] Open the search bar, click its docs link → `/getting-started/quick-search/` → AC-5
- [x] On Get started, click each card's Documentation → the page in the spec's Get started table, with `#add-taxes`, `#add-sales-items`, `#add-customers` and `#creating-purchase-invoices` scrolling to their headings → AC-6
- [x] Desktop: on a Sales Invoice list open Settings, switch to Inventory → F1 opens `/inventory/inventory-settings/`; switch to POS → `/transactions/point-of-sale/`; switch to Accounting → `/settings/settings/` → AC-7
- [x] Desktop: close the Settings dialog, press F1 → back to `/transactions/sales-invoice/` (the list underneath) → AC-7
- [x] Desktop: open Settings from a cold load at `/`, close it, press F1 → `/getting-started/getting-started-with-rarebooks/` → AC-7 (verified 2026-11-23: the cold load lands on the Dashboard, so closing gives `/basics/dashboard/`, the screen underneath, as AC-7 asks; while open, F1 gives the tab's page)
- [x] Desktop: with Settings open, follow a link that routes to another screen (closing the dialog) → F1 opens that screen's page, not the old one → AC-7
- [x] Deep link `openSettings('InventorySettings')` (Get started's inventory task or a settings link) → F1 opens `/inventory/inventory-settings/` → AC-7
- [x] Phone: open `/settings?tab=InventorySettings` → Documentation opens `/inventory/inventory-settings/`; switch tab to POS → `/transactions/point-of-sale/` → AC-7
- [x] POS screen: press F1 straight after it opens, while items still load → `/transactions/point-of-sale/` → AC-7
- [x] Lead form and Lead list → `/transactions/lead/` → AC-7
- [x] Switch the UI language (for example to Swahili), press F1 on a Sales Invoice → still the English page `/transactions/sales-invoice/` (value sourcing: page language)

## Commands
- [x] `rg docs.frappe.io frontend/src` → no output → AC-1
- [x] `cd frontend && node --test tests/docs-links.test.mjs tests/app-menu.test.mjs` → all pass; the drift check runs (not skipped) when `../rarebooks-site` is checked out → AC-1 to AC-8
- [x] Rename a page in `rarebooks-site/src/content/docs` locally, rerun the test → the drift check fails; put it back → AC-8
- [x] Change one `docsPathMap` value to a made up path, rerun → the 404 guard fails; revert → AC-8
- [x] `rg "https://rarebooks.cc" frontend/src` → only `src/utils/docs.ts` → AC-2
- [x] `cd frontend && yarn test && yarn lint && yarn typecheck` → all green

## Acceptance-criteria coverage
- AC-1: Commands 1, 2
- AC-2: UI 1, Commands 5
- AC-3: UI 1 to 3
- AC-4: UI 4 to 7
- AC-5: UI 8
- AC-6: UI 9
- AC-7: UI 10 to 17
- AC-8: Commands 2 to 4
- Value sourcing: base address (Commands 5), screen path (UI 1 to 3), empty path (UI 7), overview fallbacks (UI 4, 5), Settings tab (UI 10, 15), search path (UI 8), Get started path and anchor (UI 9), page list (Commands 3, 4), page language (UI 18)
