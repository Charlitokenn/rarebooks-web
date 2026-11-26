# 0023. Welcome page after sign up

**Date**: 2026-11-26 (cross checked the same day: sign in return URL, server to browser handoff, prefetch safe opens, timeouts, a temporary redirect first)
**Status**: In Progress

Amends: spec [0014](../0014-self-serve-onboarding/index.md) (AC-1: the start form moves from `/dashboard/start` to `/welcome`; AC-4: the page moves to `/welcome`, the address is returned while the site is built, and a signed in user whose site is Ready no longer stays on the page; AC-5: the open route moves from `/dashboard/site/open` to `/welcome/open`; AC-6: the Ready email links to `/welcome/open`). Every other rule in spec 0014, and spec [0016](../0016-release-sign-up/index.md)'s released sign up, still holds.

## Summary

The customer area at `/dashboard` becomes one reception page at `/welcome`. A new user fills in the start form there and watches their site being built: a four step checklist, the address it will have, and a few getting started links. Once their site is Ready, anyone signed in who opens `/welcome` goes straight to their own site, decided on the server so the page never flashes. Old `/dashboard` links, including the Ready emails already sent, keep working through redirects: temporary (302) at first, permanent (301) once the move is proven. The sidebar shell and the settings page are removed.

## Requirements

**User stories**:
- As a new visitor who just signed up, I want to pick my address and watch my site being built, so that I know it is working and where it will be.
- As an owner whose site is Ready, I want signing in on rarebooks.cc to take me straight to my site, so that I never land on a page with nothing to do.
- As anyone with an old `/dashboard` link (a bookmark, a nav button, a Ready email), I want it to still work, so that the rename never strands me.

