# Verify: choose dashboard accounts · spec 0003 · updated 2026-11-11
_Steps derived from spec 0003 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [x] As a Books Manager, open Settings, General tab → a "Dashboard" section sits after the Fiscal Year fields and before Tax ID / GSTIN, with a "Dashboard Accounts" table and the help line "The accounts the dashboard's Account balances card lists. Leave empty to list every cash and bank account." → AC-1
- [x] As a Books User or Books Cashier, open the same tab → the table shows with no "Add row" and no editable Account picker → AC-1
- [x] Add a row and open the Account picker → it offers only leaf Asset and Liability accounts (no groups, no Income or Expense), and offers no "Create" → AC-2
- [x] In Desk, open Books Accounting Settings and the same picker → same leaf Asset and Liability filter → AC-2
- [x] Add the same account twice and save → refused with "{account} is on the dashboard more than once." → AC-3
- [x] In Desk, add a group account, then an Income account, and save each → refused naming the account → AC-3
- [x] Save a valid pick, then in Desk turn that account into a group (or change its root type), then change another setting and save → the save succeeds → AC-3
- [x] Pick a bank and a liability with entries, save, accept "Reload RareBooks?" → the card lists exactly those two in chart order, the liability negative and in red, the Total their sum → AC-4, AC-6
- [x] Close the Settings dialog after a save without accepting the reload → the card is unchanged until the dashboard is opened again → AC-6
- [x] Make every picked account stop qualifying, or clear the table → the card lists every leaf Cash and Bank account, "No cash or bank accounts" when there are none, subtitle "As of {date}", with no note about skipped picks → AC-5
- [x] As a Books Manager, hover the settings icon in the card header → tooltip and accessible name "Choose accounts"; it shows while loading, on error, empty and loaded → AC-7
- [x] Click it on desktop → the Settings dialog opens on the General tab; tap it on a phone → the settings page opens on the General tab → AC-7
- [x] As a user who reads the ledger, Accounts and Settings but cannot write Settings → no "Choose accounts" button → AC-7
- [x] As a user without read on Accounting Settings → the Account balances card (and its row, unless Best sellers shows) is not rendered → AC-9
- [x] Try to delete a Books Account that is on the table → refused with a link error naming Books Accounting Settings; the card is unchanged → AC-8

## Value sourcing
- [x] Table editable only with write on Books Accounting Settings: compare a Books Manager and a Books User on the same tab → Settings save permission
- [ ] Help line text comes from the `dashboard_accounts` description: change it in the DocType (dev site), reload → the new text shows → DocField description via `sub_label`
- [x] Picks are stored as Books Dashboard Account rows under the single: after a save, `select account from tabBooks Dashboard Account where parenttype='Books Accounting Settings'` lists them → user's rows
- [x] "Unchanged row" is matched by row name: with a stale saved row, remove it and edit another row onto the stale account in one save → refused → `get_doc_before_save()` by row `name`
- [ ] Allowed root types come from `DASHBOARD_ROOT_TYPES` plus the leaf rule: an Equity leaf is refused on save and never listed on the card → `accounting/accounts.py`
- [x] Message label is the field label: the group or root type error starts with "Account" → `validate_account` meta label
- [x] Picker filters come from `link_filters`: the picker and Desk agree on the offered accounts → DocField `link_filters`
- [x] No Create in the picker → `withoutCreate(['account'])`
- [x] Settings read is checked before the picks are read: a user with ledger and Account read but no Settings read gets 403 from `get_cash_balances` → `has_permission` then `get_list` with `parent_doctype`
- [x] Listed accounts are picked rows still leaf Asset or Liability, else Cash and Bank: one stale and one valid pick lists only the valid one → `get_list` on Books Account, then the fallback
- [x] Row order is chart order: pick two accounts in reverse chart order → the card lists them by `lft`, not by table order → Books Account `lft`
- [ ] Balances, Total and `as_of` are unchanged from spec 0001: a reverted entry and a future dated entry on a picked account are left out → spec 0001 query
- [x] Card and row gate: removing Settings read hides the card while Best sellers stays → `canRead.ledger && canRead.accounts && canRead.settings`
- [x] Button gate: removing Settings write hides the button but keeps the card → `fyo.can(AccountingSettings, 'write')`
- [x] Button target: the link points to `/books/settings?tab=AccountingSettings` → route with `query.tab`
- [x] Card refresh: the new list appears only after the reload prompt or a new dashboard load → `useSettings.ts` reload prompt

## Commands
- [ ] `bench --site <site> migrate` on a site without the feature → `tabBooks Dashboard Account` exists, the table starts empty, the card is unchanged → AC-10
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_dashboard` → passes (picked list, fallback, stale pick, delete block, Settings read) → AC-4, AC-5, AC-8, AC-9
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_settings_accounts` → passes (save rules, stale row, moved row, `link_filters` mirror) → AC-2, AC-3
- [x] `cd frontend && node --test tests/settings-models.test.mjs tests/settings-readers.test.mjs tests/link-create.test.mjs` → passes → AC-1, AC-2
- [x] `cd frontend && yarn test:ui tests/ui/settings-form.spec.ts tests/ui/dashboard-account-balances.spec.ts tests/ui/mobile-dashboard.spec.ts` → the new tests pass → AC-1, AC-2, AC-4 to AC-7, AC-9

## Acceptance-criteria coverage
- AC-1: UI steps 1 and 2, settings-form "picked" and "Books User" tests, node test
- AC-2: UI steps 3 and 4, node test, Python mirror test
- AC-3: UI steps 5 to 7, `test_settings_accounts.py`
- AC-4: UI step 8, `test_dashboard.py` picked list test, settings-form "picked" test
- AC-5: UI step 10, `test_dashboard.py` fallback and stale tests
- AC-6: UI steps 8 and 9, settings-form "picked" test
- AC-7: UI steps 11 to 13, the "Choose accounts" Playwright tests on desktop and phone
- AC-8: UI step 15, `test_dashboard.py` delete test
- AC-9: UI step 14, `test_dashboard.py` Settings read test, "without read" Playwright test
- AC-10: migrate command
