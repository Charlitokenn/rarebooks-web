# 0022. Marketing site load speed: rationale

The decision record behind [index.md](index.md).

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

## Rationale

The trace shows the slow LCP is main thread contention, not slow content: the text is in the HTML and only waits to be painted. So the fix is to remove work from the first seconds, not to add caching or a CDN (which would not move a render delay). The biggest pieces are things the team either no longer wants (the contact form, GTM) or needs only later (the chat, Turnstile), which makes removal cheaper and safer than tuning each one in place, as Option 1 would.

PostHog replaces GTM because the team chose it, but the way it loads is what makes it fit the target: the official snippet is under 2 KB and queues calls, so starting it on `load` keeps the first paint clean without losing the pageview, unlike gating it on interaction, which would drop visitors who leave quickly and skew feature 21's numbers. The `/ingest` proxy keeps ad blockers from hiding a share of visitors, and it is one small Worker route, which this stack already runs. EU cloud and a first party cookie match the visitors (East Africa and the UK) and what feature 21 needs (one visit's pages linked); the privacy page says so.

Clerk is left alone on purpose. Removing its browser bundle from marketing routes changes how sessions refresh (a server redirect instead of a client refresh) and depends on what the integration supports; that risk is only worth taking if the measured pages still fail once the larger, safer cuts are in.

