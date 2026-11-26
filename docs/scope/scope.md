# Scope: RareBooks version-16 dashboard port

The version-16 branch is the stable release of RareBooks on Frappe 16 and MariaDB. This slice brings three dashboard features across from `develop`: the Account balances card, the Best sellers chart, and choosing which accounts the balances card lists. They are ported by hand, not cherry picked, because `develop` renamed the ledger and invoice fields that this code reads.

**Build approach:** Tracer Bullet (each feature is built end to end, server query, permission check, Vue card and tests, and works before the next starts).
**Workflow:** GA (after `/develop`: `/check verify` on a real v16 site, `/test`, a fresh model `/check review`, then `/document`). The project default level of rigor. `/architect` is the recommended first stop for a feature with a real decision, but skippable when you already know the build. Any feature can carry its own tag (e.g. `· Beta`) to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use `/develop` and skip `/architect`. You decide when a feature is `done`._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| A | Dashboard (period picker, invoice cards, cashflow, profit and loss, top expenses) | Existing | existing |
| B | Marketing site, current look (homepage, compare, alternatives) | Existing | existing |
| 1 | Project context for version-16 | Foundation | done |
| 2 | Account balances card | Slice 1 | done |
| 3 | Best sellers chart | Slice 2 | done |
| 4 | Choose dashboard accounts | Slice 3 | done |
| 5 | Expenses | Slice 4 | done |
| 6 | Trial and read only lock | Slice 5 | done |
| 9 | Lock hardening | Slice 5 | in-progress |
| 7 | Trial end export and site removal | Slice 5 | in-progress |
| 8 | Billing control site | Slice 5 | in-progress |
| 11 | Hosting on Frappe Cloud | Slice 5 | in-progress |
| 12 | Custom domains on registration | Slice 5 | in-progress |
| 10 | Support chat | Slice 6 | in-progress |
| 13 | Self serve onboarding | Slice 7 | in-progress |
| 14 | Documentation links to the RareBooks docs | Slice 8 | done |
| 15 | Release a sign up | Slice 9 | in-progress |
| 16 | Marketing design system | Slice 10 | in-progress |
| 17 | Marketing nav and footer | Slice 10 | in-progress |
| 18 | Marketing homepage | Slice 10 | in-progress |
| 19 | Pricing page | Slice 10 | in-progress |
| 20 | Compare and alternatives pages | Slice 10 | in-progress |
| 21 | Sign up conversion tracking | Slice 10 | planned |
| 22 | Marketing site load speed | Slice 10 | in-progress |
| 23 | Welcome page after sign up | Slice 7 | in-progress |
| 24 | Dashboard greeting | Slice 11 | planned |

## Already built

### A. Dashboard · existing
The version-16 dashboard: a period picker, paid and unpaid invoice cards, the cashflow chart, profit and loss, and top expenses. The new cards join it as one more row. code in `frontend/src/pages/Dashboard/` and `frappe_books/reports/dashboard.py`

### B. Marketing site, current look · existing
The `rarebooks-site` marketing pages as they are before the redesign: the homepage (Hero, Comparison, Guarantee, Pricing, Call to action), the Navbar and Footer, and the compare and alternatives pages, on the purple brand tokens in `global.css`. code in `rarebooks-site` (`src/pages/index.astro`, `src/components/`, `src/layouts/CompareLayout.astro`, `src/layouts/AlternativesLayout.astro`, `src/styles/global.css`)

## Foundations

### 1. Project context for version-16 · done
version-16 has no `AGENTS.md`, so `/architect` and `/develop` have no project rules to read. Draft them from the real v16 code, so later skills don't follow develop's rules (Frappe 17, three databases).
**Done when:** root and nested `AGENTS.md` describe the v16 stack (Frappe 16, MariaDB, frappe-ui 1.0.0, `Books Ledger Entry`) and its lint, typecheck and test commands.
- [x] Capture the project context: `/audit`

## Slice 1: Account balances card

### 2. Account balances card · done
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
- [x] Document it: `/document account balances card`

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

### 4. Choose dashboard accounts · done
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
- [x] Document it: `/document choose dashboard accounts`

## Slice 4: Expenses

