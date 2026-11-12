# Scope: RareBooks version-16 dashboard port

The version-16 branch is the stable release of RareBooks on Frappe 16 and MariaDB. This slice brings three dashboard features across from `develop`: the Account balances card, the Best sellers chart, and choosing which accounts the balances card lists. They are ported by hand, not cherry picked, because `develop` renamed the ledger and invoice fields that this code reads.

**Build approach:** Tracer Bullet (each feature is built end to end, server query, permission check, Vue card and tests, and works before the next starts).
**Workflow:** GA (after `/develop`: `/check verify` on a real v16 site, `/test`, a fresh model `/check review`, then `/document`). The project default level of rigor. `/architect` is the recommended first stop for a feature with a real decision, but skippable when you already know the build. Any feature can carry its own tag (e.g. `· Beta`) to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use `/develop` and skip `/architect`. You decide when a feature is `done`._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| A | Dashboard (period picker, invoice cards, cashflow, profit and loss, top expenses) | Existing | existing |
| 1 | Project context for version-16 | Foundation | done |
| 2 | Account balances card | Slice 1 | in-progress |
| 3 | Best sellers chart | Slice 2 | done |
| 4 | Choose dashboard accounts | Slice 3 | in-progress |
| 5 | Expenses | Slice 4 | in-progress |
| 6 | Trial and read only lock | Slice 5 | in-progress |
| 7 | Trial end export and site removal | Slice 5 | planned |
| 8 | Billing control site | Slice 5 | planned |

## Already built

### A. Dashboard · existing
The version-16 dashboard: a period picker, paid and unpaid invoice cards, the cashflow chart, profit and loss, and top expenses. The new cards join it as one more row. code in `frontend/src/pages/Dashboard/` and `frappe_books/reports/dashboard.py`

## Foundations

### 1. Project context for version-16 · done
version-16 has no `AGENTS.md`, so `/architect` and `/develop` have no project rules to read. Draft them from the real v16 code, so later skills don't follow develop's rules (Frappe 17, three databases).
**Done when:** root and nested `AGENTS.md` describe the v16 stack (Frappe 16, MariaDB, frappe-ui 1.0.0, `Books Ledger Entry`) and its lint, typecheck and test commands.
- [x] Capture the project context: `/audit`

## Slice 1: Account balances card

