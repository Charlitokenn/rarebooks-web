# 0020. Pricing page

**Date**: 2026-11-25
**Status**: In Progress

Scope: feature 19 (Slice 10, Marketing site redesign) · Beta. Code lives in the `rarebooks-site` repo. Builds on spec 0017 (the `mk` design system), spec 0018 (MkNav and MkFooter) and spec 0019 (the homepage, its copy helpers and its pricing teaser).

## Summary

Full pricing moves to its own page, `/pricing`, built from the spec 0017 components in five bands: the plans, the setup offers, an "Everything included" list, a pricing FAQ and the homepage's closing call to action. Visitors in Tanzania see one plan at TZS 300,000 a year plus the two setup offers. Everyone else sees two cards, Yearly (featured) and Monthly, plus the free data import. The page is rendered on the server for each visit (no edge cache), so the right currency and the signed in buttons show with no flash. The homepage teaser stays where it is, so old `/#pricing` links still work, and it gains a "See full pricing" link. The nav and footer Pricing links move to `/pricing`, and search engines get one fixed structured data block listing all three prices.

## Requirements

**User stories**:
- As a shop owner in Tanzania, I want to see the yearly price in shillings, how I pay, and what setup help costs, so that I know the full cost before I start a trial.
- As a business owner abroad, I want to compare monthly and yearly in dollars side by side, so that I can pick the one that suits my cash flow.
- As a visitor on a phone, I want the plans, what's included and the billing answers to read cleanly in one column, so that I don't have to zoom or scroll sideways.
- As a signed in customer, I want to check the prices without being sent to sign up again.
- As the operator, I want each plan button's clicks named in analytics, so that I can see which plan people choose.

