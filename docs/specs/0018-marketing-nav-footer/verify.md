# Verify: Marketing nav and footer · spec 0018 · updated 2026-11-25
_Steps derived from spec 0018 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Baseline (AC-13)

Taken before step 1, on a local `npm run dev` of `rarebooks-site` (`site-revamp` at `59c1ec7`), with GTM, tawk.to and Turnstile blocked. Cumulative Layout Shift, three loads each, from a `layout-shift` PerformanceObserver in Playwright Chromium:

| Page | Width | Before | After this build |
|---|---|---|---|
| `/` | 390 | 0.0014, 0.0010, 0.0014 | 0.0013, 0.0013, 0.0013 |
| `/` | 1280 | 0.0007, 0.0007, 0.0007 | 0.0008, 0.0007, 0.0008 |

Still owed: the **deployed** homepage Lighthouse mobile numbers (Accessibility score and CLS). The build container can't reach rarebooks.cc, so take them from a machine that can, on the live site before this change ships, then again after.

## UI / manual
- [ ] At 390 px on `/`, Tab once → "Skip to content" shows above the header; Enter → focus lands in `<main id="main">` → AC-6
- [ ] Scroll any marketing page → the header stays at the top, 64 px tall, over page content and the tawk.to widget → AC-2
- [ ] On `/`, click Features and Pricing in the header → each heading lands below the header, not under it → AC-2
- [ ] At 1280 px, the row reads Features, Pricing, Compare, Docs; below 768 px only the logo and Menu show → AC-3
- [ ] Signed out: header shows Sign in (`/auth/sign-in`) and Start free trial (`/auth/sign-up`), and a trial sign up lands on `/dashboard/start` → AC-4
- [ ] Signed in (a Clerk dev account): header, menu and footer show Dashboard only, in the first HTML response (`curl` with the session cookie, or View Source), with no swap after load → AC-4, AC-9
- [ ] At 390 px, open Menu → focus on Features; Tab and Shift+Tab never reach page content behind; the page doesn't scroll → AC-5
- [ ] Close the menu by Escape, by Close, by a backdrop tap → focus returns to Menu each time → AC-5
- [ ] Tap Pricing in the menu on `/` → the menu closes and the page scrolls to pricing → AC-5
- [ ] Open the menu, widen the window past 768 px → it closes and focus moves to the desktop Features link → AC-5
- [ ] With reduce motion on, the menu opens and closes with no slide → AC-5
- [ ] On `/compare` Compare has `aria-current="page"`, on `/compare/gnucash` `aria-current="true"`, both underlined; on `/alternatives/gnucash` no nav link is marked → AC-7
- [ ] Click each Start free trial (header, menu, footer) → `dataLayer` gets `trial_interest` with `cta_location` `nav`, `nav-mobile`, `footer` → AC-8
- [ ] Footer: Product, Compare, Resources columns (Legal hidden), stacked at 390, two across at 640, four across at 1024; three social links named "RareBooks on …", new tab, 44 px targets; `© 2026 RareBooks. All rights reserved.` → AC-9
- [ ] Visit `/a-made-up-path` → 404 status, the new header and footer, buttons to home and the docs → AC-1
- [ ] `/auth/sign-in`, `/auth/sign-up` and `/design-system` show no MkNav or MkFooter → AC-1
- [ ] `/privacy` and `/terms` show the draft banner and "Last updated 25 November 2026" → AC-10
- [ ] Read the drafts: privacy names Clerk, Cloudflare, Google Tag Manager, tawk.to, Resend, ClickPesa, PayPal, Frappe Cloud, the controller and the support contact, and the day 21, 22, 26 and 30 numbers; terms cover the trial, plans and renewal, the lock, the removal, acceptable use and support → AC-11
- [ ] At 1280 and 390 on `/` and `/compare/gnucash`: axe DevTools shows no violations in header, menu or footer → AC-13
- [ ] Deployed homepage: Lighthouse mobile Accessibility 100, CLS no worse than the baseline → AC-13

## Value sourcing
- [ ] Change a label in `navLinks` → it changes in the header, menu and nowhere else needs an edit → AC-3
- [ ] Make `locals.auth` throw (or remove the Clerk cookie mid session) → the page still answers 200 with the signed out set → AC-4
- [ ] `/compare/` (trailing slash) → `aria-current="page"`; `/comparenot` → nothing → AC-7
- [ ] Set `AppConfig.legal.approved` to true (locally) → the Legal column shows, the banner, meta robots and `X-Robots-Tag` go away; back to false → all return → AC-10
- [ ] Change `AppConfig.legal.updated` to `2027-01-05` → "Last updated 5 January 2027", the same in any server time zone → AC-10
- [ ] The footer year reads the server clock at request time (not the build) → AC-9
- [ ] Support link is `mailto:support@rarebooks.cc` from `AppConfig.emails.supportEmail` → AC-9
- [ ] The docs link `/getting-started/getting-started-with-rarebooks/` answers 200 with no redirect → AC-3

## Commands
- [ ] `npm test` → the 8 tests in `tests/marketing/navigation.test.ts` pass (links, auth fallback, Compare marker, footer filter, trial locations, legal gate, one `<main id="main">` per page, no React and a script under 1 KB) → AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-10, AC-12
- [ ] `grep -rn "pt-36" src` → nothing → AC-2
- [ ] `grep -rn "Navbar.astro\|components/Footer" src` → nothing → AC-1
- [ ] `curl -sI http://localhost:4321/privacy | grep -i x-robots` → `X-Robots-Tag: noindex` while not approved; `curl -s` every marketing page `| grep -c 'href="/privacy"'` → 0 → AC-10
- [ ] `npm run check` → no errors in the new or changed files (the 19 older errors elsewhere are unrelated) → AC-1
- [ ] `npm run build` → succeeds → AC-1

## Notes from the build
- Chromium's own modal dialog lets Tab step out to the browser UI once between Close and Features (a headless run reports it as the demo iframe). It never reaches the page behind, which is inert. Confirm in a real browser that this is acceptable for AC-5.
- The signed in render was checked through the `isSignedIn` unit test, not a real signed in browser session. The manual signed in step above covers it.

## Acceptance-criteria coverage
- AC-1: 404, auth and design system steps, grep and build commands · AC-2: sticky and anchor steps, `pt-36` grep · AC-3: row and phone steps, `navLinks` and docs link steps · AC-4: signed out, signed in and throwing auth steps · AC-5: the six menu steps · AC-6: skip link step, `<main>` test · AC-7: Compare marker steps · AC-8: trial tracking step · AC-9: footer, year and support steps · AC-10: legal page, approval and date steps, `X-Robots-Tag` command · AC-11: the drafts reading step · AC-12: node test · AC-13: baseline table, axe and deployed Lighthouse steps
