# 0014. Self serve onboarding: rationale

## Context

> ⚠️ Premise note: retiring the desktop license key trial on the same day hosted sign up opens leaves no way in if the pool, the control site or Frappe Cloud is down. The failure mode is quiet: visitors just leave. The build plan therefore retires the desktop parts last (task 9), only after a sign up has gone end to end on staging and live. You chose to retire it completely, and that holds; the order is the only safeguard.

Today a hosted Books site exists only after you create it on Frappe Cloud, register it on the control site (spec 0010 AC-10) and give it a subdomain (spec 0012). Every step is yours. The marketing site (`rarebooks-site`, Astro on Cloudflare Workers with Clerk, D1, Resend) offers only a desktop license key trial through Keymint, which no longer fits a hosted product.

The forces: building a Frappe Cloud site takes several minutes and is the step most likely to fail; a visitor waiting on a spinner leaves. The control site already owns every Frappe Cloud and Cloudflare call, with careful guards (commit then archive, the spec 0013 archive proof, no redirects), and those guards must keep holding when nobody is watching. Books starts its trial clock at install and treats a hosted site with no trial start as locked. Any public entry that creates real servers is a target for scripts, so limits are needed from day one.

The marketing site is on another platform (a Worker) with its own identity provider (Clerk). It needs a narrow, verifiable way to ask the control site for a site and to learn when it is ready, without holding any Frappe Cloud, Cloudflare or registry power itself.

Not deciding leaves every customer gated on you, which caps growth at your free hours.

## Options considered

### Option 1: Create a new site on each sign up

The control site calls `press.api.site.new` the moment a visitor submits, waits for it, registers it, pings it, then runs the domain steps.

**Pros**:
- Nothing idle; no pool states.
- Every site starts on the newest Books version.

**Cons**:
- The visitor waits 10 to 20 minutes through the slowest, least reliable step.
- A failed build happens in front of a customer.
- The trial clock problem still needs solving if config fails and is retried later.

### Option 2: Warm pool of prebuilt sites (chosen)

The control site keeps `pool_size` sites already created, registered and pinged, marked with `pool_status`. A sign up claims one, the Books site makes the owner and restarts the trial, and the existing domain job gives it its address.

**Pros**:
- The visitor waits only for the domain and certificate (a few minutes).
- Build failures happen off stage and cost no customer anything.
- Reuses registration, ping, domain and archive code almost unchanged.

**Cons**:
- Idle sites cost server resources.
- More states (Building, Ready, Claimed) and skip rules in the removal round and pushes.
- Pool sites need the Books release like every other site.

### Option 3: Frappe Cloud's own product trial signup

Frappe Cloud offers a SaaS style signup with standby sites of its own.

**Pros**:
- Least code for the pool itself.

**Cons**:
- Each signup becomes a Frappe Cloud team, outside your single team model, so the control site's guards (one bench group, one team key) no longer describe where sites live.
- Signup happens on Frappe Cloud's pages, not your marketing site with Clerk.
- Less control over the trial, the subdomain rules and the archive proof.

### Option 4: Pool with fallback to create on demand

Like Option 2, but an empty pool creates a site for that visitor directly.

**Pros**:
- Never a queue.

**Cons**:
- Two creation paths to test and keep apart; the chosen design already starts a build at once when the pool is empty, which gives nearly the same result through one path.

## Rationale

The slowest and least reliable step is building a site, so the design moves it before anyone waits. That is the force that rules out Option 1. Option 3 would give away the property spec 0010 was built on: one team key, one bench group, and a control site that can only archive a registered site there. Option 4 adds a second creation path for a rare case, and queuing with an immediate build covers it.

Signing marketing calls with spec 0005's HMAC scheme, using a secret of its own, keeps one signing rule across three repos with shared vectors, signed answers both ways and the existing failure alert. A Frappe API key would act as a desk user and send unsigned answers. Clerk stays the identity, since it already verifies emails on the marketing site; the control site trusts only the Worker, and the Worker trusts only Clerk's server side session.

Small calls I made with the full design in view (runner up in brackets):
- Pool sites are rows on Books Hosted Site with `pool_status`, so registration, ping, domain and archive code run unchanged (a separate pool doctype, which would need a second registry).
- A discard is a Books Removal Case of kind Discard that goes straight to Dropping, so it gets spec 0013's archive proof and the domain cleanup for free. It skips the export and fresh report checks, which assume a trial that ran its course, and adds a fail closed guard checked twice: never discard a site whose owner has logged in (a separate archive path, which would duplicate the most dangerous code in the repo).
- `claim_site` sets the time zone before it restarts the trial, so day 1 can't move when GetStarted runs (storing a date instead, which would change the clock's rules).
- The signed notice stays (the Worker polling the control site on a Cron Trigger), because the Ready email must reach someone who closed the page, and the retry state is small.
- Discards have their own `discard_mode` (default `dry_run`), not the removal `mode`, so you can turn discards on in live before removal and failed builds never pile up while removal stays off (sharing the removal `mode`, which would strand failed sites while removal is off).
- The password set link is minted on each click behind Clerk sign in, so a forwarded email hands over nothing (a 7 day link in the email).
- The control site tells the Worker about Ready and Failed with a signed notice, retried for 24 hours (a Worker Cron Trigger polling the control site).
- The trial restarts at claim through a new `state.py` writer, keeping the fail closed rule for a hosted site with no trial start (skipping `start_trial` at install for pool sites).
- `claim_site`, `owner_link` and `claim_report` are in `ALLOWED_METHODS`, since a pool site older than 30 days reads as locked until it is claimed.
- The company name is stored as a global default that GetStarted reads, since Books Subscription only takes writes from `state.py` (a field on Books Subscription).
- A Discard cancels the claimed site's open Trial or Lapsed case unless it is Dropping, even one paused by hand (leaving a paused case alone, which would strand the site until someone acts). The 5 minute sweep repairs a Failed request with no Discard case (a one off patch, which would not catch a later refusal). A Claimed site gets no Trial or Lapsed case until its request is Ready, which removes the cause; the cancel stays as the repair for cases that exist already and for a race. Added 2026-11-23 after the first staging sign up failed and its site was never discarded, with fixes from a cross check on another model.
- The IP and check limits use KV counters keyed by the hour or minute (the Workers rate limiting binding, which only counts over 10 or 60 seconds and so can't express 3 an hour).

## Evidence: what exists today

- `rarebooks_control/registry.py`: `register_site` (Billing Manager only), `send_config`, the 5 minute ping, `check_subdomain`, and the five domain steps with the 2 hour rule.
- `rarebooks_control/providers/frappe_cloud.py`: `get_site`, `update_config`, `archive` and the domain methods; no site creation yet.
- `frappe_books/setup.py`: `bootstrap` calls `start_trial` at install.
- `rarebooks-site`: Clerk middleware protects `/dashboard`; `/api/license` and `/api/create-license` create Keymint keys, a Clerk user with a generated password, a D1 `trials` row and a Resend email.
