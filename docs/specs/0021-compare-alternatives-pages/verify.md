# Verify: compare and alternatives pages · spec 0021 · updated 2026-11-25
_The AC-1 list record, the RareBooks claims still to check on the demo shop, and the copy for your review. `/check verify` runs these; `/test` locks the durable ones._

## Competitor list

Each product checked against AC-1: (a) on sale to new customers, (b) maintained (an update dated within 12 months of the check), (c) has a cloud version.

| Slug | Checked on | (a) On sale | (b) Maintained | (c) Cloud | Result |
|---|---|---|---|---|---|
| `xero` | 2026-11-25 | Yes, three US plans sold on [the pricing page](https://www.xero.com/us/pricing-plans/) | Yes, [product update](https://blog.xero.com/product-updates/tax-season-1099-preparation-e-filing/) dated 2026-11-17 | Yes, ["Online accounting software"](https://www.xero.com/us/accounting-software/) used in the browser | Kept |
| `manager-io` | 2026-11-25 | Yes, Cloud Edition with a [14 day trial](https://www.manager.cloud/) | Yes, version 26.5.15 in May 2026 on [the releases page](https://www.manager.io/releases/) | Yes, "Your books run in the browser at your own address" ([manager.cloud](https://www.manager.cloud/)) | Kept |
| `quickbooks` | 2026-11-25 | Yes, four plans and a 30 day trial on [the pricing page](https://quickbooks.intuit.com/pricing/) | Yes, [August 2026 product update](https://quickbooks.intuit.com/r/product-update/whats-new-quickbooks-online-august-2026/) | Yes, QuickBooks Online | Kept (new) |
| `freshbooks` | 2026-11-25 | Yes, [pricing page](https://www.freshbooks.com/pricing) | Yes, [feature news](https://www.freshbooks.com/hub/feature-news/new-features-july-2026) updated 2026-07-17 | Yes, online app | Kept (new) |
| `wave` | 2026-11-25 | Yes, Starter and Pro on [the pricing page](https://www.waveapps.com/pricing) | Yes, [product post](https://www.waveapps.com/blog/your-business-your-way) dated 2025-12-08 (inside the 12 months, but only just; check again before the next refresh) | Yes, online app | Kept (new) |
| `zoho-books` | 2026-11-25 | Yes, [pricing page](https://www.zoho.com/us/books/pricing/) | Yes, entries dated 2026-09-24 on [What's new](https://www.zoho.com/us/books/whats-new.html) | Yes, online app | Kept (new) |
| `freeagent` | 2026-11-25 | Yes, 30 day trial on [the pricing page](https://www.freeagent.com/pricing/) | Yes, [Apron integration](https://www.freeagent.com/blog/apron-integration-live/) dated 2026-11-04 | Yes, online app | Kept (new) |
| `reckon` | 2026-11-25 | Yes, Reckon One on [the pricing page](https://www.reckon.com/au/pricing/) | Yes, [Reckon One release](https://community.reckon.com/discussion/8103612/reckon-one-update-new-leave-management-bulk-printing-invoices-new-print-preview-more) dated 2026-11-17 | Yes, Reckon One is the cloud product | Kept (new; the entry covers Reckon One) |
| `myob` | 2026-11-25 | Yes, [pricing page](https://www.myob.com/au/pricing) | Yes, [AI BAS beta expanded](https://www.myob.com/au/press-releases/myob-expands-ai-bas-beta-to-employing-businesses) 2026-09-15 | Yes, "Sign in to use Lite, Pro, AccountRight and Payroll Only in your browser" (pricing page) | Kept (new) |
| `gnucash` | 2026-11-25 | Yes, free download ([gnucash.org](https://www.gnucash.org/)) | Yes, 5.17 released 2026-09-27 ([news](https://www.gnucash.org/news.phtml)) | No, a desktop program for Linux, Windows and macOS only | Retired, to `null` |
| `busy-accounting` | 2026-11-25 | Yes ([busy.in](https://busy.in/)) | Not needed | No, "BUSY on Cloud" is "Access your desktop software from anywhere with secure remote access" ([page](https://busy.in/cloud-accounting-software/)) | Retired, to `null` |
| `quickbooks-desktop` | 2026-11-25 | Enterprise only ([page](https://quickbooks.intuit.com/desktop/enterprise/)) | Not needed | No, Desktop Enterprise is a desktop program; its "Cloud Hosting" runs that same program on a hosted server | Retired, to `quickbooks` |
| `tallyprime` | 2026-11-25 | Yes ([page](https://tallysolutions.com/tally-prime/)) | Yes, TallyPrime 7.0 ([what's new](https://tallysolutions.com/events/whats-new-in-tallyprime-7-0/), 2025-12-24) | No, Cloud Access lets you "connect to virtual computers via web browsers" ([page](https://tallysolutions.com/tallyprime-cloud-access/)), a remote desktop service | Retired, to `null` |
| `turbocash` | 2026-11-25 | Yes, free download ([turbocash.net](https://www.turbocash.net/)) | Yes, SourceForge "Last Update" 2026-09-29 ([page](https://sourceforge.net/projects/turbocash/)) | No, its cloud option runs the desktop program "on Amazon Web Services, Microsoft Azure or any Windows Cloud Delivery" | Retired, to `null` |
| `zipbooks` | 2026-11-25 | Yes, [pricing page](https://zipbooks.com/pricing) | No, the newest [blog](https://zipbooks.com/blog) post is "6 years ago" and there is no changelog | Yes | Left out |
| `sage` | 2026-11-25 | Yes, Start, Standard and Plus on [the UK pricing page](https://www.sage.com/en-gb/pricing/), 30 day trial | Yes, Sage Copilot for all users, April 2026, on [product updates](https://www.sage.com/en-gb/sage-business-cloud/sage-accounting/product-updates/) | Yes, Sage Accounting is the online product | Kept (new). Read through search excerpts of the exact sage.com pages, since sage.com refuses every request from this environment |
| `sage-50` | 2026-11-25 | Yes | Yes, 2026.2 update from 2026-06-23 ([announcement](https://communityhub.sage.com/ca/sage_50/f/announcement/269260/coming-soon-product-update-2026-2-for-sage-50-accounting-software-la-mise-a-jour-du-produit-2026-2-du-logiciel-sage-50-comptabilite-arrive-bientot)) | No. It installs on a computer, and "Sage 50 Cloud" is the same program on an Azure virtual machine opened in a browser tab ([Sage FAQ](https://communityhub.sage.com/ca/sage_50/sage-50-canada-welcome-centre/w/cloud-customers/4346/tips-and-faq)), the same case as TallyPrime Cloud Access | Retired, to `sage` |
| `netsuite` | 2026-11-25 | Yes, by quote: "Price, Quote" and "Free Demo" on [netsuite.co.uk](https://www.netsuite.co.uk/portal/uk/home.shtml) | Yes, [NetSuite Version 2026.2](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_N3944673.html) is the current help version | Yes, "The #1 AI Cloud ERP" | Kept (new). netsuite.com refuses requests; the UK site answers |
| `hnry` | 2026-11-25 | Yes, pay as you go ([hnry.co.nz](https://hnry.co.nz/)) | No dated product update found on Hnry's own site | Yes, an app | Left out (your decision, 2026-11-25) |
| `wings-accounting` | 2026-11-25 | Unknown | Unknown | Unknown | Retired, to `null` (your decision, 2026-11-25) |
| `reach-accountant` | 2026-11-25 | Unknown | Unknown | Unknown | Retired, to `null` (your decision, 2026-11-25) |

### Borderline cases (decided 2026-11-25: Hnry left out, Wings and Reach retired to the index)

- **Hnry.** It's on sale and is an app, but Hnry's own site shows no dated product update, only tips posts (news sites report a QR payment feature in January 2026). It's also a tax and invoicing service for sole traders, not accounting with stock. My suggestion is to leave it out.
- **Wings Accounting.** `wingserp.com` now redirects to a parking page, and `wingsnxt.com` and `wingsaccounting.com` don't answer. Directories mention a hosted "Wings Accounting Nxt", but there's no vendor page to check. My suggestion is to retire it to `null`.
- **Reach Accountant.** `reachaccountant.com` loads, but its product and about pages return errors, the footer reads © 2020 and there's no dated update. Directories describe a cloud product from Chennai. My suggestion is to retire it to `null`.

### Sage and NetSuite (settled 2026-11-25)

NetSuite was checked on its UK site, which answers. sage.com still refuses every request, so Sage's facts come from search excerpts of the exact sage.com pages cited in the entry. Open [the UK pricing page](https://www.sage.com/en-gb/pricing/) once to confirm the prices (GBP 20, 43 and 59 a month, VAT excluded) and the 1, 3 and unlimited users.

### The redirect map this gives

`gnucash` → `null`, `busy-accounting` → `null`, `quickbooks-desktop` → `quickbooks`, `tallyprime` → `null`, `turbocash` → `null`; `wings-accounting` → `null`, `reach-accountant` → `null`, `sage-50` → `sage`. The map is final. It goes into `retiredCompetitors` only once each successor's entry exists, since the test refuses a successor that isn't in `competitors` (step 5).

### Notes for your review (Xero)

- **Which market's prices.** Xero sells in many countries at different prices. The entry uses its US list prices (USD 27, 59 and 97 a month) and says prices differ by country. It ignores the temporary Black Friday discount on the page.
- **Free trial.** The US site has no free trial (only "Buy now" and discounts). The South Africa site offers 30 days with no card needed. The row says both, sourced to the South Africa sign up page. Tell me if you'd rather show one market only.
- **Mobile money.** No Xero page mentions mobile money, so the row says "Not listed", sourced to the bank feeds page, rather than claiming Xero can't hold a wallet.
- **Stock.** Xero's inventory page names up to 4,000 tracked items and the optional Inventory Plus add on. It says nothing about batches, so the row makes no batch claim either way.

### Notes for your review (the eight entries from step 4, checked 2026-11-25)

- **Which market's prices.** Each entry uses one market and says so: US prices for QuickBooks, FreshBooks, Wave and Zoho Books; Australian prices (GST included) for Reckon One and MYOB; FreeAgent's international USD price, with the UK limited company price beside it; Manager's USD Cloud Edition price. Temporary discounts (Black Friday and new customer offers) are left out.
- **"Not listed".** Where a vendor's own pages don't mention a capability (mobile money for all eight, point of sale for most, stock for FreshBooks and FreeAgent, currencies for FreshBooks and Reckon One, users for FreeAgent), the row says "Not listed" or "Not stated" rather than claiming the product can't do it. FreshBooks may well support other currencies; its pricing page just doesn't say.
- **Wave's two help articles** (stock and foreign currency) block every request from this environment. Their wording was read through a search excerpt of those exact pages, not opened directly. Open them once to confirm: [stock](https://support.waveapps.com/hc/en-us/articles/208623546-Track-inventory-in-Wave), [currency](https://support.waveapps.com/hc/en-us/articles/360035158192-Foreign-currency-invoices-and-bills).
- **Reckon's point of sale.** Reckon's POS page describes syncing with Reckon Accounts (its desktop product) and doesn't mention Reckon One, so the row says exactly that.
- **Manager** has a legacy page that keeps serving until step 5. Its new page was checked in `astro dev` with the legacy files moved aside.
- **Sage and NetSuite** were added after step 4 (see above). Hnry is left out; Wings, Reach and Sage 50 are retired.

## RareBooks claims to check on the demo shop (AC-5)

Claims not in `hostedPlan.included` or `hostedPlan.features`, still to confirm on the demo shop before the switch:

- [x] Mobile money: each wallet can be set up as its own account (row template "Yes, each wallet as its own account"). Passed on demo-us.rarebooks.cc, checked by you on 2026-11-25.
- [ ] A point of sale sale updates stock and the books at once (Xero deep dive 1, RareBooks card)

## Copy review

- [x] Read the Xero entry in `rarebooks-site/src/data/competitors.ts` (or on `/compare/xero` and `/alternatives/xero`) and approve the wording (AC-15). Done 2026-11-25.
- [x] Read and approve the QuickBooks, FreshBooks, Wave, Zoho Books, FreeAgent, Reckon One, MYOB, Manager, Sage and NetSuite entries the same way (AC-15). Done 2026-11-25.
