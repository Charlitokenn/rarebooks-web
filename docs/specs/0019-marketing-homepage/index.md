# 0019. Marketing homepage

**Date**: 2026-11-25
**Status**: Proposed

Scope: feature 18 (Slice 10, Marketing site redesign) · Beta. Code lives in the `rarebooks-site` repo, plus one dev only seed command in this repo. Builds on spec 0017 (the `mk` design system) and spec 0018 (MkNav and MkFooter).

## Summary

The homepage is rebuilt from the spec 0017 components in seven bands: hero, trust row, four feature rows, the free trial promise, a pricing teaser, an FAQ and a closing call to action. Every picture is a real /books screenshot, taken by a script from a fictional demo shop on a local bench site, once in TZS for Tanzania visitors and once in USD for everyone else. The copy is written below word for word, keeps a Tanzania and an abroad version, and says the trial the way spec 0005 runs it: free for 21 days, then until day 30 to pay. The Arcade demo moves into a dialog that loads only when asked for, so the page stays fast on a phone.

## Requirements

**User stories**:
- As a shop owner in Tanzania, I want to see my kind of shop, my currency and my way of paying, so that I trust RareBooks fits me.
- As a visitor abroad, I want to see what the product does and what it costs in dollars, so that I can decide to try it.
- As a visitor on a phone, I want the page to load fast and read well, so that I don't leave before I see it.
- As any visitor, I want an honest picture of the trial, so that day 26 doesn't surprise me.
- As the operator, I want trial clicks counted by section and screenshots I can take again after a UI change.