### 5. Expenses · done
Let you record, view and change the money the business spends that isn't a purchase invoice (rent, utilities, fees). Expenses get their own list and form, reached from the sidebar under Purchases. Bulk upload goes through the Import Wizard: Managers only, and each expense is saved as a draft (AC-12).
**Done when:** a user with the right role can create, view, edit and list expenses from Purchases → Expenses in the sidebar. The server checks the caller's rights for every action. The list and form work on a phone.
spec [0004](../specs/0004-expenses/index.md) · code in `frappe_books/frappe_books/doctype/books_expense/`, `frappe_books/accounting/accounts.py` and `frontend/models/baseModels/Expense/`
- [x] Design it (spec): `/architect expenses` (settle the data model, whether an expense posts to the ledger and feeds the dashboard's Top Expenses, which roles can record or change one, and what editing means once it is submitted)
- [x] Build it: `/develop expenses`
  - [x] Server thread: Books Expense and its rows, the EXP- series and patch, the controller that validates, posts, cancels and deletes, and its Python tests (AC-4, AC-5, AC-6, AC-8, AC-16)
  - [x] Thin screen end to end: models, sidebar item, list, General Ledger Ref Type, node tests and a Playwright happy path (AC-1, AC-2, AC-3, AC-5, AC-6)
  - [x] Pickers and rules: the Paid From server search with the `linkQueries` hook, supplier filters, the duplicate warning, and tests (AC-3, AC-4, AC-7, AC-8)
  - [x] Entry points and extras: phone create menu, search, linked entries, import, print format, Duplicate (AC-9, AC-10, AC-11, AC-12, AC-13, AC-14)
  - [x] Phone layout and the full Playwright suite, desktop and phone, with the Cashier gate (AC-8, AC-15)
  - [x] Books User pickers: two account searches gated on the expense rights, so a Books User records expenses without account rights (AC-3, AC-8, AC-17)
  - [x] Server messages: show a message returned with a successful save as a toast, so the duplicate warning reaches you, per spec [0006](../specs/0006-server-messages-on-success.md) (AC-7)
- [x] Verify it: `/check verify expenses`
- [x] Test it: `/test expenses`
- [x] Review it (fresh model): `/check review expenses`
- [x] Document it: `/document expenses`

## Slice 5: Subscription gating

A new site gets a 30 day clock: days 1 to 21 are the free trial, and days 22 to 30 are the window to pay. A site that hasn't subscribed by day 26 turns read only. On day 30 the data is sent to the owner and the site is removed.

### 6. Trial and read only lock · done
Track each site's trial clock and subscription state. Show how many days are left and how to subscribe. From day 26, without a subscription, the site turns read only: you can still view and export your records, but you can't add or change anything. Paying lifts the lock at once.
**Done when:** a new site has full access on days 1 to 25, sees a subscribe prompt from day 22, and from day 26 without a subscription the server refuses every create, edit, submit, cancel and delete (no matter the role) while viewing and export still work. A subscribed site is never locked. The prompt and the lock notice work on a phone.
spec [0005](../specs/0005-trial-read-only-lock/index.md) · code in `frappe_books/subscription/` and `frappe_books/frappe_books/doctype/books_subscription/`
- [x] Design it (spec): `/architect trial and read only lock` (settle where the trial clock and subscription state live and who can change them, how payment is taken and confirmed, how the server enforces read only across every doctype and whitelisted method, what export covers, and what happens with time zones and a payment that arrives late in the window)
- [x] Build it: `/develop trial and read only lock`
  - [x] Server thread: the read only transaction spike first, Books Subscription single and its guard, phase and time zone rules, install and patch, `before_request` and `before_job` locks with the allowlist, wildcard `doc_events`, `apply_state`, Python tests (AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-9, AC-17, AC-18)
  - [x] Thin UI end to end: status in boot, the banner in the app shell, lock error mapping in `api.ts`, the Subscription page and sidebar item, node tests and one Playwright locked save test (AC-2, AC-3, AC-4, AC-5, AC-8)
  - [x] Control site contract: signing helpers, `receive_state` with rate limit and replay rule, signed pull, `start_checkout`, plans and the return refresh, payment pending and Retry states, the control stub and tests (AC-10, AC-11, AC-12, AC-15, AC-16)
  - [x] Paid lifecycle: active, renew soon, grace and lapsed texts and boundary tests (AC-13, AC-14)
  - [x] Phone layout and the full Playwright suite, desktop and phone, across every phase (AC-19, rechecks AC-2 to AC-16)
  - [x] Review follow ups (spec 0005 milestone 6): `lock_reason` and no dates for a site locked with no trial start, and an atomic claim of the 10 second pull window that a push clears (AC-8, AC-12, AC-16)
- [x] Verify it: `/check verify trial and read only lock`
- [x] Test it: `/test trial and read only lock`
- [x] Review it (fresh model): `/check review trial and read only lock`
- [x] Document it: `/document trial and read only lock`

### 9. Lock hardening · in-progress
Close the minor findings from the fresh model review of feature 6, so the paywall holds up under real traffic and real mistakes, and make its tests independent of what the test site was left in. (from review 2026-11-18-v16-dashboard-features-trial-lock)
**Done when:** two pushes at once never answer 400 or log a false "bad value"; a checkout link is accepted only over https outside developer mode; a bad time zone in System Settings falls back to UTC and logs once instead of failing every request; Frappe's own maintenance mode no longer shows "Subscribe to make changes again"; the first refused write after a site turns read only shows the current phase's text; the time zone and concurrent push paths have tests; and the two order sensitive tests (`test_is_locked_reads_nothing_on_an_unmanaged_site`, `test_a_bad_value_answers_400_and_changes_nothing`) set their own starting state, with the Milestone 6 setup line in `verify.md` fixed.
spec [0007](../specs/0007-lock-hardening/index.md) · code in `frappe_books/subscription/` and `frontend/src/utils/subscription.ts`
- [x] Design it (spec): `/architect lock hardening` (most items update spec 0005: how concurrent pushes are serialized, the wording for a real maintenance mode, the time zone fallback, and whether the client waits for a fresh status before the first lock notice)
- [x] Build it: `/develop lock hardening`
  - [x] Server hardening: the locking read for pushes, pulls and checkout, the 400 or 500 split, the https checkout rule, and the UTC fallback in the subscription clock, with no log of its own (AC-1, AC-2, AC-3, AC-4)
  - [x] The right notice on the first refused write: `with_plans` on `get_subscription`, the awaited status, the maintenance text and the loop guard (AC-5, AC-6, AC-7)
  - [x] Tests that don't depend on the site: `clear_trial_start()`, the two order sensitive tests, and spec 0005's verify.md setup line (AC-8)
- [ ] Verify it: `/check verify lock hardening`
- [x] Test it: `/test lock hardening`
- [x] Review it (fresh model): `/check review lock hardening`
- [x] Document it: `/document lock hardening`

### 7. Trial end export and site removal · in-progress
On day 30, if the site still hasn't subscribed, zip every record, email it to the owner, then remove the site for good. This can't be undone, so warnings go out before it happens.
**Done when:** an unsubscribed site gets warnings before day 30, then on day 30 the owner receives a zip of all their records and the site is removed. A site that subscribes at any point before the removal is never removed. A failed export or email stops the removal and gets flagged, it doesn't delete anyway.
spec [0007](../specs/0007-trial-end-export-removal/index.md) · code in `frappe_books/subscription/removal.py`, `frappe_books/subscription/runner.py`, `frappe_books/commands.py`, and the `rarebooks_control` repo (Milestone 4)
- [x] Design it (spec): `/architect trial end export and site removal` (settle what runs the removal, since a site can't safely remove itself, what the zip holds and in what format, how a large zip reaches the owner, the warning schedule, retries and a safety hold, and what is kept for legal or audit reasons; spec 0005 gives the day 30 `removal_on` date and the `lapsed` phase, and suggests the billing control site as the runner)
- [ ] Build it: `/develop trial end export and site removal`
  - [x] One export end to end against stubs: lapsed `removal_on`, the two Books Subscription fields, `removal.py`, `build_export`, the `books-removal-run` command with its secrets file and signed calls, the new banner texts (AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-15, AC-18, AC-19)
  - [x] Cancel and failure paths: `clear`, `step_failed` with secret scrubbing, deferred exports, control site down (AC-11, AC-12, AC-15)
  - [x] The drop behind dry run: local and remote checks, Frappe's in process drop with the case's archived path, repeat safe, phone layout and Playwright (AC-9, AC-10, AC-14, AC-19)
  - [x] Control site removal side, in `rarebooks_control` (needs feature 8): hosting bench, removal case and warnings, signed endpoints, emails, download link, approval, cap, kill switch, alerts (AC-4, AC-5, AC-7, AC-9, AC-11 to AC-17, AC-20, AC-21)
  - [ ] Rollout: replaced by feature 11 (spec 0010), which moves the runner onto the control site and the Frappe Cloud API
- [ ] Verify it: `/check verify trial end export and site removal`
- [ ] Test it: `/test trial end export and site removal`
- [ ] Review it (fresh model): `/check review trial end export and site removal`
- [ ] Document it: `/document trial end export and site removal`

### 8. Billing control site · in-progress
A small central Frappe app of yours (`rarebooks_control`, its own repo) that keeps the list of hosted sites and their per site secrets, takes payment (ClickPesa yearly for Tanzania, PayPal Subscriptions monthly or yearly for everyone else), and pushes each change to the customer site through the signed contract in spec 0005. Production use of feature 6 waits on it. (from spec 0005)
**Done when:** a customer site's Subscribe button reaches a real ClickPesa or PayPal checkout, a confirmed payment pushes a `paid_until` that lifts the lock within a minute, a PayPal cancel, suspend or expiry pushes the change, and a bad webhook signature changes nothing.
spec [0008](../specs/0008-billing-control-site/index.md) · code in the `rarebooks_control` repo, plus `frappe_books/commands.py`, `frappe_books/subscription/control.py` and the Subscription page in this repo
- [x] Design it (spec): `/architect billing control site` (settle the site registry and secret rotation, ClickPesa checkout links, its webhook checksum header and key, and its dashboard return URL, PayPal plans and webhook verification, how `paid_until` is computed (the paid period starts at trial end when someone pays early), push retries, and where it is hosted)
- [ ] Build it: `/develop billing control site`
  - [x] The thread, one ClickPesa payment end to end against stubs: new repo and CI, the data model and Billing Manager role, signing with golden vectors and signed responses, `register_site` and `books-register-site`, `get_state`, ClickPesa checkout and webhook, lock then fetch then write, one push; this repo's contract update (AC-1, AC-2, AC-3, AC-6, AC-7, AC-8, AC-13, AC-21)
  - [x] PayPal: subscriptions with `start_time` at trial end, verified webhooks, `provider_reference` rule, money checks, refunds, double subscription cancel, the "starts on" note and refusal messages on the customer site, a sandbox run, then the sandbox date fixes: noon Pacific `start_time` and the charge day counted as paid (AC-4, AC-5, AC-9, AC-10, AC-11, AC-21, AC-23)
  - [x] Reliability: versioned push queue with retries and alerts, the return page, reconcile jobs, mismatch and unknown payment alerts, receipts, retention, `being_removed` and `billing_state()` for spec 0007 (AC-5, AC-10, AC-12, AC-13, AC-16, AC-17, AC-18, AC-19)
  - [x] Operator tools and hardening: manual edit and Push now, secret rotation through the runner, two factor sign in, per site rate limits, signature failure alert (AC-14, AC-15, AC-20, AC-22)
  - [ ] Rollout: the control bench group on Frappe Cloud comes from feature 11 (spec 0010); here, Resend, ClickPesa and PayPal live setup and the TZS 1,000 launch check (AC-3, AC-4, AC-19, AC-23)
- [ ] Verify it: `/check verify billing control site`
- [ ] Test it: `/test billing control site`
- [x] Review it (fresh model): `/check review billing control site`
- [ ] Document it: `/document billing control site`

### 11. Hosting on Frappe Cloud · in-progress
Run removal, registration and secret rotation on your Frappe Cloud dedicated server, where there is no root login, host cron or database root password. The control site drives the hourly removal round over signed HTTPS, each site builds its export in a background job and uploads it through a presigned link, and sites are archived and configured through the Frappe Cloud API. (from spec 0010, amends features 7 and 8)
**Done when:** a registered staging site goes from Pending to Active with no secret typed by hand, is taken through day 30 in dry run with its export uploaded and no archive, and a throwaway site is archived in live through the Frappe Cloud API after every gate passes; nothing in this repo or `rarebooks_control` still reads the runner secrets file or host cron.
spec [0010](../specs/0010-frappe-cloud-hosting/index.md) · amended by specs [0011](../specs/0011-archive-call-mark.md) and [0013](../specs/0013-archived-site-proof/index.md) · code in `frappe_books/subscription/remote.py`, `removal.py`, `lock.py`, and the `rarebooks_control` repo (`removal.py`, `registry.py`, `site_calls.py`, `providers/frappe_cloud.py`)
- [x] Design it (spec): `/architect hosting on Frappe Cloud`
- [ ] Build it: `/develop hosting on Frappe Cloud`
  - [x] The thread, one export driven by the control site: signed site endpoints, the export job past the lock, Books Removal Settings, the round with presigned upload and the stuck export rule (AC-1 to AC-5, AC-9, AC-17)
  - [x] The drop through Frappe Cloud: API client, guards, commit then archive, the archived poll, backup wording (AC-6, AC-7, AC-8, AC-13)
  - [x] Registration and rotation through the API: register, retry config, the 5 minute ping, the secret swap (AC-10, AC-11, AC-12, AC-16)
  - [x] Archive mark and config rules (spec 0011): `archive_requested_on` replacing `archive_job`, `config_job` removed, the locked drop poll for every config status, the digest reconciliation, the Retry config and registration fixes (spec 0011 AC-1 to AC-11; 0010 task 14)
  - [x] Archive proof (spec 0013): `site_archived` with the 403 plus released name rule in the poll, the drop start read and the reconcile; domain cleanup started only in `mark_removed` with the `domain_exists` done rule (spec 0013 AC-1 to AC-8)
  - [x] Cleanup and alerts: remove the runner and bench commands, dormant days check, digest lines (AC-14, AC-15, AC-16, AC-17)
  - [ ] Rollout on Frappe Cloud: control bench group, API key, R2, dry run on a staging site, the wrong key check, then one live archive of a throwaway site with a subdomain that reaches Removed by the spec 0013 proof and finishes its domain cleanup (AC-6, AC-7, AC-10, AC-11, AC-13, AC-14; spec 0013 AC-9)
- [ ] Verify it: `/check verify hosting on Frappe Cloud`
- [ ] Test it: `/test hosting on Frappe Cloud`
- [ ] Review it (fresh model): `/check review hosting on Frappe Cloud`
- [ ] Document it: `/document hosting on Frappe Cloud`

### 12. Custom domains on registration · in-progress
When the control site registers a hosted site, it gives the site its own `rarebooks.cc` subdomain (for example `site1.rarebooks.cc`) as its main address, with no manual DNS or Frappe Cloud steps. Extends feature 11 (spec 0010 registration) and the return link host rule in spec 0008 AC-5.
**Done when:** registering a new site creates its DNS record, adds the domain on Frappe Cloud and makes it primary, and switches the control site's `site_url` only once the new address answers with the site's signature; until then the site keeps working on its `.frappe.cloud` address, a failure is shown with a Retry like Retry config, and archiving a site removes its record and domain.
spec [0012](../specs/0012-custom-domains-registration/index.md) · amends specs 0008 (AC-5) and 0010 · amended by spec [0013](../specs/0013-archived-site-proof/index.md) (cleanup) · code in the `rarebooks_control` repo (`registry.py`, `providers/cloudflare.py`, `providers/frappe_cloud.py`, `site_calls.py`, `api.py`, `removal.py`, `removal_mail.py`, the Books Hosted Site form and list, `tests/test_domains.py`)
- [x] Design it (spec): `/architect custom domains on registration` (settle where the subdomain comes from and what happens on a clash, the DNS provider and its token's reach, proxied or DNS only, the background steps and their status, retries and alerts, the `site_url` switch, cleanup at archive, and whether demo-site and demo-us move too)
- [ ] Build it: `/develop custom domains on registration`
  - [ ] The thread, one existing site to its new address against stubs: confirm the Frappe Cloud domain methods live, the Domain fields, the Cloudflare client, Add domain, the five steps under one lock rule, the return host rule (AC-1, AC-2, AC-4 to AC-9, AC-12, AC-13)
  - [x] Registration with a required, prefilled subdomain (AC-1, AC-2, AC-3)
  - [x] Failures, Retry domain and visibility: the 2 hour rule, fail fast cases, one alert, the form headline and digest (AC-6, AC-7, AC-10, AC-12, AC-14)
  - [x] Cleanup at archive: start at the archive request, the sweep before the mode check, the done rules, the 24 hour alert (AC-11)
  - [ ] Rollout: the zone on Cloudflare, the scoped token and config keys, Add domain on demo-site and demo-us, one new registration and one archive (AC-3, AC-4, AC-8, AC-9, AC-11, AC-13)
- [ ] Verify it: `/check verify custom domains on registration`
- [ ] Test it: `/test custom domains on registration`
- [ ] Review it (fresh model): `/check review custom domains on registration`
- [ ] Document it: `/document custom domains on registration`

## Slice 6: Support chat

### 10. Support chat · in-progress · Beta
Add a tawk.to chat widget to every /books screen, so a signed in user can reach support from anywhere, including the Subscription page and the read only lock. When they start a chat, their name, email and organization show up on the visitor in the tawk.to dashboard, so you don't have to ask who they are.
**Done when:** a signed in user on any /books screen can open the chat, and the tawk.to dashboard shows their name, email and organization on that chat; the details come from the server for the signed in user, so a user can't pose as someone else; the widget still loads on a locked site; it doesn't cover key controls on a phone; and the app works normally if tawk.to is blocked or down.
spec [0009](../specs/0009-support-chat/index.md) · code in `frappe_books/support_chat.py` and `frontend/src/utils/supportChat.ts`
- [x] Design it (spec): `/architect support chat` (settle where the widget keys live and who can change them, how the name, email and organization are sent and whether they are signed so a visitor can't fake them, what counts as the organization on this site, the language the widget shows, and what users are told about the data going to tawk.to)
- [ ] Build it: `/develop support chat`
  - [x] Thin thread: the signed `support_chat` boot block from the bench config keys, and a "Chat with support" item in the app menu that loads tawk.to on first open with the bubble hidden (AC-1, AC-2, AC-3, AC-4, AC-10)
  - [x] Support details and entry points: company, site, roles, version, live phase and screen path, plus buttons on the locked banner and the Subscription page (AC-5, AC-6, AC-7)
  - [x] Failure and sign out: the load timeout toast with the support email, late load guard, `Tawk_API.logout` at sign out and the expired session guard (AC-3, AC-8, AC-9, AC-11)
  - [ ] Tests and rollout: Playwright with a stub tawk.to, rollout notes, Secure Mode on, the privacy policy naming tawk.to, and a manual check with the real widget on a hosted site (AC-1, AC-3 to AC-10)
- [ ] Verify it: `/check verify support chat`
- [ ] Test it: `/test support chat`

## Slice 7: Self serve onboarding

### 13. Self serve onboarding · in-progress
A visitor on the marketing site (the `rarebooks-site` repo) signs up, picks a subdomain, and gets their own hosted Books site at `<subdomain>.rarebooks.cc` with a trial running, with no operator step. The marketing site hands the request to the control site, which creates the site on Frappe Cloud, registers it (feature 11), sets up its subdomain (feature 12) and starts the trial (feature 6). Spans `rarebooks-site`, `rarebooks_control` and this repo. Promoted from Deferred (spec 0008).
**Done when:** a new visitor goes from the marketing site's sign up to signed in on their own `<subdomain>.rarebooks.cc` site with a trial running, with no manual step; the subdomain rules and clash checks of spec 0012 apply before anything is created; they see where their site is while it is being built, and get an email once it is ready; a failed or stuck build alerts you once and never leaves a half made site billed or unarchived; one person can't create sites without limit; and the current license key trial on the marketing site either keeps working or is retired on purpose.
spec [0014](../specs/0014-self-serve-onboarding/index.md) · amends specs 0010, 0012 and 0013 · code in `rarebooks-site` (`src/pages/api/onboarding/`, `src/pages/dashboard/`), the `rarebooks_control` repo (`onboarding.py`, `pool.py`, `registry.py`, `removal.py`, `providers/frappe_cloud.py`, Books Signup, Books Onboarding Settings) and `frappe_books/subscription/onboarding.py`
- [x] Design it (spec): `/architect self serve onboarding` (settle how the marketing site talks to the control site and how that call is signed, how a new site is created on Frappe Cloud and Books installed on it, how the first Books user is made and signed in the first time, what the visitor sees while the site is built and if it fails, limits against abuse, and what happens to the license key trial)
- [ ] Build it: `/develop self serve onboarding`
  - [x] The thread, one sign up claiming one hand made pool site: confirm `press.api.site.new` live, the schema, `claim_site` and `owner_link` on Books, the signed marketing calls, the claim and owner steps, Ready in the Primary step, the Worker form, status page, open link and Ready email (AC-1 to AC-6, AC-8 to AC-14, AC-21 to AC-24)
  - [x] The pool builds itself: skip rules, the committed Building row, `new_site`, the top up under the settings lock, the poll into config and ping (AC-11, AC-15, AC-20)
  - [x] Failures and limits: daily cap and Queued alert, owner tries, the 2 hour rule, Discard cases with the twice checked login guard and label release, build failure pause, stale pool sites, Retry (AC-10, AC-13, AC-16 to AC-19)
  - [x] Retire the desktop trial: export and drop `trials`, remove the license routes, pages and Keymint (AC-7)
  - [x] Discard over a trial case: no trial case for a Claimed site before Ready, a Discard cancels one that isn't under way, Retry on any Removed case, the sweep repairs a missing Discard (AC-17 to AC-20)
  - [ ] Rollout: settings and Worker secrets, staging with `discard_mode` dry_run, one sign up end to end, one forced failure, then live with pool size 2 (AC-1 to AC-24)
- [ ] Verify it: `/check verify self serve onboarding`
- [ ] Test it: `/test self serve onboarding`
- [ ] Review it (fresh model): `/check review self serve onboarding`
- [ ] Document it: `/document self serve onboarding`

### 23. Welcome page after sign up · in-progress
Rename `/dashboard` to `/welcome`: a reception page while a new site is being created, which sends a signed in user whose site is ready straight to their site (from spec 0022).
**Done when:** a new user waits on `/welcome` while their site is created; a signed in user whose site is ready who opens `/welcome` lands on their site; and old `/dashboard` links still work.
spec [0023](../specs/0023-welcome-page-after-sign-up/index.md) · amends spec 0014 · code in `rarebooks-site` (`src/middleware.ts`, `src/pages/welcome/`, `src/layouts/WelcomeLayout.astro`, `src/components/onboarding/`, `src/lib/onboarding/`) and the `rarebooks_control` repo (`onboarding.py` `_summary`)
- [x] Design it (spec): `/architect welcome page after sign up` (settle the route change and redirects, what the page shows while the site is created, and how it fits spec 0014's sign up flow)
- [ ] Build it: `/develop welcome page after sign up`
  - [x] The thread: shared reads, `/welcome` and `/welcome/open` with the Ready redirect, prefetch guard and retry fallback, the 302 legacy map, Clerk redirect props, load speed test updates (AC-1 to AC-4, AC-6, AC-9)
  - [x] Control site address while building, then the reception shell and the waiting, failed and Ready cards (AC-3 to AC-8, AC-11)
  - [x] Links, copy, docs page and the no `/dashboard` guard, then remove the old shell (AC-10, AC-12)
  - [ ] Staging run, then the switch to 301 after one week live (AC-1 to AC-12)
- [ ] Verify it: `/check verify welcome page after sign up`
- [ ] Test it: `/test welcome page after sign up`
- [ ] Review it (fresh model): `/check review welcome page after sign up`
- [ ] Document it: `/document welcome page after sign up`

## Slice 8: Documentation links

### 14. Documentation links to the RareBooks docs · done · Beta
The sidebar's Documentation item, the search bar's docs link and the Get started cards open the matching page on the RareBooks docs site (`rarebooks.cc`, the `rarebooks-site` repo) instead of `docs.frappe.io`. Each screen still opens its own section, as `docsPathMap` does today.
**Done when:** no link in the /books app points to `docs.frappe.io`; opening Documentation from a form, list, report or settings screen lands on that screen's page on the RareBooks docs site; a screen with no matching page (for example Sales Quote, GST reports or Expenses) opens a sensible fallback page, never a 404; and the docs base address lives in one place.
spec: [0015](../specs/0015-documentation-links/index.md)
code in `frontend/src/utils/docs.ts`, tests in `frontend/tests/docs-links.test.mjs`
- [x] Design it (spec): `/architect documentation links` (settle where the docs base address lives, the map from each screen to its RareBooks docs page, and the fallback for screens with no page yet)
- [x] Build it: `/develop documentation links`
  - [x] Thin thread: `docs.ts` (base address, map, `docsUrl`, `openDocs`) and the sidebar Documentation item and F1 on it (AC-2, AC-3)
  - [x] Guard tests: `docs_pages.json`, the 404 guard, the sibling drift check and the `docs.frappe.io` scan (AC-1, AC-8)
  - [x] Fallbacks, the search bar link and the Get started links (AC-3 to AC-6)
  - [x] Settings tab following (page and dialog), POS and Lead (AC-7)
- [x] Verify it: `/check verify documentation links`
- [x] Test it: `/test documentation links`

## Slice 9: Release a sign up

### 15. Release a sign up · in-progress
A Billing Manager can release a person's Ready or Failed sign up, with a reason, so the same email and Clerk account can sign up for another site. The old site keeps running untouched, and the marketing site drops its stale copy of the request. Amends spec 0014's one sign up per email, ever. Spans the `rarebooks_control` and `rarebooks-site` repos. from spec 0014
**Done when:** a released person signs up again from `/dashboard/start` with no hand made database edit; every release keeps who, when and why; the old site still gets its trial and removal cases; and a sign up still being set up can't be released.
spec [0016](../specs/0016-release-sign-up/index.md) · amends spec 0014 · code in `rarebooks-site` (`src/pages/api/onboarding/`, `src/lib/onboarding/signups.ts`) and the `rarebooks_control` repo (`onboarding.py`, `removal.py`, Books Signup)
- [x] Design it (spec): `/architect release sign up`
- [ ] Build it: `/develop release sign up`
  - [x] Worker heal: drop a D1 row only on a signed 404 for its request, and check it before reuse on the start form (AC-8 to AC-10)
  - [x] Control site: the Released status and fields, `release_signup` with its refusals, `fail_signup` and `awaits_signup` reading Released (AC-2 to AC-7)
  - [ ] Desk button and dialog, then a release and sign up again on staging (AC-1 to AC-10) · desk built and checked locally; the staging run is still to do
- [ ] Verify it: `/check verify release sign up`
- [ ] Test it: `/test release sign up`
- [ ] Review it (fresh model): `/check review release sign up`
- [ ] Document it: `/document release sign up`

## Slice 10: Marketing site redesign

A fresh look for the public pages of `rarebooks-site`, with the feel of Wave (waveapps.com): bright, friendly and roomy, rounded buttons, real product screenshots and alternating feature rows. It keeps the RareBooks brand, logo and copy and does not copy Wave's colors, art or words. Docs, the blog and `/dashboard` keep their current look this pass. Every page keeps its URL, title, meta and canonical link, stays fast on mobile, and meets WCAG 2.2 AA.

### 16. Marketing design system · in-progress · Beta
The shared look every redesigned page builds on: color tokens, type scale, spacing, buttons, section and card patterns, and a screenshot frame, in the style direction above. Settle how it lives beside the shadcn tokens `/dashboard` uses, so the dashboard look doesn't change.
**Done when:** the tokens and base components are in one place and documented; text and buttons pass WCAG 2.2 AA contrast with visible focus; fonts stay light enough to keep mobile Core Web Vitals good; and `/dashboard` and the docs look the same as before.
spec [0017](../specs/0017-marketing-design-system/index.md) · code in `rarebooks-site` (`src/styles/marketing.css`, `src/components/marketing/`, `src/pages/design-system.astro`, `src/layouts/Layout.astro`, `tests/marketing/`)
- [x] Design it (spec): `/architect marketing design system` (study Wave's look on a machine that can reach it, then settle the palette, type, components and where the tokens live)
- [ ] Build it: `/develop marketing design system`
  - [x] The thread: before screenshots, Fraunces, `marketing.css` on `global.css` with the color tokens and band rules, the Layout switch, `MkSection`, `MkHeading`, `MkButton`, the preview page and the contrast test (AC-1, AC-3, AC-5, AC-8)
  - [x] Full tokens, focus rings, reduced motion, fallback faces and preload, with a local Lighthouse pass (AC-1, AC-6, AC-7, AC-11)
  - [x] Content and screenshot components: highlight, card, badge, check list, FAQ, the resize script with its manifest, screenshot frame and feature row (AC-4, AC-6, AC-7, AC-8)
  - [ ] README, then the before and after checks and the deployed Lighthouse, axe and keyboard pass (AC-2, AC-3, AC-9, AC-10)
- [ ] Verify it: `/check verify marketing design system`
- [ ] Test it: `/test marketing design system`

### 17. Marketing nav and footer · in-progress · Beta
A new header and footer for every marketing page: product and resources links, Sign in, and a clear Start free trial button, working well on a phone.
**Done when:** the nav is sticky and works with keyboard and screen reader (menus open, close and trap focus correctly); on a phone it becomes a menu that opens and closes cleanly; Sign in and Start free trial reach the right Clerk and `/dashboard/start` routes; the footer lists the product, compare, docs and legal links.
spec [0018](../specs/0018-marketing-nav-footer/index.md) · code in `rarebooks-site` (`src/components/marketing/MkNav.astro`, `MkFooter.astro`, `MkLogo.astro`, `MkSocialIcon.astro`, `src/constants/navigation.ts`, `src/lib/marketing/navigation.ts`, `src/layouts/LegalLayout.astro`, `src/pages/privacy.astro`, `src/pages/terms.astro`, `tests/marketing/navigation.test.ts`)
- [x] Design it (spec): `/architect marketing nav and footer` (settle a simple nav or a dropdown menu, and the link set)
- [ ] Build it: `/develop marketing nav and footer`
  - [x] The thread: baseline numbers, the link list, logo, sticky header with the server side signed in buttons and the skip link, on the homepage (AC-2, AC-3, AC-4, AC-6, AC-8, AC-12)
  - [x] Phone menu and footer: the dialog with its close rules and scroll lock, then the four column footer with social icons (AC-5, AC-8, AC-9, AC-12)
  - [x] Spread: every marketing page and the 404, the Compare marker, old padding and the old Navbar and Footer removed (AC-1, AC-2, AC-6, AC-7)
  - [ ] Legal pages: drafted `/privacy` and `/terms` behind the approval flag, then the README, axe, keyboard and Lighthouse checks (AC-10, AC-11, AC-13)
  - [ ] Your approval: the legal name and address, the wording review, then `approved: true` (AC-10)
- [ ] Verify it: `/check verify marketing nav and footer`
- [ ] Test it: `/test marketing nav and footer`

### 18. Marketing homepage · in-progress · Beta
A homepage in the new style: a hero with a real /books screenshot and one strong call to action, a trust row, alternating feature rows with screenshots, the free trial promise, a pricing teaser and a closing call to action.
**Done when:** the homepage renders in the new style on desktop and phone; every feature row uses a real product screenshot sized for speed; title, meta, canonical and social card are unchanged or better; mobile Largest Contentful Paint stays good; and the contact modal and sign up buttons still work.
spec [0019](../specs/0019-marketing-homepage/index.md) · code in `rarebooks-site` (`src/pages/index.astro`, `src/components/marketing/home/`, `src/constants/home.ts`, `scripts/home-screenshots.mjs`, `public/og/home.jpg`) and this repo (`frappe_books/demo/shop.py`)
- [x] Design it (spec): `/architect marketing homepage` (settle the section order, the copy each section needs, and which screenshots to take)
- [ ] Build it: `/develop marketing homepage`
  - [ ] The thread: the TZS demo shop seed, the capture script with the dashboard shot, the new trial numbers and the new hero, deployed (AC-3, AC-4, AC-5, AC-15, AC-16)
  - [x] Every shot in both currencies, the social image and the new title and description (AC-8, AC-13, AC-15, AC-16)
  - [x] The trust row, feature rows, trial promise, pricing teaser and FAQ, with the signed in swap (AC-1, AC-7 to AC-12)
  - [x] The demo dialog, the closing call to action and removing the old components (AC-1, AC-2, AC-6, AC-11)
  - [ ] Checks: every claim shown on the demo shop, then Lighthouse, axe and the image budget (AC-14, AC-17)
- [ ] Verify it: `/check verify marketing homepage`
- [ ] Test it: `/test marketing homepage`

### 19. Pricing page · in-progress · Beta
Pricing in the new style, with the local (TZS) and international (USD) prices still picked from the visitor's country and the setup offers kept.
**Done when:** plans show the real prices from `src/constants/pricing.ts` in the right currency for the visitor; each plan's button starts the sign up; the comparison of what each plan includes reads well on a phone; and the existing `/#pricing` link still lands on pricing.
spec [0020](../specs/0020-pricing-page/index.md) · code in `rarebooks-site` (`src/pages/pricing.astro`, `src/components/marketing/pricing/`, `src/constants/pricingPage.ts`, `src/constants/pricing.ts`, `src/lib/marketing/pricing.ts`, `src/layouts/Layout.astro`, `src/constants/navigation.ts`, `tests/marketing/pricing.test.ts`)
- [x] Design it (spec): `/architect pricing page` (settle whether pricing stays a homepage section or gets its own `/pricing` page, and the plan table shape)
- [ ] Build it: `/develop pricing page`
  - [ ] The thread: `/pricing` with the plan cards in both currencies, the signed in swap, the cache header, the nav and footer links and the teaser's See full pricing link, deployed (AC-1, AC-3 to AC-7, AC-14)
  - [x] The setup offers, the everything included list, the FAQ and the closing call to action (AC-1, AC-2, AC-8 to AC-10)
  - [x] Search and tests: title, description, canonical, social card, the `jsonLd` Layout prop, and the node tests (AC-12, AC-13, AC-14, AC-17)
  - [ ] Checks: every claim on the demo shop or the control site, the phone pass, the Schema.org validator, then Lighthouse, axe and the keyboard (AC-11, AC-13, AC-15, AC-16)
- [ ] Verify it: `/check verify pricing page`
- [ ] Test it: `/test pricing page`

### 20. Compare and alternatives pages · in-progress · Beta
Restyle `CompareLayout` and `AlternativesLayout` and their index pages with the new design system, so all eighteen comparison pages match without editing each one.
**Done when:** every `/compare/*` and `/alternatives/*` page renders in the new style; each keeps its URL, title, meta, canonical and any structured data; and the comparison tables read well on a phone.
spec [0021](../specs/0021-compare-alternatives-pages/index.md) · code in `rarebooks-site` (`src/data/competitors.ts`, `src/data/retiredCompetitors.ts`, `src/pages/compare/`, `src/pages/alternatives/`, `src/layouts/CompareLayout.astro`, `src/layouts/AlternativesLayout.astro`, `src/components/marketing/home/HomeCta.astro`, `src/lib/marketing/breadcrumb.ts`, `src/lib/marketing/escapeHtml.ts`, `astro.config.mjs`, `tests/marketing/`)
- [x] Design it (spec): `/architect compare and alternatives pages` (phone table, structured data, bands and highlights, copy, and the competitor list refresh)
- [ ] Build it: `/develop compare and alternatives pages`
  - [x] The thread: Xero checked and written with sources, the new data shape and its tests, both `[slug]` routes and the rebuilt layouts with the phone table, signed in swap, cache header, head and breadcrumb, deployed beside the legacy pages (AC-1 to AC-13, AC-17)
  - [x] The list: all 21 products checked against the keep rule, the retired map and successors settled, borderline cases decided by you (AC-1, AC-10)
  - [x] The content: every kept and added entry researched and written with sources, RareBooks claims checked on the demo shop, your copy review (AC-3 to AC-7, AC-15)
  - [x] The switch, one commit: route 301s, the `/blog/*` redirects, the old files removed and the alphabetical index pages (AC-2, AC-7, AC-10, AC-14, AC-17)
  - [ ] Checks: phone pass, axe, Lighthouse, keyboard and the Schema.org validator on the deployed pages (AC-8, AC-9, AC-16)
- [ ] Verify it: `/check verify compare and alternatives pages`
- [ ] Test it: `/test compare and alternatives pages`

### 21. Sign up conversion tracking · needs a decision · Beta
Track clicks on every Start free trial and sign up button so you can compare conversion before and after the redesign.
**Done when:** each sign up call to action sends one named event with the page and button location; the events show in your analytics; tracking is in place on the current site before the new pages ship, so there is a baseline; and no tracking runs before any consent the privacy policy needs.
- [ ] Design it (spec): `/architect sign up conversion tracking` (settle the event names and how they reach the existing Google Tag Manager, and whether consent is needed)

### 22. Marketing site load speed · in-progress
Make every marketing page fast on a phone by loading only what first paint needs: the chat waits for the visitor's first touch, Contact us opens the chat instead of a form, Google Tag Manager gives way to a light PostHog setup, and Turnstile leaves pages that don't use it (from spec 0021, whose Checks are blocked on it).
**Done when:** every marketing page on `Layout.astro` shows LCP ≤ 2.5 s, TBT ≤ 200 ms and CLS ≤ 0.1 on the median of 3 Lighthouse mobile runs; Contact us opens the chat with an email fallback; pageviews and the sign up and contact clicks reach PostHog through `/ingest`; and a test fails if an eager script comes back.
spec [0022](../specs/0022-marketing-site-load-speed/index.md) · code in `rarebooks-site` (`src/layouts/Layout.astro`, `src/components/TawkWidget.astro`, `src/pages/ingest/`, `src/middleware.ts`, `src/pages/privacy.astro`, `tests/marketing/`)
- [x] Design it (spec): `/architect marketing site load speed`
- [ ] Build it: `/develop marketing site load speed`
  - [ ] Baseline and the thread: Lighthouse before numbers, then the chat on first interaction, deployed and measured (AC-1, AC-2, AC-12)
  - [x] Contact us opens the chat, with the form, its API route and email template removed (AC-3, AC-4, AC-12)
  - [ ] GTM out, PostHog in: the key, the snippet after load, the `/ingest` proxy, the middleware skip and the two events (AC-5 to AC-9, AC-12)
  - [ ] Turnstile out of Layout, the privacy page, then the full Lighthouse, axe and keyboard pass and the Clerk checkpoint (AC-1, AC-10, AC-11, AC-13, AC-14)
- [ ] Verify it: `/check verify marketing site load speed`
- [ ] Test it: `/test marketing site load speed`
- [ ] Review it (fresh model): `/check review marketing site load speed`
- [ ] Document it: `/document marketing site load speed`

## Slice 11: Dashboard greeting

### 24. Dashboard greeting · Beta
Greet each signed in user by name at the top of the dashboard, above the paid and unpaid invoice cards: Good morning, Good afternoon or Good evening, by the time of day.
**Done when:** the dashboard shows "Good morning, <first name>" before 12:00, "Good afternoon, <first name>" from 12:00 to 17:00 and "Good evening, <first name>" from 17:00, on the user's own device clock; the name comes from the signed in Frappe user (first name, else full name, else the greeting alone), so each user sees their own; the text is translated; and it fits on a phone.
- [ ] Build it: `/develop dashboard greeting`

## Deferred

- Add a sitemap with `/pricing`, `/compare/*` and `/alternatives/*` (from spec 0020)
- Restyle the Starlight docs, the blog and `/dashboard` to match the new marketing look (from the slice 10 scope)
- Reword the "30 day trial" lines in `site-ready-email.tsx`, `StartForm.tsx` and the `create-your-site` doc to the spec 0005 numbers (21 days free, pay by day 30) (from spec 0019)
- When the dashboard is restyled: fix `global.css`'s `--color-muted` (today the marketing gray, which `bg-muted` in the dashboard relies on) and drop `@fontsource-variable/inter` if nothing uses it (from spec 0017)

- Docs pages for Sales Quote, the GST reports and Expenses in `rarebooks-site`, then repoint their map entries (from spec 0015)

- Repoint the `docs.frappe.io` link in `rarebooks-site`'s `point-of-sale.mdx` (from spec 0015)

- Support chat: load tawk.to at app start for proactive chat if the team wants to reach out first; a widget per language keyed by the user's Frappe language (from spec 0009)

- Fiscal (TRA VFD/EFD) receipts for Tanzanian payments (from spec 0008; self serve signup moved to feature 13)

- A "Removed" page so a removed site's URL explains what happened (from spec 0007)

- Anonymize Books Signup rows some time after their site is removed (from spec 0014)

- Name Clerk, Cloudflare Turnstile and Resend in the marketing site's privacy policy (from spec 0014)

- Project context for `rarebooks-site`: `/audit` there, naming the third `signing_vectors.json` copy, `turnstile-spin` and `workers-best-practices` (from spec 0014)

- Custom domains: renaming a site's subdomain (Change domain, the old label retired), and watching an Active domain for later drift such as a certificate gone Broken (from spec 0012)

- An outside heartbeat (an uptime check on a control site URL that reports `last_run_on`), so a stopped control site scheduler alerts you (from spec 0010)

- Small polish from the feature 6 review: clamp a future `issued_at` to now when storing `last_synced_on`, return `plans_error` as a typed object, and send `days_left` in the status so the client stops copying `LOCK_DAY` and `TRIAL_LAST_DAY` (from review 2026-11-18-v16-dashboard-features-trial-lock)

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
