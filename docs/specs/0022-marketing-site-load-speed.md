# 0022. Marketing site load speed

**Date**: 2026-11-26
**Status**: Proposed

Code lives in the `rarebooks-site` repo. Touches every page on `src/layouts/Layout.astro` (the marketing pages of specs 0017 to 0021, the legal pages and the 404). The customer dashboard (`PortalLayout.astro`) does not change.

## Summary

The marketing pages miss the speed target the last four specs set (the biggest text on screen should appear within 2.5 seconds on a phone), because every page loads about 2.8 MB of scripts it mostly doesn't need on first paint. This spec trims that load: the tawk.to chat waits for the visitor's first touch, the Contact us form is replaced by the chat, Google Tag Manager is replaced by a light PostHog setup, and the Turnstile script leaves pages that have no Turnstile form. Clerk's browser bundle is measured afterward and only changed in a later spec if the targets still fail.

## Context

Lighthouse mobile runs on 2026-11-26 measured LCP (largest contentful paint, the moment the biggest text or image shows) at 2.8 to 3.6 s on the homepage, 2.6 to 2.7 s on `/pricing` and 1.8 to 2.9 s on the comparison pages, with runs of one page swinging by a second. The LCP element is text that is already in the HTML: it has no load time, but about 2.3 s of render delay after first paint, because the main thread is busy. TBT (total blocking time, how long scripts keep the page from responding) was about 930 ms. Layout shift was fine (0.009).

A network trace of `/compare/xero` on a phone width shows what keeps the main thread busy, all of it loaded from the shared `Layout.astro` or components every page includes:

| Script | Size | Why it loads |
|---|---|---|
| `ContactUsForm` React island | 684 KB | `ContactUsModal` with `client:load` on every page, though the form sits in a closed dialog |
| React runtime (`client.js`) | 206 KB | Needed only by that island on marketing pages |
| Google tag served from `/163f/` | about 950 KB | Injected by Google Tag Manager (GA4 `G-RBJERDS7F6`) |
| Google Tag Manager | 348 KB | Inline loader in the `Layout.astro` head |
| Clerk browser bundle and UI | 470 KB | Injected by the `@clerk/astro` integration on every page; the marketing pages read the session only on the server (`isSignedIn(Astro.locals)`) |
| Cloudflare Turnstile | 85 KB | `Layout.astro`, though only `/dashboard` and `/dashboard/start` use it, and both already load it themselves |
| tawk.to | about 600 ms of main thread work | `TawkWidget` in `Layout.astro`, loaded on every page view |

The site is moving off Google Tag Manager to PostHog in any case, and the team wants the Contact us form replaced by the support chat. The comparison pages spec (0021, AC-16) is blocked on this: its Checks milestone cannot close until LCP passes. Not deciding leaves every marketing page slow on the phones most visitors in East Africa use, and leaves analytics on a tool the team is leaving.

## Requirements

**User stories**:
- As a visitor on a phone, I want the page's headline and text to appear quickly, so that I don't give up before reading.
- As a visitor with a question, I want Contact us to open a chat with a person, so that I get an answer without filling a form and waiting for email.
- As the site owner, I want pageviews and sign up button clicks recorded in PostHog, so that I can compare conversion before and after the redesign (feature 21).
- As the site owner, I want the speed gain guarded, so that an eagerly loaded script can't slip back in unnoticed.

