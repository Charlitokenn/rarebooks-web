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
- [ ] `/` with `cf-ipcountry: US`, and with no country header → h1 "Clear books, confident stock", "Free for 21 days, then $399 a year or $39 a month.", the USD shot → AC-3
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
