# Verify: Marketing site load speed · spec 0022 · updated 2026-11-26
_Steps derived from spec 0022 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Speed results (AC-1, AC-13)

Lighthouse 12.8.2, mobile preset, Performance and Accessibility only, median of 3 runs per page.

### Before: the deployed site, 2026-11-26 (build plan step 1)

| Page | LCP s | TBT ms | CLS | Perf | A11y |
|---|---|---|---|---|---|
| `/` | 2.79 | 590 | 0.009 | 79 | 100 |
| `/pricing` | 2.72 | 826 | 0.009 | 77 | 100 |
| `/compare` | 2.24 | 683 | 0.009 | 79 | 100 |
| `/compare/xero` | 2.06 | 635 | 0.009 | 80 | 100 |
| `/alternatives` | 2.04 | 545 | 0.009 | 83 | 100 |
| `/alternatives/xero` | 2.72 | 727 | 0.009 | 77 | 100 |
| `/privacy` | 2.25 | 467 | 0.009 | 85 | 100 |
| `/terms` | 2.44 | 691 | 0.009 | 79 | 100 |
| 404 | not measured | | | | |

Every page misses TBT ≤ 200 ms; `/`, `/pricing` and `/alternatives/xero` also miss LCP ≤ 2.5 s. Lighthouse refuses a page that answers status 404 (`ERRORED_DOCUMENT_REQUEST`), so the 404 page needs another method (for example a Performance trace in Chrome DevTools), or AC-1 should drop it.

### After the build, local only (`astro preview`, not the deployed site)

| Page | LCP s | TBT ms | CLS | A11y |
|---|---|---|---|---|
| `/` | 5.17 | 62 | 0.000 | 100 |
| `/pricing` | 4.79 | 64 | 0.000 | 100 |
| `/compare` | 4.49 | 69 | 0.000 | 100 |
| `/compare/xero` | 4.77 | 70 | 0.000 | 100 |
| `/alternatives` | 4.61 | 71 | 0.000 | 100 |
| `/alternatives/xero` | 4.74 | 56 | 0.000 | 100 |
| `/privacy` | 4.38 | 7 | 0.000 | 100 |
| `/terms` | 4.67 | 0 | 0.000 | 100 |

These numbers do not count for AC-1. The local LCP is not comparable: the Clerk development instance sends every page through a `__clerk_handshake` redirect, which production does not. TBT and weight do compare: TBT fell from 467 to 826 ms to 0 to 71 ms, and `/pricing` went from 1425 KB to 534 KB. On `/pricing` the main thread work left is Clerk's (`clerk-js` and `ui`) plus the page itself.

### After: the deployed site

- [ ] Deploy, then run 3 mobile runs per page above and record the medians here → AC-1
- [ ] If any page misses a target, record its numbers, the main thread time of `clerk.browser.js` and `ui.browser.js`, and its server response time, then open the follow up spec → AC-13

## UI / manual
- [ ] Open `/` at 390 px and wait 3 s without touching → no request to `embed.tawk.to`, `googletagmanager.com`, `google-analytics.com`, `/163f/`, `challenges.cloudflare.com` or a `ContactUsForm` chunk → AC-2, AC-4, AC-5, AC-10 (passed locally)
- [ ] Scroll once → tawk.to loads, once → AC-2 (passed locally)
- [ ] Load `/privacy` and don't touch → tawk.to requested about 10 s after `load` → AC-2 (passed locally: 10.0 s)
- [ ] Open `/dashboard` signed in → tawk.to loads at once, as before → AC-2
- [ ] Signed in on a marketing page, open the chat → it shows your name and email (Secure Mode hashes unchanged) → AC-2
- [ ] On `/pricing`, click "Talk to us" in the FAQ before scrolling → the chat opens and no message shows → AC-3 (passed locally with a stubbed tawk.to)
- [ ] Block `embed.tawk.to` and click it again → after 8 s "Chat could not load. Write to support@rarebooks.cc." shows, with a plain mailto link, and a screen reader announces it → AC-3 (text and link passed locally)
- [ ] Click once more → the message clears and the 8 s wait starts again → AC-3 (passed locally)
- [ ] Ctrl or Cmd click a Contact us link, and middle click one → email opens, not the chat → AC-3 (Ctrl click not intercepted, passed locally)
- [ ] Turn JavaScript off and click a Contact us link → email opens → AC-3
- [ ] Each Contact us control (homepage teaser for a Tanzania visitor, homepage FAQ, pricing setup cards, pricing FAQ) carries its `data-cta-location` → AC-3
- [ ] With the PostHog key set, load `/compare/xero` and click Start free trial → `/ingest` gets a `$pageview`, then `trial_interest` with `cta_location=compare_page_header`; `array.js` is requested only after `load` → AC-6, AC-7, AC-8
- [ ] Click a pricing plan's Start free trial → `trial_interest` carries `plan_name`; a header one carries `plan_name` null → AC-6
- [ ] Click a Contact us link → `contact_click` with its `cta_location` → AC-6
- [ ] In PostHog, the visitor stays anonymous (no identify call, no name or email) → AC-7
- [ ] With no key (local dev), the HTML has no snippet, no `/ingest` request is made and the console shows no error → AC-9 (no snippet, no request and no page error passed locally)
- [ ] Block PostHog and tawk.to → the page, its links and sign up still work and show no error → AC-9
- [ ] Complete a sign up on `/dashboard/start` → Turnstile passes → AC-10
- [ ] Read `/privacy` → the PostHog line in AC-11 is there, the tawk.to line stays, Google Tag Manager is gone → AC-11
- [ ] Run axe on the AC-1 pages, also with the AC-3 message showing → no violations → AC-14
- [ ] Tab through each AC-1 page → every link and button is reachable with a visible focus ring, the Contact us links included → AC-14