**Acceptance criteria**:
- **AC-1**: `src/pages/pricing.astro` (`export const prerender = false`) renders `MkNav`, then `<main id="main">`, then `MkFooter` (spec 0018). Inside `<main>` are exactly these bands in this order, each an `MkSection` whose `labelledby` names its heading: plans (`canvas`, `id="plans"`, h1 `pricing-plans-title`), setup offers (`tint`, `id="setup"`, h2 `pricing-setup-title`), everything included (`canvas`, `id="included"`, h2 `pricing-included-title`), FAQ (`tint`, `id="faq"`, h2 `pricing-faq-title`), and the closing call to action (`HomeCta` from spec 0019, unchanged: `ink`, `id="cta"`, h2 `home-cta-title`). The page has one h1. `<ContactUsModal id="contact-us-modal" title="Contact Us" />` is on the page once, after `MkFooter` and outside `<main>`, as on the homepage. The response carries `Cache-Control: private, no-cache` (set in the page through `Astro.response.headers`), so no shared cache keeps a copy that is tied to a country or a session. `no-store` is not used, so the back button cache still works.
- **AC-2**: The new bands live in `src/components/marketing/pricing/` (`PricingPlans`, `PricingSetup`, `PricingIncluded`, `PricingFaq`) and are built only from `mk` components and `mk` tokens, using the text and background pairs spec 0017 allows. No new tokens and no new base components. Anything a band needs that the base components don't offer is a class inside that band's component.
- **AC-3**: Every visible string inside `<main>` is the one in *Page copy* below, word for word, with the values in braces filled from the constants named in *Value sourcing*. The Tanzania version shows when `isTanzania(Astro.locals.countryCode ?? "US")` is true, and the abroad version otherwise (so an unknown country gets the abroad version, as on the homepage). There's no currency switch and no query string that changes the version.
- **AC-4**: Each plan card is an `MkCard as="article"` with `aria-labelledby` naming its h2 (the plan name: ids `pricing-plan-tz`, `pricing-plan-yearly`, `pricing-plan-monthly`). In the Tanzania version, the plans band holds one wide card with: an `MkBadge` "The plan", the name, the price `TZS {tzsYear}` with "a year", the note, every item of `hostedPlan.features` as an `MkCheckList`, and a primary `MkButton size="lg"` Start free trial.
- **AC-5**: In the abroad version, the plans band holds two `MkCard`s side by side from 768 pixels wide, Yearly first and Monthly second. Yearly is featured: it is a plain card with a `border-2 border-mk-brand` class inside `PricingPlans` (a plain `MkCard` has no tone), an `MkBadge` "Best value" and its extra line "Free data import when you take the yearly plan during your trial" above the check list. Each card shows its name, price and period, note, every item of `hostedPlan.features` as an `MkCheckList`, and a primary `MkButton size="lg"` Start free trial. Under 768 pixels the cards stack with Yearly on top.
- **AC-6**: Under the plan cards, in both versions, one line reads "Every plan includes unlimited users and devices." Under it, a second line names the other version's price, so every price in the structured data (AC-13) is also visible to people: "Outside Tanzania: ${usdMonth} a month or ${usdYear} a year, by card or PayPal." in the Tanzania version, and "In Tanzania: TZS {tzsYear} a year, by mobile money." in the abroad version.
- **AC-7**: Every plan card's Start free trial is `<a href="/auth/sign-up" data-cta-location="pricing_page">` with `data-plan-name` `RareBooks` (the Tanzania plan), `RareBooks Yearly` or `RareBooks Monthly` (the names the old `Pricing.astro` sent, so the `trial_interest` history carries on). The Layout click handler pushes `trial_interest` with `cta_location` and `plan_name` as it does today. No plan or currency travels to sign up. For a signed in visitor (`isSignedIn(Astro.locals)`, spec 0018), each plan button and the closing call to action instead read "Go to your dashboard" (`dashboardLabel`) and link to `/dashboard`, decided on the server. They keep their `data-cta-location` but push no `trial_interest`, because the handler only counts `/auth/sign-up` links. The setup and FAQ contact buttons don't change for signed in visitors.
- **AC-8**: The setup band shows, in the Tanzania version, one `MkCard` per item of `AppConfig.localServices` in array order (Digitize your notebooks, then Quick start). In the abroad version it shows one `MkCard` per item of the new `AppConfig.abroadServices` (one item today). Each card shows the offer's name (an h3 under `pricing-setup-title`), price, price note, blurb and its features as an `MkCheckList` (none when the list is empty), and a secondary `MkButton` with the offer's `cta` text that is a `<button type="button" data-open-modal="contact-us-modal" data-cta-location="pricing_page_setup" data-plan-name="{offer name}">`, which opens the contact modal. The cards sit two across from 768 pixels wide, or one centered card when there's only one.
- **AC-9**: The everything included band shows the groups in the new `AppConfig.hostedPlan.included`, in order, each as an h3 with its items as an `MkCheckList`: one column under 640 pixels, two from 640, three from 1024. The wording is *Included list* below, word for word. `hostedPlan.features` (the 8 points the cards and the homepage teaser read) is unchanged.
- **AC-10**: The FAQ band is one `MkFaq` with the questions in *Page copy*, in order (five in each version). Under it, a "Contact us" button (`type="button"`, `data-open-modal="contact-us-modal"`, `data-cta-location="pricing_faq"`), styled as the `MkButton` `link` variant, opens the contact modal.
- **AC-11**: Every claim in *Page copy* and *Included list* is either shown working on the spec 0019 demo shop or confirmed against the control site (our receipt email after a ClickPesa and a PayPal payment, spec 0008 AC-19; one PayPal card checkout without a PayPal account; that PayPal plans renew until cancelled and that cancelling in PayPal keeps access to the end of the period; the 7 day grace; the download link email and removal of spec 0007). The free data import is a service you deliver by hand, and `verify.md` records your confirmation that it is offered as worded. Each check is recorded in `verify.md` before the build is merged. A claim that can't be shown is reworded or removed in this spec first, then in the code.
- **AC-12**: The page passes `Layout` the title "RareBooks pricing: one plan, everything included", the description in *Page copy* (the same for every visitor), `canonicalPath="/pricing"`, `ogImage="/og/home.jpg"` and `ogImageAlt` "The RareBooks dashboard showing cash and bank balances, best sellers and profit". It passes `preloadSerif`. Title, description, canonical, social card and structured data don't vary by country or sign in state.
- **AC-13**: `Layout` gains an optional `jsonLd` prop (a plain object). When set, it writes one `<script type="application/ld+json" set:html={...}>` in the head (`set:html`, so Astro doesn't HTML escape the JSON), holding `JSON.stringify(jsonLd)` with every `<` replaced by the six characters `<`. `/pricing` passes `pricingJsonLd(AppConfig)` from the new `src/lib/marketing/pricing.ts`: a `SoftwareApplication` named "RareBooks", `applicationCategory` "BusinessApplication", `operatingSystem` "Web", `url` `{rootUrl}/pricing`, and three `Offer`s: TZS `300000` yearly, USD `39` monthly and USD `399` yearly. Each `Offer` has `name` ("RareBooks Yearly (TZS)", "RareBooks Monthly", "RareBooks Yearly"), top level `price` and `priceCurrency`, `url` `{rootUrl}/pricing`, and a `priceSpecification` `UnitPriceSpecification` with the same `price` and `priceCurrency` plus `referenceQuantity` (`value` 1, `unitCode` `ANN` or `MON`). Each price is the constant with its thousands commas removed. The Schema.org validator reports no errors for the deployed page (recorded in `verify.md`). Google rich result eligibility is not required, because `SoftwareApplication` rich results need ratings, which we don't have and won't invent.
- **AC-14**: In `src/constants/navigation.ts`, the Pricing entry in `navLinks` and in the footer's Product column becomes `/pricing`. On `/pricing` and `/pricing/` the nav's Pricing link carries `aria-current="page"`, and nowhere else. A `pricingCurrent(pathname)` helper sits beside `compareCurrent` in `src/lib/marketing/navigation.ts`, and `MkNav`'s `ariaCurrent(href)` uses it for `/pricing`, so both the desktop links and the phone sheet get it. The homepage teaser (`HomePricingTeaser`) keeps `id="pricing"`, so `/#pricing` still scrolls to it. It gains a "See full pricing" `MkButton` `link` variant to `/pricing` with `data-cta-location="pricing_more"`, centered directly under the card and above the Tanzania quick start line. `more` is added to `HomeCopy["pricing"]` and to both versions. No other homepage change.
- **AC-15**: At 390 by 844 pixels, `/pricing` has no horizontal scroll in either version. The h1 and the first plan card's price are visible without scrolling. Buttons are full width under 640 pixels. Every band stacks to one column under 768 pixels, except the included groups (AC-9).
- **AC-16**: On the deployed `/pricing`, Lighthouse mobile reports Largest Contentful Paint at most 2.5 seconds, Cumulative Layout Shift at most 0.1, Accessibility 100 and SEO 100. axe reports no violations in either version. With the keyboard alone, every button and FAQ row is reachable in reading order with a visible focus ring, and the contact modal opens and closes from each contact button. Results go in `verify.md`.
- **AC-17**: The copy lives in a new `src/constants/pricingPage.ts` as `pricingCopy.local` and `pricingCopy.abroad` (the same pattern as `homeCopy`), filled with spec 0019's `fill`. `AppConfig` gains `renewal: { graceDays: 7, removedAfterDays: 60 }` (the spec 0005 AC-14 and spec 0007 AC-1 numbers) and `abroadServices` (in `src/constants/pricing.ts`, beside `localServices`). `pricingValues` takes a `PricingSources` type that extends spec 0019's `HomeSources` with `renewal`, and a comment on `renewal` cites spec 0005 AC-14 and spec 0007 AC-1, the place to check if the numbers change. Node tests (`tests/marketing/pricing.test.ts`) fill every string of both versions with `pricingValues(AppConfig)` and fail on any placeholder with no value. They check that `hostedPlan.priceUSD.yearlySaving` equals monthly times 12 minus yearly. They also test a pure `pricingView(countryCode, signedIn)` in `src/lib/marketing/pricing.ts`, which the page renders from: the version (`TZ` → local; anything else, `undefined` included → abroad), each plan button's label, href, `data-cta-location` and `data-plan-name`, the setup offers, and the FAQ count.

## Decision

**Chosen option**: Option 1: a server rendered `/pricing` page of five `mk` bands, with the homepage teaser kept as the `/#pricing` landing spot and linking to it.

The full pricing lives at `/pricing`. It is rendered per request from the visitor's country and sign in state, uses the existing constants and copy helpers, and adds one fixed structured data block that names all three prices.

**Implementation skills**: `tailwindcss` (the `mk` classes and the breakpoints) · `clerk-astro-patterns` (`clerk/skills`, `.agents/skills/clerk-astro-patterns/`, the signed in swap through `isSignedIn`) · `web-perf` (the Lighthouse checks) · `workers-best-practices` (`cloudflare/skills`, `.agents/skills/workers-best-practices/`, why the page is never cached at the edge)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Design source**: the spec 0017 design system as built: `src/styles/marketing.css`, the components in `src/components/marketing/` and their README, and the `/design-system` preview page. The bands follow the homepage's rhythm (canvas, then tint, then canvas, then tint, then ink).

**Data model sketch**: no storage and no schema. Constants change:

| Constant | Change |
|---|---|
| `hostedPlan.included` (new, `src/constants/pricing.ts`) | `{ title: string; items: string[] }[]`, the *Included list* below |
| `abroadServices` (new, `src/constants/pricing.ts`, exported on `AppConfig`) | `ServiceOffer[]` with one item, the free data import (*Page copy*) |
| `AppConfig.renewal` (new, `src/constants/index.ts`) | `{ graceDays: 7, removedAfterDays: 60 }` |
| `navLinks`, footer Product column (`src/constants/navigation.ts`) | Pricing `href` becomes `/pricing` |
| `pricingCopy` (new, `src/constants/pricingPage.ts`) | `{ local, abroad }`, the *Page copy* below |
| `HomeCopy["pricing"]` (`src/constants/home.ts`) | gains `more: "See full pricing"` |

`ServiceOffer.features` may be empty; the card then shows no check list.

**State transitions**: none.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `/pricing` | GET | `cf-ipcountry` (through `locals.countryCode`), the Clerk session (through `locals.auth()`) | server rendered HTML, the Tanzania or abroad version, signed in or not | public | none of its own. If `auth()` throws, `isSignedIn` returns false and the signed out page renders (spec 0018) |

No API route, no form and no client fetch. The only scripts are the Layout's existing click and modal handler.

**Page copy** (word for word; braces are filled from constants and inserted exactly as stored: `{freeDays}`, `{payFromDay}`, `{readOnlyFromDay}`, `{removedOnDay}` from `AppConfig.trial`; `{graceDays}`, `{removedAfterDays}` from `AppConfig.renewal`; `{tzsYear}`, `{usdYear}`, `{usdMonth}`, `{usdSaving}` from `hostedPlan`; `{supportEmail}` from `AppConfig.emails.supportEmail`. A `*word*` is the one `MkHighlight` word.)

*Meta description* (both versions): "One plan with every feature: TZS {tzsYear} a year in Tanzania, or ${usdMonth} a month or ${usdYear} a year elsewhere. Start with a {freeDays} day free trial, no card needed."

*Plans band*, h1 (both): "One plan for your whole *shop*"
- Lead, Tanzania: "Try every feature free for {freeDays} days, with no card needed. Then pay once a year by mobile money."
- Lead, abroad: "Try every feature free for {freeDays} days, with no card needed. Then pay monthly, or yearly and save ${usdSaving}."
- Tanzania card: badge "The plan" · name "RareBooks" · price "TZS {tzsYear}" · period "a year" · note "Pay by mobile money. Nothing renews on its own." · button "Start free trial"
- Abroad Yearly card: badge "Best value" · name "Yearly" · price "${usdYear}" · period "a year" · note "Save ${usdSaving} on paying monthly. Renews each year until you cancel." · extra "Free data import when you take the yearly plan during your trial" · button "Start free trial"
- Abroad Monthly card: name "Monthly" · price "${usdMonth}" · period "a month" · note "Billed monthly after your free trial. Renews each month until you cancel." · button "Start free trial"
- Lines under the cards (both): "Every plan includes unlimited users and devices." Then, Tanzania: "Outside Tanzania: ${usdMonth} a month or ${usdYear} a year, by card or PayPal." Abroad: "In Tanzania: TZS {tzsYear} a year, by mobile money."

*Setup band*
- Tanzania: h2 "Want us to set it up for you?" · lead "Optional, and paid once. Your plan works the same either way." · cards from `localServices` as they stand today
- Abroad: h2 "Bring your records with you" · lead "Moving from other software? We do the import for you." · one card from `abroadServices[0]`: name "Free data import" · price "Free" · price note "With the yearly plan, taken during your trial" · blurb "We import your data from QuickBooks, Sage, Tally or your spreadsheets, so you start with your history in place." · features none · cta "Ask about data import"

*Everything included band*: h2 "Everything *included*" · lead "Every feature, for every user, on every plan." · the groups in *Included list*

*FAQ band*: h2 "Pricing questions"

| # | Version | Question | Answer |
|---|---|---|---|
| 1 | both | How does the free trial work? | Your first {freeDays} days are free, with every feature and no card needed. From day {payFromDay} you can pay to keep going. From day {readOnlyFromDay} your site is read only until you pay. If you haven't paid by day {removedOnDay}, we email you a link to download all your records, then remove the site a few days later. |
| 2 | Tanzania | How do I pay? | By mobile money through ClickPesa, one year at a time, from the Subscription page in RareBooks. We email you a receipt for every payment (not a TRA fiscal receipt). |
| 2 | abroad | How do I pay? | By card or PayPal, monthly or yearly, from the Subscription page in RareBooks. Payments go through PayPal, so we never see your card details. We email you a receipt for every payment. |
| 3 | both | Is there a charge per user or device? | No. Add your whole team and use RareBooks on every phone, tablet and computer you have, at no extra cost. |
| 4 | Tanzania | Can I cancel? | Yes. Nothing renews on its own: you pay for one year at a time and decide again each year. You can export your records as CSV files at any time, even when your site is read only. |
| 4 | abroad | Can I cancel? | Yes. Your plan renews until you cancel. Cancel your subscription in PayPal at any time, and you keep full access until the end of the period you paid for. You can export your records as CSV files at any time, even when your site is read only. |
| 5 | both | What happens if I stop paying? | When a paid period ends, you keep full access for {graceDays} more days. Then your site is read only, so you can still view and export everything. If you haven't renewed {removedAfterDays} days after that, we email you a link to download all your records, then remove the site a few days later. |

The FAQ contact button reads "Contact us". `{supportEmail}` is not used in the FAQ (there's no switch question until a switch is built). The closing band is `HomeCta` with the same version's `homeCopy[...].cta`.

*Homepage teaser* (`HomePricingTeaser`, both versions): a link under the card, "See full pricing".

**Included list** (`hostedPlan.included`; you approve this wording when you confirm the spec, and AC-11 checks each item on the demo shop):

| Group | Items |
|---|---|
| Accounting | Double entry accounting with your own chart of accounts · Journal entries and opening balances · Accounts in more than one currency |
| Selling and buying | Sales quotes, invoices and payments · Purchase invoices and supplier payments · Expenses, such as rent, wages and transport · Price lists, pricing rules and coupon codes · Loyalty programs |
| Point of sale | A point of sale for the counter · Barcode scanner support · A cashier role for your counter staff |
| Stock | Stock levels and stock movements · Batches and serial numbers · Purchase receipts and shipments |
| Reports | A dashboard with your balances and best sellers · Profit and loss, balance sheet and trial balance · General ledger · Print templates for your invoices |
| Your team and data | Unlimited users and devices · Roles and permissions · An import wizard for your existing records · Export to CSV at any time · Daily backups |
| Support | WhatsApp support · Step by step guides in our docs |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Render `/pricing` | Tanzania or abroad version | `isTanzania(Astro.locals.countryCode ?? "US")` from `src/constants/pricing.ts` |
| Render `/pricing` | signed in or not | `isSignedIn(Astro.locals)` from `src/lib/marketing/navigation.ts` (spec 0018) |
| Plan cards | TZS yearly price | `hostedPlan.priceTZS.yearly` ("300,000"), inserted as stored |
| Plan cards | USD monthly, yearly and saving | `hostedPlan.priceUSD.monthly`, `.yearly`, `.yearlySaving` |
| Plan cards | check list | `hostedPlan.features` (all 8) |
| Setup band | offers | `AppConfig.localServices` (Tanzania), `AppConfig.abroadServices` (abroad) |
| Included band | groups and items | `hostedPlan.included` |
| FAQ, lead, meta description | trial day numbers | `AppConfig.trial` (`freeDays`, `payFromDay`, `readOnlyFromDay`, `removedOnDay`, spec 0019 AC-4) |
| FAQ | grace days, days to removal | `AppConfig.renewal` (`graceDays` 7 from spec 0005 AC-14; `removedAfterDays` 60 from spec 0007 AC-1) |
| Other currency line | the price not shown in the cards | the same `hostedPlan` constants (AC-6) |
| Response headers | `Cache-Control: private, no-cache` | set in `src/pages/pricing.astro` (AC-1) |
| Plan cards, buttons, FAQ count | which cards, labels, hrefs and data attributes | `pricingView(countryCode, signedIn)` (AC-17) |
| Teaser link click | `cta_location` | `data-cta-location="pricing_more"` (AC-14) |
| Every placeholder | the filled value map | `pricingValues(AppConfig)` in `src/lib/marketing/pricing.ts`: `homeValues` (spec 0019) plus `graceDays` and `removedAfterDays` |
| JSON-LD | numeric prices | each price constant with `,` removed (`"300,000"` → `"300000"`), by `pricingJsonLd` |
| JSON-LD | page URL | `AppConfig.urls.rootUrl` plus `/pricing` |
| Plan button click | `cta_location`, `plan_name` | `data-cta-location="pricing_page"` and `data-plan-name` (AC-7), read by the existing Layout handler |
| Setup and FAQ contact click | `cta_location` | `data-cta-location` `pricing_page_setup` or `pricing_faq`, read by the Layout modal handler |
| Closing call to action | copy, location | `homeCopy.local.cta` or `homeCopy.abroad.cta`; `final_cta_section` from `HomeCta` |
| Nav Pricing link | `aria-current` | `pricingCurrent(Astro.url.pathname)`: `page` when the path is `/pricing`, otherwise nothing |

**Phone layout**: bands stack under 768 pixels. The abroad cards stack Yearly first. The included groups follow AC-9. Buttons go full width under 640 pixels. The plans band keeps its lead short enough that the h1 and the first price fit in the first screen at 390 by 844.

**Key invariants**:
- A price appears on the page, in the meta description and in the JSON-LD only through the `hostedPlan` constants, so changing a Books Plan price is a single edit in `src/constants/pricing.ts` (still kept in step with the control site's Books Plan rows by hand, as its comment says).
- Title, description, canonical, social card and JSON-LD are the same for every visitor. Only the visible body varies by country and sign in state.
- `/pricing` is never cached by any shared layer. It varies by country and session, so a cached copy would show the wrong currency or the wrong buttons. It always answers `Cache-Control: private, no-cache` (AC-1).
- Every price in the JSON-LD is also visible on the page in every version (AC-6), so the markup never describes content a person can't see.
- Abroad prices always say they renew until cancelled, and the Tanzania price always says nothing renews on its own.
- Every Start free trial is `href="/auth/sign-up"`, and no plan or currency is passed to it. You choose the plan when you pay, on the /books Subscription page (spec 0005 AC-10).
- The homepage keeps `id="pricing"` on its teaser for as long as old `/#pricing` links may exist.
- The page states no refund policy, until `/terms` (spec 0018) states one.

**Security model**: a public, read only page. The only identity read is the signed in flag from the Clerk session, on the server. No visitor input reaches the HTML: the JSON-LD is built from constants only and escapes `<`, and the FAQ answers are trusted HTML that we write (rendered by `MkFaq` with `set:html`). There's no payment, PII or form on the page; the contact modal is the existing one.

**Configuration required**: none. No new bindings, secrets or environment variables.

**Critical test scenarios**:
- Happy path: a visitor from Tanzania sees the TZS card, the USD line, the two setup offers and five FAQ rows. A visitor from Kenya (or with no country) sees Yearly and Monthly in USD, the TZS line, the free data import and five FAQ rows. `pricingView` is node tested for both. In `verify.md` the country is faked with a `cf-ipcountry: TZ` or `KE` header on `wrangler dev`, or with the middleware's local fallback. Verifies **AC-3**, **AC-4**, **AC-5**, **AC-8**, **AC-10**.
- Copy: every placeholder in `pricingCopy.local` and `pricingCopy.abroad` fills from `pricingValues(AppConfig)`, and a typo throws (node test). Verifies **AC-17**.
- Headers: `/pricing` answers `Cache-Control: private, no-cache`. Verifies **AC-1**.
- Saving: `yearlySaving` equals monthly times 12 minus yearly (node test). Verifies **AC-17**.
- Structured data: `pricingJsonLd(AppConfig)` returns three offers with prices `300000`, `39` and `399`, currencies TZS, USD and USD, and units `ANN`, `MON` and `ANN`, and the `<` escaping holds for a test string containing `</script>` (node test). Verifies **AC-13**.
- Signed in: with a Clerk session, every plan button and the closing call to action read "Go to your dashboard" and link to `/dashboard`, while the contact buttons don't change. If `auth()` throws, the signed out page renders. Verifies **AC-7**.
- Links: `navLinks` and the footer point Pricing at `/pricing`, `pricingCurrent` returns `page` only for `/pricing` (node test), and `/#pricing` on the homepage still scrolls to the teaser, which links to `/pricing`. Verifies **AC-14**.
- Phone and quality: 390 by 844 with no sideways scroll, then Lighthouse, axe and the keyboard pass on the deployed page. Verifies **AC-15**, **AC-16**.
- Claims: each FAQ and included claim is checked on the demo shop or the control site, and recorded. Verifies **AC-11**.

## Build plan

Tracer Bullet: the first slice puts a real `/pricing` in production, with real prices in both currencies, reachable from the nav. Later slices thicken the same page.

1. The thread: `AppConfig.renewal`, `pricingValues`, `pricingView`, `pricingCopy` with the plans band copy, `src/pages/pricing.astro` (with its `Cache-Control` header and `ContactUsModal`) with `PricingPlans` in both versions and the signed in swap, the two lines under the cards, the nav and footer `/pricing` links with `pricingCurrent` wired into `MkNav`, and the teaser's "See full pricing" link. Deployed. Satisfies **AC-1** (plans band), **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**, **AC-14**
2. Setup and included: `abroadServices`, `hostedPlan.included`, `PricingSetup` and `PricingIncluded`, with the rest of the copy for both bands. Satisfies **AC-2**, **AC-8**, **AC-9**
3. FAQ and close: `PricingFaq` with the contact button, and `HomeCta` at the foot, completing the five bands. Satisfies **AC-1**, **AC-10**
4. Search: the title, description, canonical and social card, the `Layout` `jsonLd` prop and `pricingJsonLd`. Satisfies **AC-12**, **AC-13**
5. Unit tests (`tests/marketing/pricing.test.ts`, and `navigation.test.ts` updated): copy fill for both versions, `pricingView`, the yearly saving, the JSON-LD prices and escaping, `pricingCurrent`, and the new Pricing hrefs. Satisfies **AC-13**, **AC-14**, **AC-17**
6. Checks, recorded in `verify.md`: every claim on the demo shop or the control site (receipts, one card checkout, renewal and cancel, the removal email), your confirmation of the data import offer, the `Cache-Control` header, the 390 by 844 pass, the Schema.org validator, then Lighthouse, axe and the keyboard on the deployed page. Satisfies **AC-11**, **AC-13**, **AC-15**, **AC-16**

## Consequences

**Positive**:
- Pricing gets its own URL to share and rank, with the price shown in search results through the JSON-LD, while the homepage stays short.
- Every price on the site still comes from one constants file, now including the structured data.
- Plan clicks keep the old `pricing_page` and plan names, so the before and after comparison in feature 21 has history to compare against.

**Negative / tradeoffs**:
- Prices now appear in four places (the cards, the teaser, the meta description and the JSON-LD). All four read the same constants, but `src/constants/pricing.ts` and the control site's Books Plan rows are still kept in step by hand.
- The page can't be cached at the edge, so every visit costs a Worker render (the same as the homepage today).
- The included list is new marketing copy that has to stay true as /books changes. A removed feature has to be removed here too.
- A visitor in Tanzania on a VPN, or a Tanzanian business abroad, sees USD with no way to switch.
- Crawlers outside Tanzania see only the USD body, so TZS appears to search engines only through the JSON-LD and the meta description.

**Neutral**:
- `Layout` gains a reusable `jsonLd` prop that feature 20 (compare and alternatives) can use for its structured data.
- `/#pricing` now lands on a teaser, not on full pricing. It's one click away.

## Follow-up

- [ ] When you confirm this spec, approve or change the *Included list* and the FAQ answers (AC-11 then checks them on the demo shop).
- [ ] Feature 21 (conversion tracking): the new locations are `pricing_page` (plan buttons, with `plan_name`), `pricing_page_setup`, `pricing_faq` and `pricing_more` (the teaser link). `final_cta_section` now fires on two pages, so the event needs the page path to tell them apart.
- [ ] The site has no sitemap. Adding one (with `/pricing`, `/compare/*` and `/alternatives/*`) is its own small piece of work.
- [ ] The free data import is delivered by hand and nothing tracks its condition (yearly taken during the trial). If it grows, give it a place on the control site.
- [ ] If you later build a monthly to yearly switch (spec 0008 refuses a second checkout today), add a FAQ row for it. If you state a refund policy in `/terms`, add it to the FAQ in the same change.
