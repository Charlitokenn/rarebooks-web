# Verify: Marketing homepage · spec 0019 · updated 2026-11-25
_Steps derived from spec 0019 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. This first set covers the thread (build plan step 1); later steps append theirs._

## Built so far

Build plan step 1 (the thread), apart from the deploy: the demo shop seed, both seeded sites, the capture script with the `home-dashboard` shot in both currencies, the new trial numbers, the hero copy and `HomeHero`. The USD site and the og image cut came early, as the abroad hero needs `home-dashboard-usd`.

Still owed from step 1: the spec 0018 mobile Lighthouse baseline and the deployed LCP of the new hero. This build container can't reach rarebooks.cc, so take both from a machine that can.

## Commands
- [ ] `bench --site <test site> run-tests --app frappe_books --module frappe_books.tests.test_demo_shop` → 4 pass: refused without developer mode, with `books_control_url`, with a submitted sales invoice, and for EUR → AC-15
- [ ] On a fresh `shots-tzs.localhost` (Tanzania, TZS, standard chart, setup wizard finished): `bench --site shots-tzs.localhost execute frappe_books.demo.shop.seed --kwargs "{'currency': 'TZS'}"` → "Kilima Hardware is seeded in TZS." → AC-15
- [ ] Run the same command again → refused: "this one has submitted sales invoices" → AC-15
- [ ] Seed with `'USD'` on the TZS site → refused: the company keeps its books in TZS → AC-15
- [ ] Same on `shots-usd.localhost` (United States, USD) with `'USD'` → seeded; no Mobile Money account there → AC-15
- [ ] `BOOKS_SHOTS_PASSWORD=<admin password> npm run screenshots:home` in `rarebooks-site` with both sites served → logs `home-dashboard-tzs` and `-usd`, writes `public/og/home.jpg`, then runs `npm run screenshots` → AC-16
- [ ] Stop one site and run it again → stops naming the shot and the route, prints "No screenshot was moved", and `git status` shows no changed source → AC-16
- [ ] `npm test` in `rarebooks-site` → `tests/marketing/home.test.ts` passes (`fill`, `splitHighlight`) → AC-3
- [ ] `grep -rn "localDuration\|abroadDuration" src` → nothing → AC-4
- [ ] `ls -l public/screenshots/home-dashboard-*-960.avif` → each at most 80 KB (15 KB at this build) → AC-17
- [ ] `public/og/home.jpg` is 1200 by 630 and under 150 KB (39 KB at this build) → AC-13

## UI / manual
- [ ] Open `/books/` on `shots-tzs.localhost` as Administrator → Account balances lists Kilima Bank Account, Mobile Money and Cash, all positive; Best sellers shows a Top 5; no trial banner → AC-15
- [ ] Open the Point of Sale → a shift is open, Walk in customer is the customer, items search by name → AC-15
- [ ] `/` with `cf-ipcountry: TZ` at 1280 wide → overline "For shops and small businesses", h1 "Your stock and sales, always current" with "current" highlighted, the Tanzania lead, "Free for 21 days, then TZS 300,000 a year. We can set up your shop for you.", and the TZS dashboard shot → AC-3, AC-5
- [ ] `/` with `cf-ipcountry: US`, and with no country header → h1 "Clear books, confident stock", "Free for 21 days, then USD 399 a year or USD 39 a month.", the USD shot → AC-3
- [ ] Phone, 390 by 844 → the h1 and both buttons show without scrolling; buttons are full width → AC-5
- [ ] DevTools Network → the hero image loads eagerly with `fetchpriority="high"`; the page has one h1 → AC-5
- [ ] Start free trial in the hero links to `/auth/sign-up` with `data-cta-location="hero"`; signed in, it reads "Go to your dashboard" and links to `/dashboard` → AC-12
- [ ] Watch the demo opens the Arcade demo in a new tab (the dialog replaces this in build plan step 5) → AC-5
- [ ] View source of `/` inside `<main>` → no "30 days free" or "30 day trial" → AC-4

