# 0023. Welcome page after sign up: rationale

## Context

Spec 0014 put the whole customer side of rarebooks.cc under `/dashboard`: the start form at `/dashboard/start`, the build status at `/dashboard`, the open route at `/dashboard/site/open`, and Clerk's account page at `/dashboard/settings`, all inside a sidebar shell (`PortalLayout`) inherited from the old desktop license portal. Once the license parts were retired (spec 0014 AC-7), the sidebar had one link left, and the "dashboard" name promised something the page doesn't do. The real dashboard lives on the customer's own Books site.

Behaviour has a gap too. Spec 0014 AC-4 sends a user who watched their site turn Ready straight to it, but a user who comes back later to a Ready site stays on the page and has to click **Set your password**. That button opens `/login` once a password exists, so the label is wrong from the second visit on. Sign in on rarebooks.cc lands there, so every returning owner pays an extra click on a page that has nothing else to offer.

The rename has hard constraints. Ready emails already sent carry `/dashboard/site/open` and can't be changed. The marketing nav, five call to action components and `AppConfig.portalUrl` link to `/dashboard`. The Clerk middleware protects `/dashboard(.*)`, so a signed out request to an old URL is sent to sign in before any page code runs. And the control site deliberately returned the address only at Ready (spec 0014 AC-4), so a waiting card that shows the address needs a contract change, not just UI.

If nothing is decided, `/develop` would have to choose redirect codes, the redirect mechanism, where the Ready decision runs, and how to avoid a loop when the owner link fails. Each of those is easy to get subtly wrong: a loop, a flash, a sign in bounce on an old email link.

## Options considered

### Option 1: Mirror the tree and redirect in the browser

Rename `/dashboard/*` one to one to `/welcome/*` (`/welcome`, `/welcome/start`, `/welcome/open`, `/welcome/settings`), keep `PortalLayout`, and let `SiteStatus` redirect a Ready user after its first poll. Old URLs are handled by Astro's `redirects` config.

**Pros**:
- Smallest diff. The page code and its tests barely change.
- No server side status read on the page.

**Cons**:
- A Ready owner sees `/welcome` render, then jump: a visible flash and a wasted round trip, and nothing happens without JavaScript.
- Astro's `redirects` run after the middleware, so a signed out visitor on an old email link goes through sign in at `/dashboard/...` first, and the order is hard to test.
- Keeps two pages (start and index) that already overlap (`SiteStatus` renders the start form on a 404), and a sidebar with one link.

### Option 2: One reception page, server side Ready redirect, middleware map (chosen)

`/welcome` holds the start form, waiting card and failed card, chosen on the server. A Ready user gets a `302` to `/welcome/open` before anything renders, and that route, the only one that asks for the owner link, sends them on to their site or falls back to `/welcome?open=retry`, which never redirects. A small path map in the middleware, run before Clerk, redirects every old `/dashboard` URL, temporarily at first and permanently once proven. A plain layout with `UserButton` replaces the sidebar shell.

**Pros**:
- No flash, works without JavaScript, and one rule for every Ready user (live or returning).
- Old links are handled in one tested function before auth, so an old email link costs one redirect and then the normal sign in.
- Fewer routes and about a dozen fewer files.

**Cons**:
- Two signed control calls on every `/welcome` load for a Ready owner.
- The loop guard (`?open=retry`) is a small rule the code must keep.
- Once the redirects turn permanent, browsers cache them, so a later rollback needs a reverse map.

### Option 3: Fix in place at `/dashboard`

Keep `/dashboard` and its routes, and only add the server side Ready redirect and the richer waiting card. No rename and no redirects.

**Pros**:
- No URL change, no redirect map, nothing for old links to break.
- Same behaviour win for Ready owners.

**Cons**:
- Doesn't do what scope feature 23 asks: the route change came from spec 0022's review, because "dashboard" names a page that isn't one.
- Keeps the sidebar shell and the settings page alive for no user need.

## Rationale

Option 2 is the only one that meets the scope row's three "done when" lines without a known failure mode. Option 1's browser redirect is the flash you'd see on every sign in, for the very users this feature exists to serve (returning owners). Its Astro `redirects` would bounce an old email link through sign in at the old URL. Option 3 is a reasonable fix in place, but it ignores the route change the engineer asked for.

The server side redirect costs a status read on `/welcome` and an `owner_link` call on `/welcome/open`. Both are signed calls the Worker already makes, so this adds no new dependency and no new failure mode, only latency, which a 5 second cap on the page's calls bounds. The first draft had `/welcome` call `owner_link` itself to save a hop. The cross check showed that duplicated the failure handling in two places. Keeping `owner_link` on one route (which the emails need anyway) is simpler, and one extra 302 is cheap. That route also refuses `HEAD` and prefetch requests, because a browser prefetch must never mint, and so burn, a password set link. The loop guard is a query param, not a cookie or stored state, because it must survive a Worker that keeps no session of its own.

The old link map starts as a `302` and becomes a `301` after a week live. The move is meant to be for good, but a `301` is cached by browsers forever, so a rollback in the first days would strand people. The temporary week is cheap insurance. Running the map in the middleware before Clerk, rather than in Astro's config, gives one place to test it and guarantees an old link never meets the sign in redirect on the old path. Sign in uses Clerk's fallback redirect, not a forced one, so a visitor sent to sign in from an old email link comes back to that link.

Returning the address while the site is built (AC-8) is a one line change in `_summary`, plus a pass through in the Worker. That beats a D1 column (rows written from a notice or a status read have no label) and browser storage (gone on another device). The address is the user's own chosen label, so showing it early leaks nothing. It is hidden on Failed because a failed site's label may be released. The failed step needs no change: the control site already keeps `step` on a Failed row.

Deleting the sidebar shell instead of keeping it for a future billing portal follows the reuse principle. Nothing uses it, and git keeps it if a portal ever needs it.