**Acceptance criteria**:
- **AC-1**: Speed targets. On every public marketing page that uses `Layout.astro` (`/`, `/pricing`, `/compare`, one `/compare/<slug>`, `/alternatives`, one `/alternatives/<slug>`, `/privacy`, `/terms` and the 404), the median of 3 Lighthouse mobile runs against the deployed site shows LCP ≤ 2.5 s, TBT ≤ 200 ms and CLS ≤ 0.1, and Accessibility stays 100. Results per page are recorded in `verify.md`. The other pages on `Layout.astro` (`/auth/sign-in`, `/auth/sign-up` and the unindexed `/design-system`) get every change in this spec but are not measured: the auth pages are mostly Clerk's own UI.
- **AC-2**: Chat on first interaction. On a `Layout.astro` page, no request goes to `embed.tawk.to` until the first of: a `scroll`, `pointerdown`, `keydown` or `touchstart` event, or 10 seconds after the window `load` event. Then the script loads once per page view, with the same Secure Mode visitor and login hashes as today, and the bubble shows as it does now. `PortalLayout.astro` keeps loading tawk.to at once, unchanged.
- **AC-3**: Contact us opens the chat. Every Contact us control on the marketing pages (today the `data-open-modal="contact-us-modal"` controls in `HomePricingTeaser`, `HomeFaq`, `PricingSetup` and `PricingFaq`; the `HomeFaq` one is an HTML string inside an `MkFaq` answer) is an `<a href="mailto:{supportEmail}">` carrying `data-open-chat` and keeping its `data-cta-location`.
  - Only a plain left click (no Ctrl, Cmd, Shift, Alt, not a middle click) is intercepted; any other click opens email as a normal link. Without JavaScript, the link opens email.
  - On an intercepted click, `rbOpenChat` loads tawk.to if it isn't loaded, and calls `Tawk_API.maximize()` once tawk.to is ready (a call made before then is held until `onLoad`). It wraps the existing `Tawk_API.onLoad` (the Secure Mode login), never replaces it.
  - "Opened" means `Tawk_API.onChatMaximized` fired, or `Tawk_API.isChatMaximized()` is true when checked (a click while the chat is already open counts as opened at once). Opening clears the 8 second timer.
  - At DOM ready, an empty `<span role="status" aria-live="polite">` is inserted right after every `[data-open-chat]` control. If the chat hasn't opened 8 seconds after the click, that span is filled with "Chat could not load. Write to {supportEmail}." with the address as a plain `mailto:` link (no `data-open-chat`). A later click clears the message and tries again.