**Acceptance criteria**:
- **AC-1**: `/welcome` and `/welcome/open` need a Clerk session. The middleware protects `/welcome(/.*)?` in place of `/dashboard(.*)`, so `/welcomefoo` is not matched. A signed out visitor goes to Clerk sign in, and afterwards returns to the exact URL they asked for, path and query included.
- **AC-2**: Clerk sign up (`src/pages/auth/sign-up.astro`) uses `forceRedirectUrl="/welcome"`. Clerk sign in (`src/pages/auth/sign-in.astro`) uses `fallbackRedirectUrl="/welcome"`, not `forceRedirectUrl`, so Clerk's return URL from AC-1 wins when there is one, and `/welcome` is used only when there is none.
- **AC-3**: `/welcome` reads the signed in user's sign up on the server, through the same read as `GET /api/onboarding/status`. That read is the D1 row, else `signup_status` by `clerk_user_id` alone, and it drops a stale row on a signed 404 (spec 0016 AC-8). The page's control calls use a 5 second timeout (the API route keeps 15). The server picks exactly one outcome:
  - Status Ready, on a normal page load: answers `302` to `/welcome/open`.
  - Status Ready, on a `HEAD` request or a prefetch (a `Sec-Purpose` or `Purpose` header containing `prefetch`): renders the Ready card (AC-4) and makes no `owner_link` call.
  - Status Ready with `?open=retry`: renders the Ready card with the retry line (AC-4).
  - Queued, Claiming or Preparing: renders the waiting card (AC-5).
  - Failed: renders the failed card (AC-7).
  - No sign up (a signed 404, which includes a released one) and the primary email is verified: renders the start form (spec 0014 AC-1 to AC-3, unchanged).
  - No sign up and the email is not verified: renders "Verify your email address first. Open the email we sent you, then come back to this page." with a **Refresh** button that reloads `/welcome`, and no form.
  - The control site can't be reached in 5 seconds: renders "Loading your site…", and the browser poll takes over (it shows the unreachable line and keeps trying, as today).

  `?open=retry` counts only at Ready. With any other status it is ignored and the normal outcome applies. Every rendered `/welcome` response carries `Cache-Control: private, no-store` (the middleware's `no-transform` is still appended).
- **AC-4**: `/welcome/open` is the only route that asks for the owner link.
  - On `GET` with a Ready sign up, it calls `owner_link` with a 5 second timeout. It answers `302` to that URL (the password set link while the owner has none, else the site's `/login`, spec 0014 AC-5), with `Referrer-Policy: no-referrer` and `Cache-Control: no-store`. The URL travels only in `Location` and is never logged.
  - When `owner_link` fails, is refused or times out, it answers `302` to `/welcome?open=retry`.
  - With no sign up, or one that is not Ready, it answers `302` to `/welcome`.
  - A `HEAD` request or a prefetch answers `302` to `/welcome` and never calls `owner_link`.

  The Ready card reads "Your site is ready at `<address>`" with an **Open your site** button linking to `/welcome/open`. When the answer has no address, the line is left out and only the button shows. With `?open=retry` it adds "We couldn't open your site just now. Try again in a moment." The Ready card has no checklist and never redirects by itself.
- **AC-5**: The waiting card. `/welcome` renders it with the starting state from the server (status, step, address and first name as island props). The browser makes no first fetch and shows no loading flash.
  - It shows "Welcome, `<first name>`": the Clerk `firstName`, else the part of the primary email before the `@`.
  - It shows "Your site will be at `<subdomain>.rarebooks.cc`" as plain text, not a link (the address is not live yet). When the answer has no address, this line is left out.
  - It shows a four step checklist:

    | Step | Current while |
    |---|---|
    | **Request received** | always done |
    | **Getting your site** | Queued or Claiming |
    | **Making your account** | Preparing with step `Owner`, or with no step or an unknown one |
    | **Setting up your address** | Preparing with step `Domain` |

    Steps before the current one are done, and steps after it are pending. Each step shows its state as visible text (Done, In progress, Waiting, or Failed), not colour alone, and the current step carries `aria-current="step"`. The list sits in an `aria-live="polite"` region.
  - It keeps the existing line: "This usually takes a few minutes. Keep this page open and we'll take you to your site as soon as it's ready, or close it and we'll email you."
  - It lists three links, each opened with `target="_blank" rel="noopener"` so this page keeps polling:
    - Getting started with RareBooks, `/docs/getting-started/getting-started-with-rarebooks/`
    - Chart of accounts, `/docs/getting-started/chart-of-accounts/`
    - Set up opening balances, `/docs/getting-started/setup-opening-balances/`
  - Polling keeps today's timing: every 3 seconds for the first 5 minutes from page load, then every 15 seconds, only while Queued, Claiming or Preparing.
- **AC-6**: When the poll sees a site turn Ready while the user watches, the browser goes to `/welcome/open` at once, as today. When the server rendered a waiting card, the island starts with `sawWaiting` true, so even the first poll returning Ready jumps. After the start form submits successfully, the browser reloads `/welcome` (`window.location.assign("/welcome")`), and the server renders the waiting card with the address.
- **AC-7**: The failed card keeps the checklist with the step it stopped at marked Failed. That step comes from the server's `step`: `Owner` is **Making your account**, `Domain` is **Setting up your address**, and no step is **Getting your site**. The control site keeps `step` on a Failed row (only a retry clears it), so this holds on a fresh load too. The card shows "We hit a problem setting up your site. We're on it and will email you." and the support email. It never shows `failed_reason` or the address.
- **AC-8**: The control site's `signup_status` returns `address` (`https://<cloudflare.full_domain(subdomain)>`) for Queued, Claiming, Preparing and Ready, and never for Failed. `GET /api/onboarding/status` passes it through for those same statuses and returns `address: null` for Failed. This amends spec 0014 AC-4's "the address is returned only at Ready".
- **AC-9**: Old links keep working. Before Clerk runs, the middleware matches the path `/dashboard` or anything starting with `/dashboard/`, case sensitive, on a whole path segment (`/dashboardx` passes through untouched). A trailing slash counts as the same path.
  - `GET` and `HEAD` are redirected, keeping the query string, with `Cache-Control: no-store`:
    - `/dashboard` → `/welcome`
    - `/dashboard/start` → `/welcome`
    - `/dashboard/settings` → `/welcome`
    - `/dashboard/site/open` → `/welcome/open`
    - any other `/dashboard/...` → `/welcome`
  - The redirect is a `302` until the staging run and one week live pass with no rollback, then a one line change makes it `301`. That change is the last build task.
  - Other methods pass on to Clerk and the router, which have no `/dashboard` route, so they get a 404.

  A signed out visitor on an old link reaches sign in through `/welcome` and then returns to the new URL (AC-1). A Ready email already sent still opens the site, through `/dashboard/site/open` → `/welcome/open`.
- **AC-10**: No link on rarebooks.cc points at `/dashboard` any more.
  - The marketing nav button for a signed in visitor reads **Your site** and links to `/welcome`.
  - Every former `dashboardLabel` call to action reads **Open your site** and links to `/welcome`, with its `data-cta-location` unchanged.
  - `AppConfig.portalUrl` is `https://rarebooks.cc/welcome`.
  - New Ready emails link to `/welcome/open`. Their line "The button signs you in to your dashboard first, so only you can open it." becomes "The button opens your site. You may be asked to sign in first, so only you can open it."
  - The user doc `getting-started/create-your-site.mdx` describes `/welcome`, the checklist and the **Open your site** button, in place of "your dashboard" and "Set your password".
  - A guard test scans `src/` files ending `.ts`, `.tsx`, `.astro`, `.mdx` and `.json` for the pattern `/\/dashboard(?![\w-])/`, excluding `src/middleware.ts` (the map) and its own test file, and fails on any hit.
- **AC-11**: `/welcome` uses a plain reception layout, `WelcomeLayout.astro`, on every outcome (form, waiting, failed, Ready, retry, verify, loading). It has no sidebar and no breadcrumbs.
  - It shows the logo, linking to `/`, and Clerk's `UserButton`, whose menu holds manage account and sign out. Sign out goes to `/`.
  - It loads the dashboard tawk.to widget at once (`TawkWidget` with `load="eager"`, `widget="dashboard"`).
  - It has `<title>Welcome to RareBooks</title>` and `<meta name="robots" content="noindex">`.
  - It reads well at phone width, with no sideways scroll.
  - The page calls `currentUser()` once and passes the user to the layout and the card. It calls `currentUser()` only on outcomes that render, never on the Ready redirect.
- **AC-12**: The old shell is gone and nothing imports it.
  - Removed: `PortalLayout.astro`, `src/pages/dashboard/` (all four routes), `persisted-sidebar.tsx`, `app-sidebar.tsx`, `nav-main.tsx`, `nav-projects.tsx`, `nav-user.tsx`, `team-switcher.tsx`, `dashboard-header.tsx`, `clerk-user-button.tsx`, `pageHero.tsx`, `ui/sidebar.tsx`, `src/stores/sidebar.ts` and `src/components/lib/sign-out.ts`.
  - Any shadcn `ui/` file or hook that only `ui/sidebar.tsx` imported is removed too.
  - Comments that name PortalLayout (in `TawkWidget.astro`, `src/constants/index.ts` and `src/components/marketing/README.md`) are updated.
  - `npm run check`, `npm test` and `npm run build` pass.

## Decision

**Chosen option**: Option 2: One reception page with a server side Ready redirect and a middleware map for old links.

`/welcome` takes over every job `/dashboard` had: the start form, the build status and the failure. A Ready user is sent from the server to `/welcome/open`, the one route that asks for the owner link. Old `/dashboard` URLs are redirected by the middleware before Clerk runs, temporarily at first and permanently once proven.

**Implementation skills**: `clerk-astro-patterns` (`clerk/skills`, `.agents/skills/clerk-astro-patterns/`) for the middleware matcher, sign in redirect props, SSR redirects and `UserButton` · `workers-best-practices` (`cloudflare/skills`, `.agents/skills/workers-best-practices/`) for the redirect responses, headers and timeouts on the Worker

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**: no schema change. The D1 `signups` table (spec 0014) and the control site's Books Signup are unchanged. `subdomain`, `status` and `step` already exist on Books Signup, and `step` already survives a failure. Only `_summary` in `rarebooks_control/onboarding.py` starts returning the address earlier.

**State transitions**: unchanged from spec 0014 (Queued → Claiming → Preparing (`Owner` → `Domain`) → Ready, or → Failed; Ready or Failed → Released, spec 0016). This spec only maps them to what `/welcome` does:

| Sign up | `/welcome` (server) | Browser |
|---|---|---|
| none or released, email verified | start form | on success, reloads `/welcome` |
| none, email not verified | verify message with Refresh | nothing |
| Queued, Claiming, Preparing | waiting card with starting props | polls; Ready → `/welcome/open` |
| Ready | `302 /welcome/open` (HEAD or prefetch: Ready card) | nothing |
| Ready with `?open=retry` | Ready card with retry line | nothing |
| Failed | failed card with the failed step | no poll |
| control unreachable (5 s) | loading card | polls |

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `/welcome` (page) | GET, HEAD | Clerk session; `open=retry` (optional); `Sec-Purpose` / `Purpose` header | HTML (form, waiting, failed, Ready, verify or loading card), `private, no-store`; or `302 /welcome/open` | Clerk session | signed out → Clerk sign in |
| `/welcome/open` | GET, HEAD | Clerk session; prefetch header | `302` owner link · `302 /welcome?open=retry` · `302 /welcome` | Clerk session | signed out → Clerk sign in |
| `/api/onboarding/status` | GET | Clerk session | `request_id`, `status`, `step`, `address` (now also while waiting) | Clerk session | 401, 404, 503 (unchanged) |
| `/dashboard`, `/dashboard/...` | GET, HEAD | path, query | `302` (later `301`) per AC-9 | none (before Clerk) | other methods: 404 |
| control `signup_status` | POST (signed, `marketing_secret`) | `clerk_user_id`, `request_id` | `_summary` plus `email`; `address` for every status but Failed | signed marketing call (spec 0014 AC-8) | signed 404 |

Shared server code, so the page and the routes can't drift:
- `callControl` in `src/lib/onboarding/control.ts` gains an optional timeout argument (default 15000 ms).
- The body of `status.ts` moves into `src/lib/onboarding/status.ts` as `readSignupStatus(locals, timeoutMs)`. It returns `none`, `unreachable` or the status object, and the API route answers byte for byte as today.
- `src/lib/onboarding/prefetch.ts` exports `isPrefetch(request)`, which is true for `HEAD` or a `Sec-Purpose` / `Purpose` header containing `prefetch`.
- The legacy map is an exported pure function `legacyTarget(pathname)` in `src/lib/redirects.ts` (it returns the new path or `null`), so it can be unit tested. `src/middleware.ts` calls it first in `onRequest`, next to the `/ingest/` early return.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| `/welcome` | which outcome to render | `readSignupStatus` (D1 row, then control `signup_status`), `isPrefetch`, the `open` query param, and the primary email's verification on `currentUser()` for the no sign up case |
| `/welcome/open` | redirect URL | control `owner_link` with the D1 row's `request_id`, 5 s timeout |
| Waiting card | first name | `currentUser().firstName`, else the primary email before the `@`, read once per render |
| Waiting and Ready cards | address | control `_summary.address` (Books Signup `subdomain` through `cloudflare.full_domain`), shown without `https://`; line left out when absent |
| Waiting card | current checklist step | `status`, plus `step` when Preparing (no step or an unknown one maps to **Making your account**) |
| Failed card | the step it stopped at | the server's `step` on the Failed row (`Owner`, `Domain`, or none for **Getting your site**) |
| Failed card | support email | `AppConfig.emails.supportEmail` |
| Docs links | titles and URLs | a new `welcomeDocs` list in `src/constants/` with the three entries in AC-5 |
| Retry line | whether to show it | `open=retry` together with status Ready |
| Island starting state | status, step, address, first name, `sawWaiting` | props from the `/welcome` server render |
| Legacy redirect | target path and code | `legacyTarget(pathname)` plus the request's query string; the code is a constant (`302`, later `301`) |
| Ready email | open URL | `${PUBLIC_SITE_URL}/welcome/open` in `notify.ts` |
| Nav and CTAs | label and href | `dashboardPath` renamed to `welcomePath = "/welcome"`, `dashboardLabel` renamed to `welcomeLabel = "Open your site"`, and a nav label `"Your site"`, in `src/constants/` |
| Start form success | where to go | `/welcome` (replaces `/dashboard` in `StartForm.tsx`) |
| `SiteStatus` open target | URL | `OPEN_URL = "/welcome/open"`; the `label()` helper is replaced by the checklist mapping |

**Key invariants**:
- From `/welcome` a browser follows at most two redirects (`/welcome` → `/welcome/open` → the site or `/welcome?open=retry`), and `/welcome?open=retry` never redirects. Together these mean no loop.
- Only `/welcome/open` calls `owner_link`, and only on a `GET` that is not a prefetch.
- The owner link URL is only ever in a `Location` header with `no-store` and `no-referrer`. It is never logged, rendered or stored.
- `failed_reason` never leaves the control site. The address is never shown for a Failed sign up.
- The legacy map runs before Clerk and changes only the path, so it can never send a visitor to another host.
- Identity comes from the Clerk session on the server, never from a query param or form field.

**Security model**: only the signed in Clerk user's own sign up is read, found by their Clerk user id as in spec 0014. The legacy redirect is public but leaks nothing (a fixed path map). Rendered pages are `private, no-store`, so no shared cache or back/forward cache keeps a name or address. `noindex` keeps `/welcome` out of search results. There is no new secret, and no compliance scope beyond spec 0014's (the owner's email and name, already handled there).

**Configuration required**: none. No new binding or secret, and the control site change needs no new setting. The Clerk instance's sign in URL must stay `/auth/sign-in` for `redirectToSignIn` (check in the Follow-up).

**Critical test scenarios**:
- Happy path: sign up in Clerk → land on `/welcome` → start form → submit `acme` → reload to the waiting card with "acme.rarebooks.cc" → the checklist moves through the steps → Ready → the password set page. Verifies **AC-2**, **AC-3**, **AC-5**, **AC-6**, **AC-8**
- Returning owner: a Ready user signs in on rarebooks.cc → `/welcome` → `/welcome/open` → their site, with no page rendered. Verifies **AC-2**, **AC-3**, **AC-4**
- Owner link down: `owner_link` answers 503 or takes over 5 s → `/welcome?open=retry` with the retry line, and no loop. Verifies **AC-4**
- Prefetch: `HEAD /welcome` and `GET /welcome/open` with `Sec-Purpose: prefetch` make no `owner_link` call. Verifies **AC-3**, **AC-4**
- Old Ready email: open `/dashboard/site/open?x=1` signed out → `302 /welcome/open?x=1` → sign in → back to `/welcome/open?x=1` → the site. Verifies **AC-1**, **AC-2**, **AC-9**
- Old links: unit tests on `legacyTarget` for each path in AC-9, plus `/dashboard/`, `/dashboardx` (no match) and `/Dashboard` (no match). Verifies **AC-9**
- Released sign up: a D1 row whose request was released → `/welcome` drops the row and shows the start form. Verifies **AC-3**
- Failed at the address step: a fresh load shows **Setting up your address** as Failed, with no address and no `failed_reason`. Verifies **AC-7**, **AC-8**
- Retry ignored: `/welcome?open=retry` on a waiting sign up shows the waiting card. Verifies **AC-3**
- Auth: signed out `GET /welcome` → Clerk sign in, then back to `/welcome`. Verifies **AC-1**
- No `/dashboard` left: the guard test in AC-10. Verifies **AC-10**

## Build plan

Tracer Bullet: the first slice is the whole thread (old link → `/welcome` → Ready user on their site) on today's card. Each later slice thickens it.

1. Shared server reads: the timeout argument on `callControl`, `readSignupStatus`, and `isPrefetch`. The API route keeps its answers byte for byte. Satisfies **AC-3**, **AC-4**
2. The thread:
   - Add `src/pages/welcome/index.astro` (the server outcome per AC-3: Ready → `302 /welcome/open`, else today's `SiteStatus` and `StartForm` with starting props).
   - Add `src/pages/welcome/open.ts` (moved from `site/open.ts`, with the 5 s timeout, the prefetch guard and the `?open=retry` fallback).
   - In the middleware, protect `/welcome(/.*)?`, and add `legacyTarget` in `src/lib/redirects.ts` with its unit test (`302`).
   - Set sign up to `forceRedirectUrl` and sign in to `fallbackRedirectUrl`, both `/welcome`.
   - Point `StartForm` success and `SiteStatus`'s `OPEN_URL` at the new routes, then remove `src/pages/dashboard/`.
   - Update `tests/marketing/load-speed.test.ts`: drop `PortalLayout` and `src/pages/dashboard/` from its skip list, add `src/layouts/WelcomeLayout.astro` and `src/pages/welcome/` (they load Turnstile and use `client:load`), repoint its Turnstile and tawk.to checks at `welcome/index.astro` and `WelcomeLayout.astro`, and drop the `dashboard/*.astro` reads.

   Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-6**, **AC-9**
3. Control site: `_summary` in `rarebooks_control/onboarding.py` returns `address` for every status but Failed. In `tests/test_onboarding.py`, update the two `assertNotIn("address", body)` checks (in the status test and in `test_one_sign_up_claims_a_pool_site_and_is_ready_at_its_address`) to expect it, and add a Failed case with no address but with its step. Then pass the address through in `readSignupStatus`. Ship the control change first: the extra field is harmless to the current Worker. Satisfies **AC-7**, **AC-8**
4. Reception shell: `src/layouts/WelcomeLayout.astro` (logo, `UserButton` with sign out to `/`, eager dashboard tawk.to, title, `noindex`, `global.css`), with `private, no-store` set by the page and one `currentUser()` passed down. All `/welcome` outcomes use it. Satisfies **AC-3**, **AC-11**
5. Cards: rework `SiteStatus.tsx` into the greeting, the "will be at" address with its fallback, the checklist (mapping, text states, `aria-current`), the docs links (new `welcomeDocs` constant), the failed step, and the Ready card with the retry line. Add the verify message's Refresh button. Satisfies **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**
6. Links and copy:
   - Rename `dashboardPath` and `dashboardLabel` (nav **Your site**, CTAs **Open your site**) and set `AppConfig.portalUrl`.
   - Change the `notify.ts` open URL and the Ready email line, and update `create-your-site.mdx`.
   - Update `tests/marketing/competitors.test.ts`, `pricing.test.ts` and `navigation.test.ts` for the new href and labels.
   - Add the no `/dashboard` guard test.

   Satisfies **AC-10**
7. Remove the old shell, the `ui/` files and hooks only it used, and the PortalLayout comments (AC-12 list), after a grep shows no importer. Run `npm run check`, `npm test` and `npm run build`. Satisfies **AC-12**
8. Staging run: deploy the control site, then the Worker. Do one sign up end to end, sign in as a Ready owner, open an old Ready email link signed out, force an `owner_link` failure once, and send a prefetch `HEAD`. Satisfies **AC-1** to **AC-12**
9. After one week live with no rollback, change the legacy redirect code from `302` to `301` (one constant and its test). Satisfies **AC-9**

## Migration plan

**Strategy**: big bang rename behind temporary redirects (small, one Worker deploy, no data moves), made permanent once proven.
**Phases**:
1. Deploy the control site with the earlier `address` (build plan step 3). The current Worker ignores it.
2. Deploy the Worker with `/welcome`, the `302` legacy map and the removed shell.
3. After one week with no rollback, switch the map to `301` (build plan step 9).

**Rollback**: during phase 2, revert the Worker commit, and add a reverse map to the old code (`/welcome` → `/dashboard`, `/welcome/open` → `/dashboard/site/open`), because Ready emails sent after the deploy carry `/welcome/open`. The `302`s are not cached, so no browser is stuck. After phase 3, a rollback needs that reverse map forever, because browsers keep a `301`. The control change needs no rollback.

**Risks**:
- Ready emails sent before the deploy depend on the `/dashboard/site/open` redirect forever, so the legacy map must never be removed.
- A Clerk instance setting (after sign up, after sign in or home URL in the Clerk dashboard) still set to `/dashboard` keeps working through the map, but should be updated (Follow-up).

## Consequences

**Positive**:
- One page, one job per state. A Ready owner never sees a page with nothing to do.
- A new user sees real progress and their address while they wait, which should cut "is it working?" support chats.
- About a dozen sidebar files leave the codebase.

**Negative / tradeoffs**:
- Every sign in by a Ready owner costs two signed control calls (the status, then `owner_link` on `/welcome/open`) and two redirects. While they have no password, each one mints a new password set link. That is fine at this volume, and each call is capped at 5 seconds.
- The browser's Back button from the site lands on `/welcome`, which sends the owner forward to the site again. It is accepted: there is nothing on `/welcome` for a Ready owner.
- There is no account page on the site any more. Account changes happen only in the `UserButton` menu on `/welcome`, which a Ready owner is always sent past, so in practice they reach it only at `/welcome?open=retry`. Their Books site is where they manage their account. Changing the Clerk email still does not reach Books (spec 0014 AC-1).
- The legacy map is permanent code. After the switch to `301`, a rollback needs the reverse map.
- Spec 0014 AC-4 loses "the address only at Ready". The address is the user's own chosen label, so nothing private leaks, but it is shown before the site answers there.

**Neutral**:
- `SiteStatus` keeps its polling and its live Ready jump. Its visuals, its starting state and its step mapping change.
- The code polls every 3 seconds for 5 minutes, while spec 0014 AC-4's text says 5 seconds for 2 minutes. This spec keeps the code's timing and records it.

## Follow-up

- [ ] In the Clerk dashboard, for both instances, check the after sign up, after sign in and home URLs, and set any `/dashboard` value to `/welcome`. Confirm the sign in URL is `/auth/sign-in`.
- [ ] Specs 0014 (`verify.md`, AC-1, AC-4 to AC-6 wording and the poll timing), 0016 and 0022 (`verify.md`) name `/dashboard` and `/dashboard/start`. `/sync` should flag them once this ships. They still work through the map.
- [ ] Root `AGENTS.md` in `rarebooks-site` says "`/dashboard(.*)` is protected in `src/middleware.ts`" and "the customer dashboard at `/dashboard`". `src/pages/api/AGENTS.md` may name the dashboard too. `/sync` should update them to `/welcome`.
- [ ] Sign up conversion tracking (scope feature 21, no spec yet): the renamed CTAs keep their `data-cta-location` attributes, so no event changes, but its spec should name the new labels.
