# Verify: Best sellers chart · spec 0002 · updated 2026-11-11
_Steps derived from spec 0002 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

Run these on a real v16 site with the setup wizard done and at least six items sold this month. The steps below are suggestions; skip any that don't fit your data.

## UI / manual
- [ ] Sign in as a Books Manager, open `/books` → the Account balances row shows Account balances on the left and "Best sellers" on the right, with up to five legend entries named by item → AC-1, AC-10
- [ ] Sell six or more items this month, then open the dashboard on "This month" → the subtitle "Total sales: …" is larger than the centre value, the centre label reads "Top 5", and there is no Others entry → AC-4, AC-6
- [ ] Sell only three items in a fresh period → the centre reads "Top 3" and the subtitle equals the centre value → AC-6
- [x] Hide one legend entry → the centre value and the percents recompute over the slices still shown; the "Top N" label stays the same → AC-6
- [x] Switch the period from "This year" to "This month" → a new `get_best_sellers` request goes out with the new period and the chart redraws → AC-7
- [x] Pick a period with no sales → "No sales in this period", with no subtitle → AC-9
- [x] Block `get_best_sellers` in devtools (or stop the server for a moment) → "Failed to load" shows; Try again reloads it → AC-9
- [x] Click a slice and a legend entry → only the tooltip and the legend toggle react; the URL does not change → AC-11
- [ ] Sign in as a Books Cashier (sales read, no ledger read) → Account balances is gone and Best sellers sits in the left half; the figures match what a Manager sees → AC-8, AC-10
- [x] Sign in as a user with no Books role and call `frappe_books.reports.dashboard.get_best_sellers` directly → 403 `PermissionError` → AC-8
- [x] Open the dashboard at phone width (390 px) → Best sellers is full width on its own bordered card, 24 rem tall (`h-96`) → AC-10
- [x] Switch to dark mode → the card's text, ring and legend read clearly (frappe-ui tokens only) → AC-10

## Value sourcing (vary the input, check the output)
- [ ] Period bounds: freeze or pick a date mid month and use "This month" → only invoices from the first of the month to today count, the same as the Paid and Unpaid sales cards → AC-2
- [ ] Which invoices count: save one invoice as a draft and cancel another → neither changes any figure → AC-2
- [ ] Late on the last day: an invoice dated today at 23:30 counts; one dated tomorrow at 00:00 does not → AC-2
- [ ] Item label: each slice shows the Books Item name from the invoice row; rename an item → past sales show under the new name → AC-1
- [ ] Row net amount (discount before tax): a row of 100 with a 10% item discount counts as 90 → AC-1
- [ ] Row net amount (discount after tax): on an invoice with "Discount after tax", the row counts as `amount − (taxed − discounted)` → AC-1
- [ ] Base currency: a foreign currency invoice at exchange rate 2 counts its rows at twice their face value; the amount shows in the company currency → AC-1
- [ ] Which items are slices: two items tied at fifth place → only the one whose name sorts first is shown → AC-4
- [ ] Returns and the zero rule: return part of a sale this month → that item drops by the return; return all of it → the item leaves the slices and the total → AC-3, AC-5
- [ ] Total: with seven items sold, the subtitle equals the sum of all seven, not just the five shown → AC-6
- [ ] Formatting: amounts use the company currency symbol and number format from System Settings (compact in the centre, full in the subtitle) → AC-6
- [ ] Row visibility: a user with ledger and account read but no sales read sees Account balances alone; a user with none of them sees no row and no divider → AC-8, AC-10

## Commands
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_dashboard` → all pass, including `IntegrationTestBestSellers` (6 tests) → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-9
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_permissions` → `test_every_sales_role_gets_the_same_best_sellers_and_others_are_refused` passes → AC-8
- [x] `BOOKS_TEST_URL=<site url> yarn test:ui tests/ui/dashboard-best-sellers.spec.ts tests/ui/mobile-dashboard.spec.ts` (after `yarn build`) → the 8 best sellers tests and "best sellers sits full width on its own card" pass → AC-6, AC-7, AC-8, AC-9, AC-10, AC-11

## Acceptance-criteria coverage
- AC-1: manual 1, value sourcing (item label, both net amount rows, base currency); `test_amounts_are_after_the_row_discount_and_in_base_currency`
- AC-2: value sourcing (period bounds, which invoices count, late on the last day); `test_a_sale_late_on_the_last_day_counts_and_sales_outside_the_period_do_not`
- AC-3: value sourcing (returns); `test_returns_lower_an_item_and_drafts_and_cancelled_invoices_change_nothing`
- AC-4: manual 2, value sourcing (ties); `test_the_five_largest_items_are_returned…`, `test_ties_are_broken_by_item…`
- AC-5: value sourcing (returns and the zero rule); `test_few_items_all_come_back_and_no_sales_give_an_empty_result`
- AC-6: manual 2, 3, 4, value sourcing (total, formatting); Playwright "Top 5 centre" and "how many items came back"
- AC-7: manual 5; Playwright "changing the period"
- AC-8: manual 9, 10, value sourcing (row visibility); the permission test; Playwright "without ledger read"
- AC-9: manual 6, 7; Python "no sales"; Playwright "empty copy" and "failed load"
- AC-10: manual 1, 9, 11, 12; Playwright layout tests, desktop and phone
- AC-11: manual 8; Playwright "does not navigate"