- **AC-4**: Contact form removed. `src/components/ContactUsModal.astro`, `src/components/ContactUsForm.tsx`, `src/pages/api/contact-us.ts` and the enquiry email template in `src/components/templates/` are deleted, and every layout and page drops its `<ContactUsModal>` (today `CompareLayout.astro`, `AlternativesLayout.astro`, `index.astro`, `pricing.astro`, `compare/index.astro` and `alternatives/index.astro`), so nothing in `src/` references them. `POST /api/contact-us` answers 404. Any helper, constant or package used only by them is removed too.
- **AC-5**: Google Tag Manager removed. `Layout.astro` has no GTM loader, no `noscript` GTM iframe and no `dataLayer` code. That includes the dead handlers for `purchase_interest`, `payment_confirmation_started`, `payment_checkout_started` and `software_download`, and the `desktop-payment-modal` branch (nothing in `src/` uses them; one called `Tawk_API.maximize()` directly). The generic `data-open-modal` handler stays, since the nav menu and the demo dialog use it. A page load makes no request to `googletagmanager.com`, `google-analytics.com` or `/163f/`.
- **AC-6**: PostHog events. When a PostHog key is configured, every `Layout.astro` page records one `$pageview`. A click on a link whose `href` equals `AppConfig.urls.signUpUrl` (passed into the inline script with `define:vars`, not hardcoded) and that carries `data-cta-location` records `trial_interest` with `cta_location` and `plan_name` (the same values the GTM event carried, `plan_name` null when absent). A click on a `data-open-chat` control records `contact_click` with `cta_location`. Every capture checks that `window.posthog` exists first. A click that navigates away before PostHog's library has loaded may lose its event; this is accepted.
- **AC-7**: PostHog loads after the page. `Layout.astro` carries PostHog's official inline snippet (under 2 KB, it queues calls), and `posthog.init` runs on the window `load` event, so the library is requested only after `load`. Events called before that, the pageview included, are queued and sent once it loads (except as noted in AC-6). The init options are exactly: `api_host: "/ingest"`, `ui_host: "https://eu.posthog.com"`, `capture_pageview: true`, `autocapture: false`, `disable_session_recording: true`, `disable_surveys: true`, `advanced_disable_flags: true` (no feature flag calls), `person_profiles: "identified_only"`, `persistence: "cookie"`. No visitor is identified (no `posthog.identify`).
- **AC-8**: First party proxy. `src/pages/ingest/[...path].ts` (`prerender = false`, handlers for GET, POST and OPTIONS) forwards `/ingest/static/*` and `/ingest/array/*` to `https://eu-assets.i.posthog.com/`, and every other `/ingest/*` path to `https://eu.i.posthog.com/`, keeping the method, path, query string and body. It passes only the `content-type`, `content-encoding`, `accept` and `user-agent` request headers (never `cookie`, `authorization` or any `cf-*` header), sets `X-Forwarded-For` from `cf-connecting-ip`, and forwards to no other host. Responses pass through with their status, body, `content-type` and `cache-control`. When PostHog can't be reached, it answers 502 with an empty body. Before building, the paths are checked against PostHog's current proxy guide and the paths the pinned snippet actually calls; any other assets path it uses joins the assets list. `src/middleware.ts` lets `/ingest/` requests skip `clerkMiddleware` (and the cache header it adds), so analytics calls never pay for a session check or get a Clerk redirect.
- **AC-9**: Failure is silent. The PostHog key comes from the `PUBLIC_POSTHOG_KEY` variable (set in production only), so local dev and previews have none: then the snippet is not rendered and no `/ingest` request is made. If PostHog or tawk.to is blocked or down, the page, its links and the sign up buttons keep working, and nothing shows an error to the visitor (beyond AC-3's message).
- **AC-10**: Turnstile only where used. `Layout.astro` no longer loads `challenges.cloudflare.com/turnstile/v0/api.js` or preconnects to it. `/dashboard` and `/dashboard/start` still load it themselves, and a sign up on `/dashboard/start` still passes Turnstile.
- **AC-11**: Privacy page. The drafted `/privacy` page names PostHog in place of Google Tag Manager: "PostHog (EU cloud): for analytics about the pages you visit on rarebooks.cc and the sign up and contact buttons you click. It sets a cookie to link the pages of one visit." The tawk.to line stays.
- **AC-12**: Guard test. A node test scans the `.astro`, `.ts`, `.tsx` and `.mdx` files in `src/layouts/` (except `PortalLayout.astro`), `src/components/marketing/` and `src/pages/` (except `src/pages/dashboard/` and `src/pages/api/`), and fails when any contains `googletagmanager`, `turnstile/v0/api.js`, `ContactUs` or `client:load`, or when `Layout.astro` renders `TawkWidget` without `load="interaction"`. It also checks that `PortalLayout.astro` renders `TawkWidget` without that prop, and that `src/pages/dashboard/index.astro` and `src/pages/dashboard/start.astro` still contain the Turnstile script. (The comment in `MkNav.astro` that names `ContactUsModal` is reworded.)
- **AC-13**: Clerk checkpoint. After AC-2 to AC-10 are deployed, AC-1 is measured. If any page still misses a target, `verify.md` records that page's numbers, the main thread time of `clerk.browser.js` and `ui.browser.js`, and the page's server response time (which includes `TawkWidget`'s `Astro.locals.currentUser()` call for signed in visitors), and a follow-up spec is opened on keeping Clerk's browser bundle off marketing pages. This spec does not change Clerk, and `TawkWidget` keeps its server call, since Secure Mode needs it.
- **AC-14**: No regressions. On the pages in AC-1, axe reports no violations, including with the AC-3 failure message shown; every link and button is reachable by keyboard with a visible focus ring; and `npm test` and `npm run check` pass with no new errors.

## Options considered

### Option 1: Load the heavy scripts later, keep the tools (defer in place)

Keep tawk.to, the contact form and GTM, but load each later: tawk.to on first interaction, the form island with `client:idle` or on dialog open, GTM after `load`.

**Pros**:
- Smallest behaviour change; analytics history in GA4 carries on.
- Each change is a few lines.

**Cons**:
- GTM still pulls about 1.3 MB of Google tag code after load, which keeps TBT high on slow phones even when deferred.
- Keeps a contact form, an email endpoint and React on every page that the team no longer wants.
- Spends work on GTM, which the team is leaving for PostHog anyway.

### Option 2: Defer the chat, replace the form with the chat, replace GTM with a light PostHog setup, drop Turnstile from Layout (chosen)

As Option 1 for the chat, but the Contact us form is removed and its buttons open the chat; GTM is replaced by PostHog's small queueing snippet started after `load`, through a first party proxy; Turnstile leaves `Layout.astro`. Clerk is measured afterward.

**Pros**:
- Removes about 2.2 MB of the 2.8 MB from first paint (form and React, GTM and its tag, Turnstile), and moves tawk.to out of the LCP window.
- One support channel (the chat) instead of two; one less public endpoint to defend.
- Lands the analytics move the team already decided on, with no gap in pageview and click tracking.

**Cons**:
- Visitors who never touch the page before leaving never load the chat bubble.
- GA4 history ends; PostHog starts from zero.
- A visitor with tawk.to blocked can no longer leave a message on the site; they get the support email instead.

### Option 3: Move third party scripts to a web worker (Partytown)

Run GTM and similar tags off the main thread with Astro's Partytown integration, leaving the rest as is.

**Pros**:
- Keeps every tool and its timing; no product change.

**Cons**:
- Does nothing for the contact form island, React or Clerk, which are first party.
- GTM, gtag and tawk.to have known problems in Partytown (cookies, `dataLayer` forwarding, iframes), adding a dependency that is hard to debug.

### Option 4: Remove the chat and analytics from marketing pages entirely

**Pros**:
- Fastest possible pages.

**Cons**:
- No support chat for visitors deciding whether to buy, and no measurement for feature 21's conversion work.

## Decision

**Chosen option**: Option 2: defer the chat to first interaction, replace the Contact us form with the chat, replace GTM with PostHog loaded after `load` through a first party proxy, and take Turnstile out of `Layout.astro`; measure Clerk afterward.

The marketing pages load only what first paint needs; the chat, analytics and sign up protection arrive when, and where, they are used.

**Implementation skills**: `workers-best-practices` (`cloudflare/skills`, `.agents/skills/workers-best-practices/`, the `/ingest` proxy route on the Worker) · `turnstile-spin` (`cloudflare/skills`, `.agents/skills/turnstile-spin/`, keeping Turnstile on the pages that use it) · `web-perf` (the Lighthouse runs) · `clerk-astro-patterns` (`clerk/skills`, `.agents/skills/clerk-astro-patterns/`, for the AC-13 checkpoint only)

## Rationale

The trace shows the slow LCP is main thread contention, not slow content: the text is in the HTML and only waits to be painted. So the fix is to remove work from the first seconds, not to add caching or a CDN (which would not move a render delay). The biggest pieces are things the team either no longer wants (the contact form, GTM) or needs only later (the chat, Turnstile), which makes removal cheaper and safer than tuning each one in place, as Option 1 would.

PostHog replaces GTM because the team chose it, but the way it loads is what makes it fit the target: the official snippet is under 2 KB and queues calls, so starting it on `load` keeps the first paint clean without losing the pageview, unlike gating it on interaction, which would drop visitors who leave quickly and skew feature 21's numbers. The `/ingest` proxy keeps ad blockers from hiding a share of visitors, and it is one small Worker route, which this stack already runs. EU cloud and a first party cookie match the visitors (East Africa and the UK) and what feature 21 needs (one visit's pages linked); the privacy page says so.

Clerk is left alone on purpose. Removing its browser bundle from marketing routes changes how sessions refresh (a server redirect instead of a client refresh) and depends on what the integration supports; that risk is only worth taking if the measured pages still fail once the larger, safer cuts are in.

## Feature design

**Data model sketch**: none. No storage, no schema.

**State transitions**: the chat on a marketing page: `not loaded` → (first interaction, 10 s after `load`, or a Contact us click) → `loading` → `ready`. A Contact us click in `loading` waits for `ready`, then maximizes; if not open after 8 s, it shows the AC-3 message and stays clickable.

**API surface**:

| Route | Method | Inputs | Outputs | Auth | Errors |
|---|---|---|---|---|---|
| `/ingest/static/*`, `/ingest/array/*` | GET, OPTIONS | path, query | the PostHog asset, passed through from `eu-assets.i.posthog.com` | public | upstream status passed through; 502, empty body, when unreachable |
| `/ingest/*` (other paths) | GET, POST, OPTIONS | path, query, body, the four allowed headers | PostHog's response, passed through from `eu.i.posthog.com` | public | upstream status passed through; 502, empty body, when unreachable |
| `/api/contact-us` | POST | none | 404 (route deleted) | n/a | 404 |

Client side, in `Layout.astro`:
- `TawkWidget` gains `load?: "eager" | "interaction"` (default `eager`, so `PortalLayout.astro` is unchanged); `Layout.astro` passes `interaction`.
- A small inline script exposes `window.rbOpenChat(control)` used by the `data-open-chat` handler: it loads tawk.to if needed, wraps `Tawk_API.onLoad` and sets `onChatMaximized`, maximizes once ready, records `contact_click`, and starts the 8 s fallback timer (AC-3).
- The existing click handler in `Layout.astro` sends `trial_interest` to PostHog instead of `dataLayer`; the other `dataLayer` handlers are deleted (AC-5).
- `src/middleware.ts` returns early for `/ingest/` paths before `clerkMiddleware` (AC-8).

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| Render the PostHog snippet | project key | `PUBLIC_POSTHOG_KEY` (a public `phc_` key from the PostHog EU project), read with `import { env } from "cloudflare:workers"`, declared in `wrangler.toml` and `worker-configuration.d.ts`, set in production only; empty or missing means off (AC-9) |
| Init PostHog | options | the fixed list in AC-7 |
| Proxy upstream | host | `/ingest/static/*` and `/ingest/array/*` → `eu-assets.i.posthog.com`; else `eu.i.posthog.com` (fixed in the route, checked against PostHog's proxy guide at build) |
| Proxy request headers | headers sent upstream | only `content-type`, `content-encoding`, `accept`, `user-agent` from the request, plus `X-Forwarded-For` |
| Proxy `X-Forwarded-For` | visitor IP | `cf-connecting-ip` request header |
| `trial_interest` | which links count | `href` equal to `AppConfig.urls.signUpUrl`, passed in with `define:vars` |
| `trial_interest` | `cta_location`, `plan_name` | the clicked link's `data-cta-location` and `data-plan-name` (as the GTM event used) |
| AC-3 "opened" | chat state | `Tawk_API.onChatMaximized`, or `Tawk_API.isChatMaximized()` |
| `contact_click` | `cta_location` | the clicked control's `data-cta-location` |
| AC-3 fallback message | support email | `AppConfig.emails.supportEmail` |
| Contact link `href` | mailto address | `AppConfig.emails.supportEmail` |
| Secure Mode hashes | `hash`, login hash | unchanged: `TawkWidget`'s server side HMAC with `TAWK_API_KEY` |
| Chat load trigger | timing | first `scroll`, `pointerdown`, `keydown` or `touchstart`, or 10 s after `load` (AC-2) |
| Fallback delay | 8 s | fixed in the inline script (AC-3) |
| Speed results | LCP, TBT, CLS | Lighthouse mobile, median of 3 runs on the deployed site (AC-1) |

**Key invariants**:
- No third party script (tawk.to, PostHog's library) starts before the window `load` event or the visitor's first interaction on a marketing page.
- No `client:load` island on a marketing page.
- The proxy forwards only to the two PostHog EU hosts and never forwards the visitor's cookies.
- PostHog never receives a name, email or user id from the marketing pages.
- The dashboard (`PortalLayout.astro`) behaves exactly as before.

**Security model**: public pages. The proxy is an open pass through, but only to two fixed PostHog hosts, with cookies stripped, so it can't be used to reach other sites or leak the Clerk session. PostHog data: page URLs, referrer, the two named events and their `cta_location`, and PostHog's own anonymous id cookie; the privacy page names it (AC-11). Deleting `/api/contact-us` removes an unauthenticated endpoint that sent email. The tawk.to Secure Mode keys stay server side as today.

**Configuration required**:
- `PUBLIC_POSTHOG_KEY`: the PostHog project API key (public, `phc_…`), from the PostHog EU project's settings. Not a secret (it ships in the page), so it is a plain `[vars]` entry, set for production only, left empty for local dev and previews. Owed from you before phase 3.

**Critical test scenarios**:
- Phone load: open `/` at 390 px, wait 3 s without touching: no request to `embed.tawk.to`, `googletagmanager.com`, `/163f/`, `challenges.cloudflare.com` or a `ContactUsForm` chunk; scroll once: tawk.to loads, verifies **AC-2**, **AC-4**, **AC-5**, **AC-10**
- Contact us: click "Talk to us" in the pricing FAQ before scrolling: the chat opens; block `embed.tawk.to` and click again: after 8 s the support email message appears and is announced, verifies **AC-3**
- PostHog: load `/compare/xero`, click Start free trial: `/ingest` receives a `$pageview` then `trial_interest` with `cta_location=compare_page_header`; `array.js` is requested only after `load`, verifies **AC-6**, **AC-7**, **AC-8**
- No key: run with an empty key: no snippet in the HTML, no `/ingest` requests, no console errors, verifies **AC-9**
- Proxy: an event POST to `/ingest/e/` (or the capture path the pinned library uses) with a cookie reaches `eu.i.posthog.com` without the cookie, and not through Clerk; `/ingest/static/array.js` comes from `eu-assets.i.posthog.com`; with PostHog unreachable the route answers 502, verifies **AC-8**
- Modifier click: Ctrl click on a Contact us link opens email, not the chat, verifies **AC-3**
- Sign up still works: complete `/dashboard/start` with Turnstile, verifies **AC-10**
- Guard: put `client:load` back on a marketing component in a scratch copy and `npm test` fails, verifies **AC-12**
- Speed: Lighthouse mobile, 3 runs per page in AC-1 on the deployed site, verifies **AC-1**, then the Clerk checkpoint, verifies **AC-13**

## Build plan

Tracer Bullet: one change goes end to end on one page first (the chat on first interaction, measured on the homepage), then the rest follow, each measured.

1. Baseline: run Lighthouse mobile 3 times on each AC-1 page on the deployed site and record the medians in `verify.md`, so every later step has a before number, satisfies **AC-1**
2. The thread: `TawkWidget` `load` prop with the interaction trigger, used by `Layout.astro`; the guard test's TawkWidget checks; deploy and measure `/`, satisfies **AC-2**, **AC-12**
3. Contact us opens the chat: `data-open-chat` mailto links in the four components, `rbOpenChat` with the `onLoad` wrapper, `onChatMaximized`, the 8 s fallback and the status spans; delete `ContactUsModal`, `ContactUsForm`, `/api/contact-us` and the enquiry template, and drop every `<ContactUsModal>` from the two layouts and four pages; reword the `MkNav` comment; guard test for `ContactUs` and `client:load`, satisfies **AC-3**, **AC-4**, **AC-12**
4. Analytics: remove GTM, `noscript` and every `dataLayer` handler (keeping the generic `data-open-modal` one); add `PUBLIC_POSTHOG_KEY` to `wrangler.toml` and `worker-configuration.d.ts`; check PostHog's current proxy guide and the snippet's paths; the snippet with the AC-7 options and init on `load`, the `/ingest/[...path].ts` proxy, the `/ingest/` early return in `middleware.ts`, and the `trial_interest` and `contact_click` captures; guard test for `googletagmanager`, satisfies **AC-5**, **AC-6**, **AC-7**, **AC-8**, **AC-9**, **AC-12**
5. Turnstile out of `Layout.astro`, with a sign up on `/dashboard/start` checked; guard test for the Turnstile script, satisfies **AC-10**, **AC-12**
6. Privacy page wording, satisfies **AC-11**
7. Deploy, then the AC-1 runs on every page, axe, keyboard, `npm test` and `npm run check`, recorded in `verify.md`; then the Clerk checkpoint, satisfies **AC-1**, **AC-13**, **AC-14**

## Migration plan

**Strategy**: feature by feature deploys, each one revertable on its own.
**Phases**:
1. Chat on interaction (step 2): deploy, measure.
2. Contact form to chat (step 3): deploy. The old form and endpoint go in the same commit as the new buttons.
3. GTM to PostHog (step 4): deploy once `PUBLIC_POSTHOG_KEY` is set in production and the PostHog EU project exists. Check the first events arrive in PostHog the same day.
4. Turnstile and privacy (steps 5 and 6): deploy, then the full measurement (step 7).
**Rollback**: revert the phase's commit. Phase 3 restores GTM by revert; GA4 data from the gap is not recoverable.
**Risks**: a gap in analytics if phase 3 ships without the key (AC-9 keeps the site working, but nothing is recorded); visitors who block tawk.to lose the form and get the email address instead; Lighthouse lab numbers swing by a second run to run, which is why AC-1 uses the median of 3.

## Consequences

**Positive**:
- About 2.2 MB of script leaves first paint on every marketing page, and tawk.to moves out of the LCP window.
- One support channel for visitors; one fewer public endpoint that sends email.
- Analytics move to PostHog with pageviews and the same click events, ready for feature 21.
- A test keeps eager scripts from creeping back.

**Negative / tradeoffs**:
- GA4 history ends; PostHog trends start from the switch date.
- A visitor who leaves without touching the page never sees the chat bubble.
- A visitor with tawk.to blocked can't send a message from the site; they get the support email address.
- The site now runs a small proxy route that must keep pace with PostHog's host names.
- Clerk's 470 KB stays for now; if the targets still fail, a riskier auth change follows.

**Neutral**:
- Spec 0021's Checks milestone (AC-16) closes on this spec's AC-1 results.
- `PortalLayout.astro` keeps its eager chat.

## Follow-up

- [ ] Supply the PostHog EU project key for `PUBLIC_POSTHOG_KEY` (production) before phase 3.
- [ ] If AC-13 finds a page still failing, run `/architect keep Clerk's browser bundle off marketing pages`.
- [ ] Rename `/dashboard` to `/welcome`: a reception page while a new site is created, which sends a signed in user whose site is ready straight to their site. It changes spec 0014's sign up flow, so it needs its own spec: `/architect welcome page after sign up`.
- [ ] Feature 21 (sign up conversion tracking) now builds on PostHog: its events are `trial_interest` and `contact_click` with the `cta_location` values listed in specs 0019 to 0021.
- [ ] `ContactUsModal` was the last user of the old purple tokens on marketing pages; check whether any old token classes remain unused in `global.css` once it is gone.