**Acceptance criteria**:
- **AC-1**: `src/pages/index.astro` renders, inside `<main id="main">` between MkNav and MkFooter (spec 0018), exactly these bands in this order, each an `MkSection` whose `labelledby` names its heading (ids `home-hero-title`, `home-trust-title`, `home-features-title`, `home-trial-title`, `home-pricing-title`, `home-faq-title`, `home-cta-title`): hero (`canvas`, h1), trust row (`tint`, its h2 "Trusted by growing businesses" visually hidden with `sr-only`, the overline showing the same words), features (`canvas`, `id="features"`), trial promise (`pink`, `id="trial"`), pricing teaser (`canvas`, `id="pricing"`), FAQ (`tint`, `id="faq"`), closing call to action (`ink`, `id="cta"`). The page has one h1, and every other band heading is an h2. The `features` and `pricing` ids stay, so the spec 0018 nav links land (`/#features`, `/#pricing`) without being hidden under the sticky header.
- **AC-2**: The sections live in `src/components/marketing/home/` (`HomeHero`, `HomeTrust`, `HomeFeatures`, `HomeTrial`, `HomePricingTeaser`, `HomeFaq`, `HomeCta`, `HomeDemoDialog`), built only from `mk` components and `mk` tokens with allowed pairs from spec 0017. `Hero.astro`, `Comparison.astro`, `HowItWorks.astro`, `Stats.astro`, `Guarantee.astro`, `Pricing.astro` and `CallToAction.astro` in `src/components/` are deleted, and no file imports them.
- **AC-3**: Every visible string on the homepage is the one in *Page copy* below, word for word, with the values in braces filled from the named constants. The Tanzania version shows when `isTanzania(Astro.locals.countryCode ?? "US")` is true, the abroad version otherwise (so an unknown country gets the abroad version, as today).
- **AC-4**: `AppConfig.trial` becomes `{ freeDays: 21, payFromDay: 22, readOnlyFromDay: 26, removedOnDay: 30 }` (the spec 0005 and 0007 numbers). `localDuration` and `abroadDuration` are gone, and every file that read them (today `enquiry-email.tsx`) reads `freeDays` instead. Nothing inside the homepage's `<main>` says "30 days free" or "30 day trial" (the contact modal sits outside `<main>` and isn't checked); the trial promise and FAQ read the four numbers from `AppConfig.trial`.
- **AC-5**: The hero shows the h1 with one `MkHighlight` word, the lead, a primary `MkButton size="lg"` and a secondary `Watch the demo` button (also `size="lg"`), the price line, and the dashboard screenshot in `MkScreenshotFrame` with `priority` (eager, `fetchpriority="high"`). The page passes `preloadSerif` to `Layout`. The hero is the only image loaded eagerly; every other screenshot is lazy.
- **AC-6**: `Watch the demo` is a `<button type="button" data-open-modal="mk-demo">` that opens `<dialog id="mk-demo" aria-label="RareBooks interactive demo">` through the existing Layout handler. No request to `demo.arcade.software` happens until it opens: the iframe (`title="RareBooks interactive demo"`, `allow="clipboard-write"`, `allowfullscreen`, inside a box with today's ratio, `padding-bottom: calc(61.24% + 41px)`) sits in a `<template>`. One inline script (`is:inline`, under 1 KB) owns everything the Layout handler doesn't: it removes the button's `hidden`, clones the iframe in when the button is clicked, closes the dialog on a click whose target is the dialog itself (the backdrop, as the dialog has `p-0` and an inner wrapper), and removes the iframe on the dialog's `close` event. The Layout handler only calls `showModal()` for `mk-demo`; it pushes no event for it, since the button has no `data-cta-location`. The dialog closes on Escape, on its Close button (`<form method="dialog">`, accessible name "Close demo") and on a backdrop tap, and focus returns to `Watch the demo`. Below 768 pixels it fills the screen; from 768 pixels it is at most 64rem wide. The dialog always holds a link "Open the demo in a new tab" to `AppConfig.urls.demoUrl` (`target="_blank"`, `rel="noopener noreferrer"`), for a visitor whose browser blocks the embed. With JavaScript off the button can't open the dialog, so it carries the `hidden` attribute, which the inline script removes, and a `<noscript>` link "Watch the demo" to the same URL shows in its place.
- **AC-7**: The trust row shows the overline "Trusted by growing businesses" and the names in `AppConfig.featuredClients` as text. It shows one `MkCard variant="quote"` only when `AppConfig.testimonial.quote`, `.name` and `.business` are all non empty; while any is empty, no quote markup renders (no empty card, no stray `<figure>`).
- **AC-8**: The features band holds four `MkFeatureRow`s in this order: dashboard balances, point of sale, stock, profit and loss. Rows 2 and 4 are `reverse`. Each row's screenshot is a real /books capture named in *Screenshots* below, with the `-tzs` set for the Tanzania version and the `-usd` set otherwise, its alt text from *Page copy*, and `sizes="(min-width: 1200px) 600px, (min-width: 768px) 50vw, 100vw"`. A name missing from `src/data/screenshots.json` fails the build (spec 0017).
- **AC-9**: The trial promise is an `<ol>` of three `MkCard` steps (Start free, Get set up, Decide by day {removedOnDay}), then a primary `Start free trial`. Its numbers come from `AppConfig.trial` and its prices from `AppConfig.hostedPlan`.
- **AC-10**: The pricing teaser shows the plan price in the visitor's currency from `AppConfig.hostedPlan` (TZS yearly; or USD yearly with the monthly price and the yearly saving), the first four items of `hostedPlan.features` as an `MkCheckList`, and a primary `Start free trial`. In the Tanzania version only, it adds the quick start line with a secondary `MkButton` "Talk to us" (`data-open-modal="contact-us-modal"`, `data-cta-location="pricing_setup"`) that opens the contact modal.
- **AC-11**: The FAQ is one `MkFaq` with the five questions in *Page copy*, in order. The last answer ends with a "Contact us" button (`type="button"`, `data-open-modal="contact-us-modal"`, `data-cta-location="faq"`) styled as the `MkButton` `link` variant, which opens the contact modal. `ContactUsModal` stays on the page once, as today.
- **AC-12**: Every Start free trial on the page is `<a href="/auth/sign-up">` with `data-cta-location` `hero`, `trial`, `pricing` or `final_cta_section` (the hero and closing names are unchanged from today, so the event history carries on), so the Layout handler pushes `trial_interest`. For a signed in visitor (`isSignedIn(Astro.locals)` from spec 0018), each of these instead reads "Go to your dashboard" and links to `/dashboard`, decided on the server. Each swapped link keeps its `data-cta-location` but pushes no `trial_interest` (the handler only counts `/auth/sign-up` links), which is intended. `Watch the demo`, `Talk to us` and `Contact us` don't change for signed in visitors. If `auth()` throws, the signed out set renders and the page answers 200.
- **AC-13**: `AppConfig.description` becomes "Online accounting, stock and point of sale for small businesses, hosted for you." The homepage passes `Layout` the title "RareBooks: accounting, stock and point of sale for small businesses", that description, `canonicalPath="/"` and `ogImage="/og/home.jpg"`. `Layout` gains an optional `ogImage` prop that, when set, writes `og:image` (absolute URL on `AppConfig.urls.rootUrl`), `og:image:width` 1200, `og:image:height` 630, `og:image:alt` (from a matching optional `ogImageAlt` prop; the homepage passes the hero screenshot alt) and `twitter:image`. `public/og/home.jpg` is a 1200 by 630 JPEG under 150 KB, cut from `home-dashboard-usd` by the screenshot script.
- **AC-14**: Every feature claim in *Page copy* (balances, best sellers, point of sale with barcode scanner, stock levels, expenses, profit and loss, daily backups, CSV export, and the abroad offer of a free data import from QuickBooks, Sage, Tally or spreadsheets with the yearly plan, which you confirm is a real offer) is shown working or confirmed on the seeded demo site, as recorded in `verify.md`, before the build is merged. A claim that can't be shown is reworded or removed in the spec first.
- **AC-15**: In this repo, `bench --site <site> execute frappe_books.demo.shop.seed --kwargs "{'currency': 'TZS'}"` (or `'USD'`) fills a fresh site with the fictional Kilima Hardware shop (*Demo shop* below) through the normal controllers, so stock, ledgers, the dashboard cards and reports show real numbers. It refuses, with `frappe.throw` and a translated message, unless `frappe.conf.developer_mode` is on, `books_control_url` is not set (so the site is not on the trial clock: `clock.is_managed()` is false, it never locks and shows no trial banner) and the site has no submitted sales invoice, so it can never touch a customer site. Running it twice on the same site is refused by the same rule.
- **AC-16**: In `rarebooks-site`, `npm run screenshots:home` (`scripts/home-screenshots.mjs`, Playwright) signs in to the two seeded sites, captures every shot in *Screenshots* at a 1280 by 800 viewport with `deviceScaleFactor: 2`, with `embed.tawk.to` blocked, waits for each shot's named element (*Screenshots* table), fails if a `SubscriptionBanner` is on the page, writes every PNG to a temporary folder first, and only when all ten succeed moves them into `src/assets/screenshots/source/`, writes `public/og/home.jpg`, then runs `npm run screenshots`. A shot whose page fails to load or whose element doesn't appear within 15 seconds stops the script with the route named, and nothing is moved.
- **AC-17**: On the deployed homepage, Lighthouse mobile reports Largest Contentful Paint at most 2.5 seconds, Cumulative Layout Shift at most 0.1, Accessibility 100 and SEO 100, and none is worse than the spec 0018 baseline in its `verify.md`. The hero image's AVIF at 960 wide is at most 80 KB and the page's total image transfer before scrolling is at most 150 KB, measured in Lighthouse's default mobile emulation (390 pixels wide at its default device pixel ratio). If the hero misses 80 KB, `scripts/screenshots.mjs` takes an optional per name AVIF quality (45 for `home-dashboard-*`) instead of the default 55. If spec 0018's `verify.md` has no mobile baseline yet, recording one is the first step of the build. axe reports no violations at 1280 and 390 pixels, in both country versions, and with the demo dialog open.

## Decision

**Chosen option**: Option 1: a server rendered homepage of seven `mk` bands, with screenshots scripted from a seeded local demo shop in two currencies and the demo behind a dialog.

The page is plain Astro on the spec 0017 components with copy fixed in this spec; images come from a repeatable seed and capture pipeline, not hand taken files.

**Implementation skills**: `tailwindcss` (the `mk` classes and breakpoints) · `clerk-astro-patterns` (`clerk/skills`, `.agents/skills/clerk-astro-patterns/`, the signed in swap through `isSignedIn`) · `playwright-best-practices` (the capture script and the dialog test) · `web-perf` (the LCP and image budget checks) · `frappe-app-dev` (the seed command)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Design source**: the spec 0017 design system as built: `src/styles/marketing.css`, the components in `src/components/marketing/` and their README, and the `/design-system` preview page, with the Wave patterns spec 0017 records. No new tokens and no new base components; anything a section needs that the base components don't offer is a class inside that section's component.

**Data model sketch**: no storage and no schema. Constants change:

| Constant | File | Shape |
|---|---|---|
| `AppConfig.trial` | `src/constants/index.ts` | `{ freeDays: 21, payFromDay: 22, readOnlyFromDay: 26, removedOnDay: 30 }`, replacing `localDuration` and `abroadDuration` |
| `AppConfig.description` | `src/constants/index.ts` | the AC-13 string |
| `AppConfig.testimonial` | `src/constants/index.ts` | `{ quote: string; name: string; business: string }`, all `""` until you supply them |
| `AppConfig.urls.demoUrl` | `src/constants/index.ts` | the current Arcade embed URL (`https://demo.arcade.software/FeRaybGnq8w8icVFYOSu?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true`), moved out of `Hero.astro` |
| `homeCopy` | `src/constants/home.ts` | `{ local: HomeCopy; abroad: HomeCopy }`, every string in *Page copy*, typed, with `{name}` placeholders filled by a small `fill(template, values)` helper in `src/lib/marketing/home.ts` |

**Page copy** (word for word; braces are filled from constants and inserted exactly as stored, with no reformatting: `{freeDays}`, `{payFromDay}`, `{readOnlyFromDay}`, `{removedOnDay}` from `AppConfig.trial`; `{tzsYear}` from `hostedPlan.priceTZS.yearly` ("300,000"); `{usdYear}`, `{usdMonth}`, `{usdSaving}` from `hostedPlan.priceUSD.yearly`, `.monthly` and `.yearlySaving`; `{quickStart}` from `localServices[1].price` ("TZS 75,000", which already holds the currency); `{supportEmail}` from `AppConfig.emails.supportEmail`):

*Hero*
- Overline, both: "For shops and small businesses"
- h1, Tanzania: "Your stock and sales, always *current*" (italic word in `MkHighlight`)
- h1, abroad: "Clear books, confident *stock*"
- Lead, Tanzania: "RareBooks turns your notebooks into live records: what's on the shelf, what's selling and what you're earning, on your phone or computer."
- Lead, abroad: "RareBooks keeps your accounting, invoicing, point of sale and stock in one place, hosted for you. Know your numbers and stay ready for tax."
- Buttons: "Start free trial", "Watch the demo"
- Price line, Tanzania: "Free for {freeDays} days, then TZS {tzsYear} a year. We can set up your shop for you."
- Price line, abroad: "Free for {freeDays} days, then ${usdYear} a year or ${usdMonth} a month."
- Screenshot alt: "The RareBooks dashboard showing cash and bank balances and the best selling items"

*Trust row*
- Overline: "Trusted by growing businesses"; then the client names; then the quote card when AC-7 allows.

*Features* (band h2 "Everything your shop runs on", overline "Features")
1. Overline "Dashboard", h3 "Know where you stand every morning", text: "See your cash, mobile money and bank balances, and your best selling items, the moment you open RareBooks." (abroad: "See your cash and bank balances, and your best selling items, the moment you open RareBooks.") Alt: "Account balances and a best sellers chart on the RareBooks dashboard"
2. Overline "Point of sale", h3 "Sell fast at the counter", text: "Your cashier rings up sales on the point of sale screen, with a barcode scanner if you have one. Every sale takes the items out of stock on its own." Alt: "The RareBooks point of sale screen with items in a cart"
3. Overline "Stock", h3 "See what's on the shelf without counting", text: "Check how much of each item you have at any moment, and plan your next order from real numbers, not guesses." Alt: "A stock balance report listing items and quantities on hand"
4. Overline "Reports", h3 "Profit you can trust", text: "Record expenses as they happen, and your profit and loss is ready whenever you ask. Hand your accountant clean reports at tax time." Alt: "A profit and loss report in RareBooks"

*Trial promise* (h2 "Try it free for {freeDays} days", lead "Run your real business on it before you pay anything.")
1. "Start free": "Sign up and your own site at yourname.rarebooks.cc is ready in minutes. Every feature, nothing to pay up front."
2. "Get set up", Tanzania: "Do it yourself, or let us set up your shop: your items, opening stock and the customers who owe you." Abroad: "Do it yourself, or take the yearly plan during your trial and we import your data from QuickBooks, Sage, Tally or your spreadsheets."
3. "Decide by day {removedOnDay}", Tanzania: "Pay TZS {tzsYear} for the year by mobile money and keep going. If not, we send you all your records as CSV files." Abroad: "Keep going for ${usdYear} a year or ${usdMonth} a month. If not, we send you all your records as CSV files."
- Button: "Start free trial"

*Pricing teaser* (h2 "One plan. Everything included.")
- Tanzania price: "TZS {tzsYear}" with "a year"; abroad: "${usdYear}" with "a year", then "or ${usdMonth} a month. Save ${usdSaving} with yearly."
- Check list: `hostedPlan.features.slice(0, 4)`
- Button: "Start free trial"
- Tanzania only: "Want us to set up your shop? Quick start is {quickStart}, and it comes back as 3 free months." and the "Talk to us" button.

*FAQ* (h2 "Questions people ask")
1. "Do I need to install anything?" "No. Your RareBooks site lives online at yourname.rarebooks.cc. Open it in the browser on your phone, tablet or computer."
2. "What happens when the trial ends?" "Your first {freeDays} days are free. From day {payFromDay} you can pay to keep going ({payMethod}). From day {readOnlyFromDay} your site is read only until you pay, and if you haven't paid by day {removedOnDay}, we email you all your records as CSV files and remove the site." (`{payMethod}`: Tanzania "by mobile money", abroad "by card or PayPal")
3. "Can I bring my existing records?" Tanzania: "Yes. Our quick start ({quickStart}) enters your items, opening stock and the customers who owe you. We can also type in your old notebooks; ask us for a price." Abroad: "Yes. Take the yearly plan during your trial and we import your data from QuickBooks, Sage, Tally or your spreadsheets, free."
4. "Is my data safe, and is it mine?" "Your site is backed up every day. You can export your records as CSV files at any time, and they stay yours whatever you decide."
5. "How do I get help?" "Email us at {supportEmail} or send a message, and read the step by step guides in our docs." then the "Contact us" button (AC-11). "docs" links to `AppConfig.urls.docsHomePath`.

*Closing call to action* (ink band)
- h2: "Stop dreading your books. Start *trusting* them."
- Lead: "Join businesses that left notebooks and spreadsheets behind for good."
- Button (`on-dark`): "Start free trial"

Signed in visitors see "Go to your dashboard" in place of every "Start free trial" in the body (AC-12).

**Screenshots** (all at 1280 by 800, `deviceScaleFactor: 2`, so sources are 2560 wide and `npm run screenshots` writes 640, 960, 1280 and 1920; each name exists as `-tzs` and `-usd`):

| Name | Route on the demo site | What is captured | Ready when |
|---|---|---|---|
| `home-dashboard` | `/books/` | the full viewport (hero) | the account balances card and the best sellers chart are both visible with data |
| `home-balances` | `/books/` | one element shot of the smallest box holding the account balances card and the best sellers chart (add a `data-shot="home-balances"` attribute to that box in the Books frontend, so the script never depends on layout classes) | as above |
| `home-pos` | `/books/pos` | the point of sale with three items in the cart: the first three seeded items, each found with the item search and clicked | the cart shows three lines and a total |
| `home-stock` | `/books/report/StockBalance` | the stock balance report | the report table has at least one row |
| `home-profit` | `/books/report/ProfitAndLoss` | profit and loss from 30 days ago to today, set by filling the report's from and to date filters | the report table shows an income row |

**Demo shop** (fictional; no real customer, person or business): Kilima Hardware, Dar es Salaam. Two local sites, `shots-tzs.localhost` (company currency TZS, country Tanzania) and `shots-usd.localhost` (USD, country United States). You create each with `bench new-site --admin-password <yours>`, install the app, and finish the Books setup wizard with the company name Kilima Hardware, that currency and the standard chart of accounts; the seed then runs on that set up company. The seed adds opening stock with one stock entry dated 31 days ago, creates one POS profile for the cashier, and gives the three role users the fixed password `demo-shop-only` (local sites only). The capture script signs in as Administrator with `BOOKS_SHOTS_PASSWORD`. The seed creates about 20 hardware items with prices in the site's currency and opening stock, 6 customers and 3 suppliers with made up names, the Books User, Books Manager and Books Cashier users, about 60 sales invoices and POS sales spread over the last 30 days (dates relative to the day it runs), 4 purchases, and 8 expenses (rent, electricity, transport, wages), so best sellers, balances and profit and loss have shape. It doesn't touch the subscription: the site is unmanaged (no `books_control_url`), so the trial clock never runs there.

**API surface**: no new endpoints. Routes and commands:

| Route or command | Method | Inputs | Output | Auth | Key errors |
|---|---|---|---|---|---|
| `/` | GET | `cf-ipcountry` (through `locals.countryCode`), the Clerk session if any | the homepage | public | `auth()` throwing renders signed out, 200 (AC-12) |
| `/og/home.jpg` | GET | none | the social image (static file) | public | none |
| `bench execute frappe_books.demo.shop.seed` | CLI | `currency`: `"TZS"` or `"USD"` (req) | a seeded site | bench shell on a dev machine | throws unless developer mode, no `books_control_url` and no submitted sales invoice; throws on any other currency (AC-15) |
| `npm run screenshots:home` | CLI | `BOOKS_SHOTS_TZS_URL`, `BOOKS_SHOTS_USD_URL`, `BOOKS_SHOTS_PASSWORD` | PNG sources, the og image, the resized set and manifest | Administrator on the local sites | stops on a failed route, naming it (AC-16) |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Render `/` | Tanzania or abroad version | `isTanzania(Astro.locals.countryCode ?? "US")` from `src/constants/pricing.ts` |
| Render `/` | every string | `homeCopy` in `src/constants/home.ts` (this spec's *Page copy*) |
| Render `/` | trial day numbers | `AppConfig.trial` (spec 0005 and 0007 numbers) |
| Render `/` | prices and saving | `AppConfig.hostedPlan.priceTZS` and `.priceUSD` |
| Render `/` | quick start price | `AppConfig.localServices[1].price` |
| Render `/` | included points | `AppConfig.hostedPlan.features.slice(0, 4)` |
| Render `/` | client names | `AppConfig.featuredClients` |
| Render `/` | quote, name, business | `AppConfig.testimonial`, supplied by you |
| Render `/` | support email, docs link | `AppConfig.emails.supportEmail`, `AppConfig.urls.docsHomePath` |
| Render `/` | signed in or not | `isSignedIn(Astro.locals)` (spec 0018) |
| Render `/` | screenshot files, sizes, widths | `src/data/screenshots.json`, written by `npm run screenshots` |
| Render `/` | which screenshot set | `-tzs` for the Tanzania version, `-usd` otherwise |
| Render `/` | og image absolute URL | `new URL("/og/home.jpg", AppConfig.urls.rootUrl)` in `Layout` |
| Open demo | iframe URL | `AppConfig.urls.demoUrl` |
| Trial click | `cta_location` | the link's `data-cta-location` (AC-12) |
| Contact click | `cta_location` | `data-cta-location` `pricing_setup` or `faq`, read by the Layout modal handler |
| Seed | shop data | the fixed lists in `frappe_books/demo/shop.py`, dates relative to `frappe.utils.today()` |
| Capture | site URLs and password | `BOOKS_SHOTS_TZS_URL`, `BOOKS_SHOTS_USD_URL`, `BOOKS_SHOTS_PASSWORD` in your shell, never committed |

**Phone layout**: bands stack to one column under 768 pixels. Feature rows show text first, then the frame (MkFeatureRow's own rule). The hero puts the buttons above the screenshot, so the h1 and the buttons are visible without scrolling at 390 by 844. The trial steps and the pricing teaser stack; buttons go full width under 640 pixels.

**Key invariants**:
- The homepage varies by visitor (country and sign in), so no shared or edge cache, as spec 0018 already requires.
- One `MkHighlight` per headline at most; one h1; the hero is the only eager image.
- Screenshots only ever come from the seeded demo sites, never from a customer site.
- The seed command never runs on a site that has a submitted sales invoice, a `books_control_url`, or no developer mode.
- Copy changes go through this spec's *Page copy* (or a later spec), so the words and the claims checked in AC-14 stay in step.
- The page adds one inline script (the demo dialog). The `src/components/marketing/README.md` rule on client JavaScript names it next to the MkNav exception.

**Security model**: public, read only page. The only identity read is the signed in flag from the Clerk session on the server. The Arcade iframe loads only on request, from the one fixed URL in `AppConfig`, never from a query string. The seed command runs only from a bench shell and refuses anything but a fresh developer mode site. The capture script reads its password from the environment and logs no secrets.

**Configuration required**:
- `BOOKS_SHOTS_TZS_URL`, `BOOKS_SHOTS_USD_URL`: the two local seeded sites (default `http://shots-tzs.localhost:8000` and `http://shots-usd.localhost:8000`), only for `npm run screenshots:home`
- `BOOKS_SHOTS_PASSWORD`: the Administrator password of those local sites, only in your shell

**Critical test scenarios**:
- Happy path: with `countryCode` `TZ`, the rendered homepage has the seven bands in order, the Tanzania copy, `-tzs` images and the Talk to us line; with `US` and with no country, the abroad copy and `-usd` images, verifies **AC-1**, **AC-3**, **AC-8**, **AC-10**
- Trial numbers: no "30 day" or "30 days free" anywhere in the rendered page, and the FAQ shows 21, 22, 26 and 30, verifies **AC-4**, **AC-9**
- Quote gate: with `AppConfig.testimonial` empty, no quote card renders; with all three filled, one renders, verifies **AC-7**
- Signed in: with a mocked session, every body trial link reads "Go to your dashboard" to `/dashboard`; with `auth()` throwing, the page answers 200 signed out, verifies **AC-12**
- Demo: in Playwright, no request to `demo.arcade.software` before the click; after it, the iframe loads; Escape closes it, removes the iframe and returns focus, verifies **AC-6**
- Contact: Talk to us and the FAQ Contact us both open `contact-us-modal`, verifies **AC-10**, **AC-11**
- Seed guard: a Python test that the seed throws without developer mode, with `books_control_url` set, and on a site with a submitted sales invoice, verifies **AC-15**
- Speed and access: deployed Lighthouse mobile and axe at 1280 and 390 pixels meet the numbers, verifies **AC-17**

## Build plan

Tracer Bullet: the first slice is one real screenshot travelling the whole way, from the seed to a deployed hero, before the other bands are filled in.

1. Thread: if spec 0018's `verify.md` has no mobile Lighthouse baseline, record it first; in this repo, `frappe_books/demo/shop.py` with the guard and the TZS shop, and its guard test; on a local `shots-tzs.localhost`, seed it; in `rarebooks-site`, `scripts/home-screenshots.mjs` with the `home-dashboard` shot only and `npm run screenshots:home`; then `AppConfig.trial`, `homeCopy` with the hero strings, `HomeHero` with the priority screenshot, and `index.astro` rendering MkNav, the new hero and the old remaining sections; deploy and record LCP for the new hero, satisfies **AC-3**, **AC-4**, **AC-5**, **AC-15**, **AC-16**
2. Both currencies and every shot: the USD site and seed, the `data-shot` attribute in the Books dashboard, the other four shots, the og image cut, `Layout`'s `ogImage` prop, the new description and title, satisfies **AC-8**, **AC-13**, **AC-15**, **AC-16**
3. Features and trust: `HomeFeatures` with the four rows, `HomeTrust` with `AppConfig.testimonial` and the quote gate, and a node render test for both versions, satisfies **AC-1**, **AC-7**, **AC-8**
4. Trial, pricing and FAQ: `HomeTrial`, `HomePricingTeaser` (with the Talk to us line), `HomeFaq` (with the Contact us button), the signed in swap on every body CTA, and their render tests, satisfies **AC-9**, **AC-10**, **AC-11**, **AC-12**
5. Demo and close: `HomeDemoDialog` with its inline script and no JS fallback, `HomeCta`, `AppConfig.urls.demoUrl`, the README script rule; delete the seven old components; a Playwright test for the dialog and the two contact buttons, satisfies **AC-1**, **AC-2**, **AC-6**, **AC-11**
6. Checks: walk every claim on the seeded sites and record it in `verify.md`; deployed Lighthouse mobile, axe in both versions and with the dialog open, the image budget, satisfies **AC-14**, **AC-17**

## Consequences

**Positive**:
- The homepage finally shows the product: five real screens, in the visitor's own currency.
- Screenshots can be taken again with two commands after any /books change, so they don't go stale silently.
- The trial is told the way the product runs it, matching the terms and privacy drafts.
- Dropping the inline Arcade iframe takes its weight off every page view.

**Negative / tradeoffs**:
- Two seeded local sites and a Playwright run are a real chore before every screenshot refresh, and the seed must follow any Books doctype change.
- Ten screenshot sources plus their resized files add a few megabytes to the repo.
- A second inline script joins MkNav's, widening spec 0017's "no client JavaScript" exception.
- The copy lives in a constants file, so wording changes need a code change and a deploy, and the spec's copy and the file can drift unless changes go through the spec.
- Fewer than three real customer names makes the trust row thin until you add a quote or more clients.

**Neutral**:
- `AppConfig.trial` changes shape; other "30 day" strings outside the homepage are listed in Follow-up, not changed here.
- The old purple homepage components are gone; the compare and alternatives pages keep their own look until feature 20.
- Feature 19 may move full pricing to `/pricing`; this teaser keeps `id="pricing"` and should then link to it.

## Follow-up

- [ ] Supply `AppConfig.testimonial` (a real quote, the person's name and their business, with their permission). The quote shows once all three are set.
- [ ] Logos for `AppConfig.featuredClients`, if those businesses agree; then the trust row can show them instead of text.
- [ ] Other "30 day trial" wording outside the homepage: `src/components/templates/site-ready-email.tsx`, `src/components/onboarding/StartForm.tsx` and `src/content/docs/getting-started/create-your-site.mdx` say the trial lasts 30 days. Reword them to the spec 0005 numbers next time each is touched.
- [ ] Feature 19 (pricing page): if pricing moves to `/pricing`, add a "See full pricing" link to the teaser and update `navLinks` in the same change (spec 0018 invariant).
- [ ] Feature 21 (conversion tracking) gains three new `cta_location` values: `trial`, `pricing` and `faq`, plus `pricing_setup` on the contact modal.
- [ ] `tailwindcss`, `web-perf`, `playwright-best-practices` and `frappe-app-dev` are installed skills not listed in `rarebooks-site/AGENTS.md` `## Agent skills`; the first three are project wide for that repo and belong in its root `AGENTS.md`. `frappe-app-dev` belongs in this repo's root `AGENTS.md`.
- [ ] The seed lives in `frappe_books/demo/`; note it in `frappe_books/AGENTS.md` (for `/sync`) so nobody runs it on a real site.