### 2. Account balances card · in-progress
A dashboard card that lists each leaf cash and bank account's balance as of today, with the total. Each account links to the General Ledger for that account. Ported from develop's spec 0001.
**Done when:** a ledger reader sees each cash and bank balance as of today and the total, the balances don't reload on a period change, a user without ledger read gets a permission error from the server and sees no card, and the card works on a phone.
spec [0001](../specs/0001-account-balances-card/index.md)
code in `frappe_books/reports/dashboard.py` and `frontend/src/pages/Dashboard/AccountBalances.vue`
- [x] Design it (spec): `/architect account balances card` (port develop's spec 0001 to the v16 names: `Books Ledger Entry`, `reverted`)
- [x] Build it: `/develop account balances card`
  - [x] Server method `get_cash_balances` with its happy path, cut off and permission tests (AC-1, AC-2, AC-4, AC-8)
  - [x] Thin card end to end: client call, minimal card, the new dashboard row and its gate, mobile mock (AC-1, AC-3, AC-4, AC-8, AC-11, AC-12)
  - [x] Card complete: colors, ledger links, scrolling with sticky header and Total, loading, empty and error states, stale load guard, zero and negative tests (AC-5, AC-6, AC-7, AC-9, AC-10, AC-12)
  - [x] Layout polish and Playwright tests, desktop and phone (AC-2, AC-3, AC-6, AC-7, AC-9, AC-10, AC-11, AC-12)
- [x] Verify it: `/check verify account balances card`
- [x] Test it: `/test account balances card`
- [x] Review it (fresh model): `/check review account balances card`
- [ ] Document it: `/document account balances card`

## Slice 2: Best sellers chart

### 3. Best sellers chart · done
A donut chart of the period's five best selling items by base currency sales, with the total sales of every item. Ported from develop's spec 0002 in its final top five shape, with no Others slice.
**Done when:** a sales reader sees the period's top five items and the total, with returns netted in. A sale made late on the period's last day counts. A user who can read sales but not the ledger still sees the chart, in the left half of the row.
spec [0002](../specs/0002-best-sellers-chart/index.md)
code in `frappe_books/reports/dashboard.py` and `frontend/src/pages/Dashboard/BestSellers.vue`
- [x] Design it (spec): `/architect best sellers chart` (port develop's spec 0002 to the v16 names: invoice `date` as a Datetime, item link `item`, `exchange_rate`, item name from the Item's own name; settle whether Frappe 16's `get_list(run=False)` works as a subquery and whether frappe-ui 1.0.0 has the chart props used)
- [x] Build it: `/develop best sellers chart`
  - [x] Server method `get_best_sellers` on one `get_list`, the shared invoice fixture, happy path and the permission test for every sales role (apply the fallback if a role fails) (AC-1, AC-4, AC-6, AC-8)
  - [x] Thin card end to end: client call, minimal `BestSellers.vue`, the widened row gate, mobile mock (AC-6, AC-7, AC-8, AC-10)
  - [x] Edge rule tests: discounts, currency, period edge, returns, draft and cancelled, zero or below, ties, few and none (AC-1, AC-2, AC-3, AC-4, AC-5, AC-9)
  - [x] Card complete and Playwright tests, desktop and phone: states, centre label, left column fallback, no click action (AC-6, AC-7, AC-9, AC-10, AC-11)
- [x] Verify it: `/check verify best sellers chart`
- [x] Test it: `/test best sellers chart`
- [x] Review it (fresh model): `/check review best sellers chart`
- [x] Document it: `/document best sellers chart`

## Slice 3: Choose dashboard accounts

### 4. Choose dashboard accounts · in-progress
Let a user who can save Accounting Settings pick which leaf asset and liability accounts the balances card lists, from a Dashboard section in Accounting Settings. With none picked, the card falls back to every cash and bank account. Ported from develop's spec 0003.
**Done when:** picked accounts show on the card in chart order. A duplicate or a non leaf, non asset, non liability pick is refused on save. A saved pick that later stops qualifying is skipped on the card and doesn't block saving other settings. The "Choose accounts" button shows only to users who can write Accounting Settings.
spec [0003](../specs/0003-choose-dashboard-accounts/index.md)
code in `frappe_books/reports/dashboard.py`, `frappe_books/frappe_books/doctype/books_accounting_settings/`, `frappe_books/frappe_books/doctype/books_dashboard_account/` and `frontend/src/pages/Dashboard/AccountBalances.vue`
- [x] Design it (spec): `/architect choose dashboard accounts` (port develop's spec 0003; merge into v16's own Accounting Settings model and controller, which differ from develop's)
- [x] Build it: `/develop choose dashboard accounts`
  - [x] Server thread: Books Dashboard Account child table, `_dashboard_accounts()` read through `get_list` with the Settings check and the Cash and Bank fallback, delete block, test helper, read path and delete tests first (AC-4, AC-5, AC-8, AC-9, AC-10)
  - [x] Settings end to end: `DashboardAccount` row model with no Create, help line in `SettingsField.vue`, read only check for non writers, node test, pick shows on the card after the reload (AC-1, AC-2, AC-6)
  - [x] Save rules and the gate: `validate_dashboard_accounts()` with the stale row rule, `canRead.settings` on the dashboard row and card, Python rule, mirror and permission tests (AC-3, AC-4, AC-5, AC-9)
  - [x] "Choose accounts" button in every card state, then Playwright tests for the settings flow, the button and the gate, desktop and phone (AC-1, AC-2, AC-4, AC-5, AC-6, AC-7, AC-9)
- [x] Verify it: `/check verify choose dashboard accounts`
- [x] Test it: `/test choose dashboard accounts`
- [x] Review it (fresh model): `/check review choose dashboard accounts`
- [ ] Document it: `/document choose dashboard accounts`

## Slice 4: Expenses

### 5. Expenses · in-progress
Let you record, view and change the money the business spends that isn't a purchase invoice (rent, utilities, fees). Expenses get their own list and form, reached from the sidebar under Purchases.
**Done when:** a user with the right role can create, view, edit and list expenses from Purchases → Expenses in the sidebar. The server checks the caller's rights for every action. The list and form work on a phone.
spec [0004](../specs/0004-expenses/index.md)
- [x] Design it (spec): `/architect expenses` (settle the data model, whether an expense posts to the ledger and feeds the dashboard's Top Expenses, which roles can record or change one, and what editing means once it is submitted)
- [ ] Build it: `/develop expenses`
  - [x] Server thread: Books Expense and its rows, the EXP- series and patch, the controller that validates, posts, cancels and deletes, and its Python tests (AC-4, AC-5, AC-6, AC-8, AC-16)
  - [x] Thin screen end to end: models, sidebar item, list, General Ledger Ref Type, node tests and a Playwright happy path (AC-1, AC-2, AC-3, AC-5, AC-6)
  - [ ] Pickers and rules: the Paid From server search with the `linkQueries` hook, supplier filters, the duplicate warning, and tests (AC-3, AC-4, AC-7, AC-8)
  - [ ] Entry points and extras: phone create menu, search, linked entries, import, print format, Duplicate (AC-9, AC-10, AC-11, AC-12, AC-13, AC-14)
  - [ ] Phone layout and the full Playwright suite, desktop and phone, with the Cashier gate (AC-8, AC-15)
- [ ] Verify it: `/check verify expenses`
- [ ] Test it: `/test expenses`
- [ ] Review it (fresh model): `/check review expenses`
- [ ] Document it: `/document expenses`

## Slice 5: Subscription gating

A new site gets a 30 day clock: days 1 to 21 are the free trial, and days 22 to 30 are the window to pay. A site that hasn't subscribed by day 26 turns read only. On day 30 the data is sent to the owner and the site is removed.

### 6. Trial and read only lock · in-progress
Track each site's trial clock and subscription state. Show how many days are left and how to subscribe. From day 26, without a subscription, the site turns read only: you can still view and export your records, but you can't add or change anything. Paying lifts the lock at once.
**Done when:** a new site has full access on days 1 to 25, sees a subscribe prompt from day 22, and from day 26 without a subscription the server refuses every create, edit, submit, cancel and delete (no matter the role) while viewing and export still work. A subscribed site is never locked. The prompt and the lock notice work on a phone.
spec [0005](../specs/0005-trial-read-only-lock/index.md)
- [x] Design it (spec): `/architect trial and read only lock` (settle where the trial clock and subscription state live and who can change them, how payment is taken and confirmed, how the server enforces read only across every doctype and whitelisted method, what export covers, and what happens with time zones and a payment that arrives late in the window)
- [ ] Build it: `/develop trial and read only lock`
  - [ ] Server thread: the read only transaction spike first, Books Subscription single and its guard, phase and time zone rules, install and patch, `before_request` and `before_job` locks with the allowlist, wildcard `doc_events`, `apply_state`, Python tests (AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-9, AC-17, AC-18)
  - [ ] Thin UI end to end: status in boot, the banner in the app shell, lock error mapping in `api.ts`, the Subscription page and sidebar item, node tests and one Playwright locked save test (AC-2, AC-3, AC-4, AC-5, AC-8)
  - [ ] Control site contract: signing helpers, `receive_state` with rate limit and replay rule, signed pull, `start_checkout`, plans and the return refresh, payment pending and Retry states, the control stub and tests (AC-10, AC-11, AC-12, AC-15, AC-16)
  - [ ] Paid lifecycle: active, renew soon, grace and lapsed texts and boundary tests (AC-13, AC-14)
  - [ ] Phone layout and the full Playwright suite, desktop and phone, across every phase (AC-19, rechecks AC-2 to AC-16)
- [ ] Verify it: `/check verify trial and read only lock`
- [ ] Test it: `/test trial and read only lock`
- [ ] Review it (fresh model): `/check review trial and read only lock`
- [ ] Document it: `/document trial and read only lock`

### 7. Trial end export and site removal · needs a decision
On day 30, if the site still hasn't subscribed, zip every record, email it to the owner, then remove the site for good. This can't be undone, so warnings go out before it happens.
**Done when:** an unsubscribed site gets warnings before day 30, then on day 30 the owner receives a zip of all their records and the site is removed. A site that subscribes at any point before the removal is never removed. A failed export or email stops the removal and gets flagged, it doesn't delete anyway.
- [ ] Design it (spec): `/architect trial end export and site removal` (settle what runs the removal, since a site can't safely remove itself, what the zip holds and in what format, how a large zip reaches the owner, the warning schedule, retries and a safety hold, and what is kept for legal or audit reasons; spec 0005 gives the day 30 `removal_on` date and the `lapsed` phase, and suggests the billing control site as the runner)

### 8. Billing control site · needs a decision
A small central Frappe app of yours (`rarebooks_control`, its own repo) that keeps the list of hosted sites and their per site secrets, takes payment (ClickPesa yearly for Tanzania, PayPal Subscriptions monthly or yearly for everyone else), and pushes each change to the customer site through the signed contract in spec 0005. Production use of feature 6 waits on it. (from spec 0005)
**Done when:** a customer site's Subscribe button reaches a real ClickPesa or PayPal checkout, a confirmed payment pushes a `paid_until` that lifts the lock within a minute, a PayPal cancel, suspend or expiry pushes the change, and a bad webhook signature changes nothing.
- [ ] Design it (spec): `/architect billing control site` (settle the site registry and secret rotation, ClickPesa checkout links, its webhook checksum header and key, and its dashboard return URL, PayPal plans and webhook verification, how `paid_until` is computed (the paid period starts at trial end when someone pays early), push retries, and where it is hosted)

## Deferred

- Tax on expenses (a Books Tax per row, posting to tax accounts), if input tax needs claiming back (from spec 0004)
- Foreign currency expenses with an exchange rate, if foreign bills become common (from spec 0004)

- Label the balances card's Total "Net" (or add a tooltip) when a picked liability is listed; revisit after real users pick one (from spec 0003)

- If the dashboard gets slow on a large site, measure `get_best_sellers` and consider an index on Books Sales Invoice `date` (from spec 0002)
- Check whether `frappe.get_list` on v16 applies a default page length from Python, which could cut rows in `get_top_expenses` and `_monthly_totals` (from spec 0001)

## Legend

**The decision box.** Every feature carries exactly one, the sub task whose label ends with `(spec)`. Skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | **`/architect` at spec capture** | `Design it` ticked; spec linked; `Build it: /develop <feature>` + **2 to 5 milestones**; the tier's closing boxes (`Verify it` Alpha+, `Test it` Beta+, `Review it` + `Document it` GA); any surfaced follow up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | **you, when you decide it is** (any skill sets it when you say so); `/sync` reconciles | boxes you ran ticked, skipped ones marked skipped; the tier's last stage (`Prototype` → after `/develop`; `Alpha` → after `/check verify`; `Beta`/`GA` → after `/test`) is the suggested point to call it done; `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for project context). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (pre workflow) and `dropped` (de scoped, kept for history).
- **Approach tag** beside a heading (e.g. `· Facade`) overrides the project default for that feature; no tag = inherits it.
- **Workflow tier tag** beside a heading (e.g. `· Beta`) sets that one feature's rigor above or below the project default; no tag inherits the default.
- **Workflow** (header line) is the project default, what runs after `/develop`: **Prototype** = nothing; **Alpha** = `/check verify`; **Beta** = `/check verify` then `/test`; **GA** = adds a fresh model `/check review` then `/document`. A feature built on an unratified decision (an `Assumed` spec) stays flagged, but that never blocks `done`.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