## Value sourcing
- [ ] Tanzania or abroad: TZ gets the local copy; KE, US and no header get the abroad copy → `isTanzania(countryCode ?? "US")`
- [ ] Trial days: change `AppConfig.trial.freeDays` locally to 14 → the price line reads 14; change it back → `AppConfig.trial`
- [ ] Prices: the price line matches `hostedPlan.priceTZS.yearly` and `priceUSD.yearly` / `.monthly` exactly as stored → `AppConfig.hostedPlan`
- [ ] Screenshot set: TZ shows `home-dashboard-tzs-*`, everyone else `home-dashboard-usd-*` → `src/data/screenshots.json`
- [ ] Signed in: with a Clerk session the hero button reads "Go to your dashboard"; with `auth()` throwing the page still answers 200 signed out → `isSignedIn(Astro.locals)`
- [ ] Seed data dates: run the seed on a later day → sales still span the last 30 days and the opening entries sit 31 days back → `frappe.utils.today()`
- [ ] Capture credentials: the script reads only `BOOKS_SHOTS_TZS_URL`, `BOOKS_SHOTS_USD_URL` and `BOOKS_SHOTS_PASSWORD`, and logs no password → environment

## Still owed (later build plan steps)
- [ ] Deployed: Lighthouse mobile on the live homepage before this ships (the spec 0018 baseline), then after: LCP ≤ 2.5 s, CLS ≤ 0.1, Accessibility and SEO 100 → AC-17
- [ ] Steps 2 to 6: the other four shots, the og image wired into `Layout`, the remaining bands, the demo dialog, the claim walk and axe → AC-1, AC-2, AC-6 to AC-14

## Acceptance-criteria coverage
- AC-3: hero copy steps, home.test.ts, value sourcing (country) · AC-4: grep and view source steps · AC-5: hero, phone and Network steps · AC-12: hero button step (hero only so far) · AC-13: og image size step · AC-15: guard tests, seed, rerun, wrong currency and /books steps · AC-16: capture and failure steps · AC-17: image budget step, deployed Lighthouse owed · AC-1, AC-2, AC-6 to AC-11, AC-14: later steps

---

# Verify: Marketing homepage, build plan steps 2 to 5 · spec 0019 · updated 2026-11-25

## Built in this run
Every shot in both currencies, `Layout`'s `ogImage`, the new title and description, the trust row, features, trial promise, pricing teaser, FAQ, demo dialog and closing call to action, and the old components removed. Not yet: the deploy, the AC-14 claim walk, deployed Lighthouse.

**Deviation to settle in the spec (`/architect`)**: the Books Profit and Loss report has no from and to date filters. `home-profit` opens it with Based On `Until Date`, To Date today, Monthly, Number of Months 1; the report counts that month back from To Date, so its one column covers the 30 seeded days.

**Note**: AC-5 says the hero is the only eager image. The spec 0018 `MkLogo` (32 pixels, in the nav and the footer) is also eager. Decide whether the footer one should be lazy.

## Commands
- [x] `npm test` in `rarebooks-site` → `home.test.ts` passes: every placeholder in both versions has a value, no "30 day" wording, FAQ shows 21, 22, 26, 30, TZS and USD prices, shot set by country, quote gate → AC-3, AC-4, AC-7, AC-9, AC-10
- [x] `BOOKS_SHOTS_PASSWORD=<admin password> npm run screenshots:home` → logs ten shots (five per site), writes `public/og/home.jpg`, then `npm run screenshots` lists all ten → AC-8, AC-16
- [x] `ls -l public/screenshots/home-*-960.avif` → each at most 80 KB (largest 21 KB) → AC-17
- [x] `grep -rln "Comparison\|Guarantee\|components/Pricing\|CallToAction" src --include=*.astro` → only comments, no imports → AC-2
- [x] `npm run check` → no errors in `src/components/marketing/home/`, `src/pages/index.astro`, `src/constants/home.ts` (19 older errors elsewhere remain, down from 41) → AC-2