## Commands
- [ ] `curl -s -o /dev/null -w "%{http_code}" -X POST -H "Origin: https://rarebooks.cc" https://rarebooks.cc/api/contact-us` → `404` → AC-4 (passed locally; without an Origin header Astro's origin check answers 403 first)
- [ ] `curl -sI https://rarebooks.cc/ingest/static/array.js` → 200, JavaScript, PostHog's `cache-control` → AC-8
- [ ] `curl -s -X POST -H "Cookie: __session=x" --data '{}' https://rarebooks.cc/ingest/e/` → PostHog's answer, no Clerk redirect, no `no-transform` cache header added → AC-8
- [ ] With PostHog unreachable, `/ingest/e/` → 502, empty body → AC-8 (passed locally: the local Worker can't reach the internet here)
- [ ] `npm test` in `rarebooks-site` → all pass → AC-12, AC-14 (passed: 69 of 69)
- [ ] Put `client:load` back on a marketing component in a scratch copy and run `npm test` → it fails → AC-12 (covered by a unit test of the guard)
- [ ] `npm run check` in `rarebooks-site` → no new errors → AC-14 (passed: 11 errors, all in files this build did not touch; 24 before, the other 13 were in the deleted form)

## Value sourcing
- [ ] PostHog key: set `PUBLIC_POSTHOG_KEY`, then empty it → snippet present, then absent → AC-9
- [ ] Init options: the AC-7 list exactly, in the page source → AC-7 (unit test)
- [ ] Proxy upstream host: `/ingest/static/*` and `/ingest/array/*` reach `eu-assets.i.posthog.com`, `/ingest/e/` and `/ingest/flags/` reach `eu.i.posthog.com` → AC-8 (unit test; matches PostHog's Cloudflare guide and posthog-js 1.455.4)
- [ ] Proxy headers: a request with `cookie`, `authorization` and `cf-ray` reaches PostHog with only the four allowed headers plus `X-Forwarded-For` → AC-8 (unit test)
- [ ] `X-Forwarded-For`: PostHog shows the visitor's real country, not a Cloudflare data center's → AC-8
- [ ] `trial_interest` links: only links whose href equals `AppConfig.urls.signUpUrl` count; change the constant in a scratch copy and the old href no longer records → AC-6
- [ ] `cta_location` and `plan_name`: read from the clicked link's `data-cta-location` and `data-plan-name` → AC-6
- [ ] Chat "opened": the timer clears on `onChatMaximized`, and at once when `isChatMaximized()` is already true → AC-3
- [ ] Contact link and fallback address: both come from `AppConfig.emails.supportEmail` → AC-3
- [ ] Secure Mode hashes: unchanged server side HMAC with `TAWK_API_KEY` → AC-2
- [ ] Chat trigger: each of scroll, pointerdown, keydown and touchstart loads it on its own; with none of them, 10 s after `load` → AC-2
- [ ] Fallback delay: the message appears at 8 s, not before → AC-3 (passed locally: empty at 7 s, shown at 8.5 s)

## Acceptance-criteria coverage
- AC-1: speed results above (before recorded; after needs a deploy)
- AC-2: UI steps 1 to 5, value sourcing (chat trigger, hashes)
- AC-3: UI steps 6 to 11, value sourcing (opened, address, delay)
- AC-4: UI step 1, the contact-us command, unit test
- AC-5: UI step 1, unit test
- AC-6: UI steps 12 to 14, value sourcing (trial links, locations)
- AC-7: UI steps 12 and 15, value sourcing (options)
- AC-8: the `/ingest` commands, value sourcing (hosts, headers, IP)
- AC-9: UI steps 16 and 17, value sourcing (key)
- AC-10: UI steps 1 and 18
- AC-11: UI step 19
- AC-12: `npm test`, the guard test
- AC-13: the deployed speed runs
- AC-14: UI steps 20 and 21, `npm test`, `npm run check`
