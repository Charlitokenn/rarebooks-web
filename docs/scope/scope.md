# Scope: RareBooks version-16 dashboard port

The version-16 branch is the stable release of RareBooks on Frappe 16 and MariaDB. This slice brings three dashboard features across from `develop`: the Account balances card, the Best sellers chart, and choosing which accounts the balances card lists. They are ported by hand, not cherry picked, because `develop` renamed the ledger and invoice fields that this code reads.

**Build approach:** Tracer Bullet (each feature is built end to end, server query, permission check, Vue card and tests, and works before the next starts).
**Workflow:** GA (after `/develop`: `/check verify` on a real v16 site, `/test`, a fresh model `/check review`, then `/document`). The project default level of rigor. `/architect` is the recommended first stop for a feature with a real decision, but skippable when you already know the build. Any feature can carry its own tag (e.g. `· Beta`) to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use `/develop` and skip `/architect`. You decide when a feature is `done`._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| A | Dashboard (period picker, invoice cards, cashflow, profit and loss, top expenses) | Existing | existing |
| 1 | Project context for version-16 | Foundation | planned |
| 2 | Account balances card | Slice 1 | in-progress |
| 3 | Best sellers chart | Slice 2 | in-progress |
| 4 | Choose dashboard accounts | Slice 3 | in-progress |

## Already built

### A. Dashboard · existing
The version-16 dashboard: a period picker, paid and unpaid invoice cards, the cashflow chart, profit and loss, and top expenses. The new cards join it as one more row. code in `frontend/src/pages/Dashboard/` and `frappe_books/reports/dashboard.py`

## Foundations

### 1. Project context for version-16
version-16 has no `AGENTS.md`, so `/architect` and `/develop` have no project rules to read. Draft them from the real v16 code, so later skills don't follow develop's rules (Frappe 17, three databases).
**Done when:** root and nested `AGENTS.md` describe the v16 stack (Frappe 16, MariaDB, frappe-ui 1.0.0, `Books Ledger Entry`) and its lint, typecheck and test commands.
- [ ] Capture the project context: `/audit`

## Slice 1: Account balances card

### 2. Account balances card · in-progress
A dashboard card that lists each leaf cash and bank account's balance as of today, with the total. Each account links to the General Ledger for that account. Ported from develop's spec 0001.
**Done when:** a ledger reader sees each cash and bank balance as of today and the total, the balances don't reload on a period change, a user without ledger read gets a permission error from the server and sees no card, and the card works on a phone.
spec [0001](../specs/0001-account-balances-card/index.md)
code in `frappe_books/reports/dashboard.py` and `frontend/src/pages/Dashboard/AccountBalances.vue`
- [x] Design it (spec): `/architect account balances card` (port develop's spec 0001 to the v16 names: `Books Ledger Entry`, `reverted`)
- [ ] Build it: `/develop account balances card`
  - [x] Server method `get_cash_balances` with its happy path, cut off and permission tests (AC-1, AC-2, AC-4, AC-8)
  - [x] Thin card end to end: client call, minimal card, the new dashboard row and its gate, mobile mock (AC-1, AC-3, AC-4, AC-8, AC-11, AC-12)
  - [x] Card complete: colors, ledger links, scrolling with sticky header and Total, loading, empty and error states, stale load guard, zero and negative tests (AC-5, AC-6, AC-7, AC-9, AC-10, AC-12)
  - [ ] Layout polish and Playwright tests, desktop and phone (AC-2, AC-3, AC-6, AC-7, AC-9, AC-10, AC-11, AC-12)
- [ ] Verify it: `/check verify account balances card`
- [ ] Test it: `/test account balances card`
- [ ] Review it (fresh model): `/check review account balances card`
- [ ] Document it: `/document account balances card`

## Slice 2: Best sellers chart

### 3. Best sellers chart · in-progress
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
- [ ] Test it: `/test best sellers chart`
- [ ] Review it (fresh model): `/check review best sellers chart`
- [ ] Document it: `/document best sellers chart`

## Slice 3: Choose dashboard accounts

### 4. Choose dashboard accounts · in-progress
Let a user who can save Accounting Settings pick which leaf asset and liability accounts the balances card lists, from a Dashboard section in Accounting Settings. With none picked, the card falls back to every cash and bank account. Ported from develop's spec 0003.
**Done when:** picked accounts show on the card in chart order. A duplicate or a non leaf, non asset, non liability pick is refused on save. A saved pick that later stops qualifying is skipped on the card and doesn't block saving other settings. The "Choose accounts" button shows only to users who can write Accounting Settings.
spec [0003](../specs/0003-choose-dashboard-accounts/index.md)
- [x] Design it (spec): `/architect choose dashboard accounts` (port develop's spec 0003; merge into v16's own Accounting Settings model and controller, which differ from develop's)
- [ ] Build it: `/develop choose dashboard accounts`
  - [ ] Server thread: Books Dashboard Account child table, `_dashboard_accounts()` read through `get_list` with the Settings check and the Cash and Bank fallback, delete block, test helper, read path and delete tests first (AC-4, AC-5, AC-8, AC-9, AC-10)
  - [ ] Settings end to end: `DashboardAccount` row model with no Create, help line in `SettingsField.vue`, read only check for non writers, node test, pick shows on the card after the reload (AC-1, AC-2, AC-6)
  - [ ] Save rules and the gate: `validate_dashboard_accounts()` with the stale row rule, `canRead.settings` on the dashboard row and card, Python rule, mirror and permission tests (AC-3, AC-4, AC-5, AC-9)
  - [ ] "Choose accounts" button in every card state, then Playwright tests for the settings flow, the button and the gate, desktop and phone (AC-1, AC-2, AC-4, AC-5, AC-6, AC-7, AC-9)
- [ ] Verify it: `/check verify choose dashboard accounts`
- [ ] Test it: `/test choose dashboard accounts`
- [ ] Review it (fresh model): `/check review choose dashboard accounts`
- [ ] Document it: `/document choose dashboard accounts`

## Deferred

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