## UI / manual
- [x] `/` with `cf-ipcountry: TZ` at 1280 → seven bands in order: hero, trust (tint), features (four rows, 2 and 4 reversed, `-tzs` shots), trial (pink), pricing, FAQ (tint), call to action (ink); one h1 → AC-1, AC-8
- [x] Same with `US` and with no header → abroad copy, `-usd` shots, no Talk to us → AC-3, AC-10
- [x] Trust row → overline and the two client names, no quote card while `AppConfig.testimonial` is empty → AC-7
- [ ] Fill all three `AppConfig.testimonial` fields locally → one quote card shows; empty one → it goes → AC-7
- [x] Every body Start free trial links to `/auth/sign-up` with `data-cta-location` `hero`, `trial`, `pricing`, `final_cta_section` → AC-12
- [ ] Signed in (Clerk session) → all four read "Go to your dashboard" and link to `/dashboard`; Watch the demo, Talk to us and Contact us unchanged → AC-12
- [x] Network panel: no request to `demo.arcade.software` before Watch the demo; after the click the iframe loads → AC-6
- [x] Escape closes the dialog, removes the iframe, and focus returns to Watch the demo; Close demo closes it; a backdrop tap closes it at 1280 → AC-6
- [x] Dialog fills the screen at 390 wide and is 64rem (1024 pixels) wide at 1280 → AC-6
- [x] JavaScript off → the button stays hidden and the noscript "Watch the demo" link shows → AC-6
- [x] Talk to us (TZ) and the last FAQ answer's Contact us both open `contact-us-modal` → AC-10, AC-11
- [x] Head: title "RareBooks: accounting, stock and point of sale for small businesses", the new description, canonical `https://rarebooks.cc/`, `og:image` `https://rarebooks.cc/og/home.jpg` with width 1200, height 630 and alt, `twitter:image` → AC-13
- [x] axe (axe-core 4.10) at 1280 and 390, TZ and US, and with the dialog open → no violations → AC-17
- [x] 390 wide → no sideways scroll; trial, pricing and call to action buttons full width → Phone layout
- [ ] Walk every claim in *Page copy* on the seeded sites (balances, best sellers, point of sale with barcode scanner, stock levels, expenses, profit and loss, daily backups, CSV export) and confirm the abroad free import offer is real → AC-14
- [ ] Deployed Lighthouse mobile: LCP ≤ 2.5 s, CLS ≤ 0.1, Accessibility and SEO 100, image transfer before scroll ≤ 150 KB, none worse than the spec 0018 baseline → AC-17

## Value sourcing
- [x] Quick start price: the Tanzania pricing line reads "TZS 75,000" from `localServices[1].price`
- [x] Included points: the check list is the first four `hostedPlan.features`
- [x] Support email and docs link in the last FAQ answer come from `AppConfig.emails.supportEmail` and `urls.docsHomePath`
- [ ] Change `hostedPlan.priceUSD.yearlySaving` locally → the abroad note changes; change it back
- [x] og image URL: `new URL("/og/home.jpg", rootUrl)` gives `https://rarebooks.cc/og/home.jpg`
- [x] Demo iframe src equals `AppConfig.urls.demoUrl`
- [ ] Contact clicks push `cta_location` `pricing_setup` and `faq` into `dataLayer`

## Acceptance-criteria coverage (this run)
- AC-1 band order · AC-2 removal and check · AC-3 copy tests and both countries · AC-4 trial test · AC-6 dialog steps · AC-7 trust and quote gate · AC-8 shots · AC-9 trial step · AC-10 pricing and Talk to us · AC-11 FAQ Contact us · AC-12 trial links, signed in step open · AC-13 head step · AC-14 claim walk open · AC-16 capture · AC-17 axe and image sizes done, Lighthouse open
