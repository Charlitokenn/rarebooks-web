# Verify: Welcome page after sign up · spec 0023 · updated 2026-11-26 (first /check verify run: local Worker against a signed stub control site, Clerk dev instance)
_Steps derived from spec 0023 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

Run against staging: the control site deployed first (build plan step 3), then the Worker. Use a fresh Clerk test user unless a step says otherwise.

## UI / manual
- [ ] Signed out, open `/welcome?x=1` → Clerk sign in; after sign in you land on `/welcome?x=1` (path and query kept) → AC-1, AC-2
- [x] Open `/welcomefoo` signed out → 404, no sign in redirect → AC-1
- [ ] Sign up a new user in Clerk → you land on `/welcome` (not `/welcome/start` or `/dashboard`) and see the start form → AC-2, AC-3
- [ ] Sign up but don't verify the email (or use a user whose primary email is unverified) → `/welcome` shows "Verify your email address first…" and a **Refresh** button that reloads `/welcome`, no form → AC-3
- [ ] Submit the start form with `acme` → the page reloads to the waiting card: "Welcome, <first name>", "Your site will be at acme.rarebooks.cc" as plain text (not a link), the four step checklist, the "This usually takes a few minutes…" line and three links that open in a new tab → AC-5, AC-6, AC-8
- [x] View source of that first waiting render: the card is in the HTML; the network tab shows no `/api/onboarding/status` call in the first 3 seconds → AC-5
- [x] Watch the checklist: **Getting your site** In progress while Queued or Claiming, **Making your account** at Preparing `Owner`, **Setting up your address** at Preparing `Domain`; each state is visible text and the current step has `aria-current="step"` → AC-5
- [x] Keep the page open until Ready → the browser goes to `/welcome/open` and then the password set page of the site → AC-6, AC-4
- [ ] As that Ready owner, sign out, then sign in on rarebooks.cc → `/welcome` → `/welcome/open` → the site, with no page rendered in between → AC-2, AC-3, AC-4
- [x] Make `owner_link` fail once (stop the hosted site or block it) and open `/welcome` as the Ready owner → you end on `/welcome?open=retry` with "We couldn't open your site just now. Try again in a moment." and an **Open your site** button; no loop → AC-4
- [x] Open `/welcome?open=retry` as a user whose site is still waiting → the waiting card, no retry line → AC-3
- [x] Release (spec 0016) a Ready or Failed sign up, then open `/welcome` as its user → the D1 row is dropped and the start form shows → AC-3
- [x] Fail a sign up at the address step, then load `/welcome` fresh → the failed card, **Setting up your address** marked Failed, the support email, and no address and no `failed_reason` anywhere in the HTML → AC-7, AC-8
- [x] Fail one at the owner step → **Making your account** Failed; one with no step → **Getting your site** Failed → AC-7
- [x] On every `/welcome` outcome: logo linking to `/`, Clerk `UserButton` (manage account, sign out to `/`), the dashboard chat widget loads at once, `<title>Welcome to RareBooks</title>`, `noindex`, no sidebar or breadcrumbs, no sideways scroll at 390 px → AC-11
- [x] Signed in on the homepage, pricing and a compare page: the nav button reads **Your site**, every former dashboard button reads **Open your site**, and all go to `/welcome` with their `data-cta-location` unchanged → AC-10
- [ ] A new Ready email links to `/welcome/open` and reads "The button opens your site. You may be asked to sign in first, so only you can open it." → AC-10
- [x] `/getting-started/create-your-site/` describes `/welcome`, the checklist and **Open your site** → AC-10

## Commands
- [x] `curl -sI https://<staging>/dashboard/site/open?x=1` → `302`, `Location: /welcome/open?x=1`, `Cache-Control: no-store` → AC-9
- [x] `curl -sI` on `/dashboard`, `/dashboard/`, `/dashboard/start`, `/dashboard/settings`, `/dashboard/anything` → `302` to `/welcome` (query kept) → AC-9
- [x] `curl -sI` on `/dashboardx` and `/Dashboard` → no redirect (404) → AC-9
- [x] `curl -s -X POST -H "Origin: https://<staging>" https://<staging>/dashboard` → 404 → AC-9
- [x] As a signed in Ready owner (session cookie): `curl -sI https://<staging>/welcome` (HEAD) → 200 with the Ready card, and the control site's log shows no `owner_link` call → AC-3
- [x] Same owner: `curl -s -o /dev/null -w "%{http_code} %{redirect_url}" -H "Sec-Purpose: prefetch" https://<staging>/welcome/open` → `302 /welcome`, no `owner_link` call → AC-4
- [x] Same owner, plain GET of `/welcome/open` → `302` to the site with `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; the Worker log line is `welcome/open: 200` with no URL → AC-4
- [x] Rendered `/welcome` responses carry `Cache-Control: private, no-store, no-transform` → AC-3
- [x] `GET /api/onboarding/status` while waiting → `address` set; for a Failed sign up → `address: null` → AC-8
- [x] Control site: `bench --site <site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_onboarding` → all pass → AC-7, AC-8
- [x] rarebooks-site: `npm test` → all pass, including `tests/welcome/` and the no `/dashboard` guard → AC-1, AC-3 to AC-5, AC-7 to AC-10
- [x] rarebooks-site: `npm run build` passes; `npm run check` shows no new errors (11 errors predate this spec) → AC-12

## Value sources
- [x] Which outcome renders: vary the sign up (none, unverified email, each status, control down) and confirm the matching card → `readSignupStatus`, `isPrefetch`, `open`, primary email verification → AC-3
- [ ] Redirect URL from `/welcome/open`: with and without a password set on the site → the password set link, then `/login` → control `owner_link` → AC-4
- [ ] First name: a Clerk user with a first name shows it; one without shows the email part before the `@` → AC-5
- [ ] Address: a different subdomain shows that subdomain without `https://`; Failed shows none → control `_summary.address` → AC-5, AC-8
- [x] Current step: each status and step (including no step and an unknown step at Preparing) → AC-5
- [x] Failed step: `Owner`, `Domain`, none → AC-7
- [x] Support email equals `AppConfig.emails.supportEmail` → AC-7
- [x] Docs links: each of the three opens a real docs page (not a 404) → `welcomeDocs` → AC-5
- [x] Retry line only with `open=retry` at Ready → AC-3, AC-4
- [x] Island starting state: the server's status, step, address and first name match the first paint → AC-5, AC-6
- [x] Legacy redirect: target path from `legacyTarget`, query kept, code 302 → AC-9
- [ ] Ready email open URL uses `PUBLIC_SITE_URL` + `/welcome/open` → AC-10
- [x] Nav and CTA labels and hrefs come from `welcomePath`, `welcomeLabel`, `welcomeNavLabel` → AC-10
- [ ] Start form success goes to `/welcome`; `SiteStatus` opens `/welcome/open` → AC-6

## Acceptance-criteria coverage
- AC-1: UI steps 1, 2 · unit test `WELCOME_ROUTE`
- AC-2: UI steps 1, 3, 9
- AC-3: UI steps 3, 4, 11, 12 · commands HEAD, cache header · value source "which outcome"
- AC-4: UI steps 8 to 10 · commands prefetch, plain GET
- AC-5: UI steps 5 to 7 · value sources first name, address, step, docs links
- AC-6: UI steps 5, 8
- AC-7: UI steps 13, 14 · control site tests
- AC-8: UI steps 5, 13 · command status API · control site tests
- AC-9: commands curl set · unit tests `legacyTarget`
- AC-10: UI steps 16 to 18 · guard test
- AC-11: UI step 15
- AC-12: commands build and check
