# Verify: pricing page · spec 0020 · updated 2026-11-25
_These steps come from the spec 0020 acceptance criteria. `/check verify` runs them, and `/test` locks in the ones that should keep running. You fake the country with a `cf-ipcountry: TZ` or `KE` header (on `wrangler dev`, or on `astro dev`, which reads the same header in the middleware)._

## UI / manual
- [ ] Open `/pricing` with `cf-ipcountry: TZ`. You should see one h1 and five bands in this order: plans (canvas), setup (tint), included (canvas), FAQ (tint), call to action (ink). The contact modal appears once, after the footer → AC-1
- [ ] With `TZ`: you see one wide card with "The plan", "RareBooks", TZS 300,000 a year, the 8 features and Start free trial. Below it is only "Every plan includes unlimited users and devices.", and the body has no dollar price, PayPal or card payment anywhere → AC-3, AC-4, AC-6
- [ ] With `KE`, and again with no header: you see Yearly first with a brand border and "Best value", the free data import line and USD 399. Monthly comes second at USD 39. Below them is only the unlimited line, and the body has no TZS price or mobile money anywhere. Under 768 pixels the cards stack with Yearly on top → AC-3, AC-5, AC-6
- [ ] Signed out: every plan button is `/auth/sign-up` with `data-cta-location="pricing_page"` and `data-plan-name` set to RareBooks, RareBooks Yearly or RareBooks Monthly. Clicking one pushes `trial_interest` with that plan name to `dataLayer` → AC-7
- [ ] Signed in: every plan button and the closing button read "Go to your dashboard" and go to `/dashboard`. Clicking them pushes no `trial_interest`. The setup and FAQ contact buttons stay the same → AC-7
- [ ] Setup band: with `TZ` you see Digitize your notebooks, then Quick start, two across. With `KE` you see one centered "Free data import" card with no check list. Each button opens the contact modal and carries `pricing_page_setup` → AC-8
- [ ] Included band: seven groups, one column at 390 pixels, two at 640 and three at 1024 → AC-9
- [ ] FAQ: five rows in each version (the pay and cancel answers differ by version). Contact us opens the modal → AC-10
- [ ] Record each claim as shown on the demo shop or confirmed on the control site: the receipt email after ClickPesa and PayPal payments, one PayPal card checkout without an account, renewal until cancel and access to the end of the period, the 7 day grace, and the download link email and removal. Record your confirmation of the data import offer → AC-11
- [ ] The head has the title "RareBooks pricing: one plan, everything included", the description, the canonical `https://rarebooks.cc/pricing`, `/og/home.jpg` with its alt text, and the Fraunces preloads. All of these are identical for `TZ`, `KE` and signed in → AC-12
- [ ] After the deploy, inspect `/pricing` in Search Console (URL Inspection) and record any structured data warning about the TZS `Offer`. If there is one, drop the TZS `Offer` from `pricingJsonLd` → AC-6, AC-13
- [ ] Run the deployed page through the Schema.org validator and expect no errors. Expect three Offers: 300000 TZS ANN, 39 USD MON and 399 USD ANN → AC-13
- [ ] On the nav and in the phone sheet, Pricing goes to `/pricing` and has `aria-current="page"` only on `/pricing`. On the homepage, `/#pricing` still scrolls to the teaser, and "See full pricing" under the card goes to `/pricing` → AC-14
- [ ] At 390 by 844 in both versions: no sideways scroll, the h1 and the first price show without scrolling, and buttons are full width under 640 pixels → AC-15
- [ ] On the deployed `/pricing`, Lighthouse mobile should show LCP ≤ 2.5 s, CLS ≤ 0.1, Accessibility 100 and SEO 100. axe should report no violations in either version. Using only the keyboard, you can reach every button and FAQ row with a visible focus ring, and the modal opens and closes from each contact button → AC-16

## Value sourcing
- [ ] Change `hostedPlan.priceUSD.yearly` in a scratch build. The abroad Yearly card, the meta description and the JSON-LD should all follow, and the Tanzania body should not change → AC-3, AC-13
- [ ] Change `AppConfig.renewal.graceDays`. FAQ row 5 should follow → AC-17
- [ ] Change `AppConfig.trial.freeDays`. The lead, FAQ row 1 and the meta description should follow → AC-3
- [ ] Send `cf-ipcountry: tz` in lower case, or `TZA`. The abroad version shows, because `isTanzania` matches only `TZ` exactly → AC-3

## Commands
- [ ] `curl -sI https://rarebooks.cc/pricing -H "cf-ipcountry: TZ" | grep -i cache-control` → `private, no-cache` (never `no-store`) → AC-1
- [ ] `npm test` in `rarebooks-site` → `tests/marketing/pricing.test.ts` and `navigation.test.ts` pass → AC-13, AC-14, AC-17
- [ ] `npm run build` → builds with no error → AC-1

## Acceptance-criteria coverage
- AC-1: band order, modal, header, build · AC-2: the review of the `pricing/` components (only `mk` parts) · AC-3 to AC-6: the country steps · AC-7: the signed out and signed in steps · AC-8: setup · AC-9: included · AC-10: FAQ · AC-11: the claims record · AC-12: head · AC-13: validator, node tests · AC-14: nav and teaser · AC-15: phone pass · AC-16: Lighthouse, axe, keyboard · AC-17: node tests, Value sourcing

## Results
- 2026-11-25, `/develop` self check on `astro dev`: with `TZ` and `KE`, at 1280 by 900 and 390 by 844, there was one h1, the five bands were in order, there was no sideways scroll, and the first price sat at 478 pixels of 844. Pricing had `aria-current` in the nav and in the sheet, the JSON-LD prices were 300000, 39 and 399, and the header was `private, no-cache`. The deployed checks are still open.
