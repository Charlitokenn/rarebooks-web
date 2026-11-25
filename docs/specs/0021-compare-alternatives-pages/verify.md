# Verify: compare and alternatives pages · spec 0021 · updated 2026-11-25
_The AC-1 list record, the RareBooks claims still to check on the demo shop, and the copy for your review. `/check verify` runs these; `/test` locks the durable ones._

## Competitor list

Each product checked against AC-1: (a) on sale to new customers, (b) maintained (an update dated within 12 months of the check), (c) has a cloud version.

| Slug | Checked on | (a) On sale | (b) Maintained | (c) Cloud | Result |
|---|---|---|---|---|---|
| `xero` | 2026-11-25 | Yes, three US plans sold on [the pricing page](https://www.xero.com/us/pricing-plans/) | Yes, [product update](https://blog.xero.com/product-updates/tax-season-1099-preparation-e-filing/) dated 2026-11-17 | Yes, ["Online accounting software"](https://www.xero.com/us/accounting-software/) used in the browser | Kept |

The other 20 products are checked in build plan step 3.

### Notes for your review (Xero)

- **Which market's prices.** Xero sells in many countries at different prices. The entry uses its US list prices (USD 27, 59 and 97 a month) and says prices differ by country. It ignores the temporary Black Friday discount on the page.
- **Free trial.** The US site has no free trial (only "Buy now" and discounts). The South Africa site offers 30 days with no card needed. The row says both, sourced to the South Africa sign up page. Tell me if you'd rather show one market only.
- **Mobile money.** No Xero page mentions mobile money, so the row says "Not listed", sourced to the bank feeds page, rather than claiming Xero can't hold a wallet.
- **Stock.** Xero's inventory page names up to 4,000 tracked items and the optional Inventory Plus add on. It says nothing about batches, so the row makes no batch claim either way.

## RareBooks claims to check on the demo shop (AC-5)

Claims not in `hostedPlan.included` or `hostedPlan.features`, still to confirm on the demo shop before the switch:

- [ ] Mobile money: each wallet can be set up as its own account (row template "Yes, each wallet as its own account")
- [ ] A point of sale sale updates stock and the books at once (Xero deep dive 1, RareBooks card)

## Copy review

- [ ] Read the Xero entry in `rarebooks-site/src/data/competitors.ts` (or on `/compare/xero` and `/alternatives/xero`) and approve the wording (AC-15)
