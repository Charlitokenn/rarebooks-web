# Verify: Account balances card · spec 0001 · updated 2026-11-10
_Steps derived from spec 0001 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. Run them on a version-16 site (Frappe 16, MariaDB) with the setup wizard done._

## UI / manual
- [ ] Sign in as a Books Manager, open `/books` → an "Account balances" card sits below Profit and Loss and Top expenses, in the left half of its row → AC-11
- [ ] Compare the card's rows with Books Account (leaf, `account_type` Cash or Bank) → every such account is listed, in chart of accounts order, and no group or non cash account shows → AC-1
- [ ] Post a ledger entry to a cash account dated tomorrow, and reverse another entry → neither changes any balance on the card → AC-2
- [ ] Switch the period selector (This year to This quarter) with the network tab open → no `get_cash_balances` request, and the figures stay the same → AC-2, AC-12
- [ ] Read the subtitle → "As of" plus today's date in the Books date format. Set the site timezone far from your own and check that it names the server's day → AC-3
- [ ] Add up the row balances → the Total row matches, and it stays visible at the bottom → AC-4
- [ ] An account with no entries → listed, showing 0.00 in the default ink → AC-5
- [ ] Overdraw a bank account → its balance shows a minus sign in red, and a positive balance shows in green → AC-6
- [ ] Click an account → the General Ledger opens filtered to that account with To date = the card's date and no From date, and its closing balance equals the row's balance. The Total row is not a link → AC-7
- [ ] Sign in as a Books User, then as a Books Cashier → no card and no empty row. Calling `frappe_books.reports.dashboard.get_cash_balances` directly returns 403 → AC-8
- [ ] With more accounts than fit (or with 30 routed rows) → the body scrolls while the header and the Total stay visible → AC-9
- [ ] Throttle the network on first load → three skeleton bars. Block the request → "Failed to load" with Try again, and Try again recovers. Return no accounts → "No cash or bank accounts" → AC-10
- [ ] Leave the dashboard and come back while a slow load is still running → only the newer response shows → AC-12
- [ ] On a phone (390 px wide) → the card is full width on its own bordered card, 18rem (`h-72`) tall, and long names truncate. In dark mode, every color comes from a theme token → AC-11

## Value sourcing
- [ ] Listed accounts come from Books Account `account_type in (Cash, Bank)`, `is_group = 0`: change one account's type to Expense → it drops off the card
- [ ] Row order follows `lft`: move an account in the chart tree → the card order follows
- [ ] `as_of` comes from the server: set the browser clock to another day → the subtitle still names the server's day
- [ ] `balance` is debit minus credit with `reverted = 0` and `posting_date <= as_of`: compare one account against the General Ledger closing balance
- [ ] `total` is the sum of the rounded rows: use balances with three or more decimals → the Total equals the sum of the shown rows
- [ ] Amount format uses the base currency from System Settings: change the currency → the symbol follows
- [ ] Card gate needs both reads: give a role ledger read but not Account read → no card

## Commands
- [ ] `bench --site <v16-site> run-tests --app frappe_books --module frappe_books.tests.test_dashboard` → `IntegrationTestCashBalances` passes → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- [ ] `bench --site <v16-site> run-tests --app frappe_books --module frappe_books.tests.test_permissions` → `test_only_ledger_readers_get_cash_balances` and the Books User test pass → AC-8
- [ ] `cd frontend && yarn test` → the dashboard node tests pass, including "cash balances take no period" → AC-2
- [ ] `cd frontend && yarn test:ui tests/ui/dashboard-account-balances.spec.ts tests/ui/mobile-dashboard.spec.ts` → all pass → AC-2, AC-3, AC-6, AC-7, AC-9, AC-10, AC-11, AC-12

## Acceptance-criteria coverage
- AC-1: UI step 2, Python happy path · AC-2: UI steps 3 and 4, Python cut off, Playwright no reload · AC-3: UI step 5, Python `as_of`, Playwright subtitle · AC-4: UI step 6, Python total · AC-5 and AC-6: UI steps 7 and 8, Python zero and negative, Playwright colors · AC-7: UI step 9, Playwright link (the closing balance check is manual only) · AC-8: UI step 10, Python permissions · AC-9: UI step 11, Playwright scrolling · AC-10: UI step 12, Playwright empty and retry · AC-11: UI steps 1 and 14, Playwright layout · AC-12: UI steps 4 and 13, Playwright stale load
