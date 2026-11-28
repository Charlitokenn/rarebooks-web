# 0027. Rationale: product analytics with PostHog

## Context

RareBooks has three running parts. The marketing site (`rarebooks-site`) already sends pageviews and sign up clicks to a PostHog EU project through its own `/ingest` proxy (spec 0022). The `/books` app (`rarebooks-web`) and the billing control site (`rarebooks_control`) send nothing. You can see who clicks Start free trial, but not whether they finish signing up, use the app, pay, or leave.

The `/books` app runs on many hosted shop sites, each its own Frappe site on a Frappe Cloud bench, some on custom domains. It shows a shop's financial records. Route paths and screen titles hold record names, and a Customer's name is a real person or business. The same app can also be installed by anyone outside RareBooks hosting, and those installs must never report to you. The control site runs billing, where a failed side call must never break a payment write or a signed answer (its `AGENTS.md` rules).

Shops are mostly in Tanzania, with EU visitors possible. There is no personal data in what we want to measure, so the main forces are: keep personal and business data out of PostHog, keep a PostHog outage from ever touching the product, keep operating cost near zero, and link the funnel across three systems that share no user id.

## Options considered

### Option 1: Browser only everywhere

Load posthog-js in `/books` and in the control site's desk, and track lifecycle moments from the operator's desk screens.

**Pros**:
- One library and one pattern for everything.

**Cons**:
- Billing events happen in webhooks and scheduled jobs, not in a browser, so most of the funnel would be missing.
- The desk is used only by you, so its events say nothing about customers.

### Option 2: Client events in /books, server lifecycle events from the control site (chosen)

`/books` sends pageviews by route template, generic doc events and errors from the browser. The control site sends the lifecycle from Python at the moments the code already marks, through one provider module, after commit. The marketing anonymous id is passed at sign up to join the funnel.

**Pros**:
- Each event comes from the place that knows it for sure: usage from the browser, money and lifecycle from the server.
- Fits the control site's one provider per outside service rule and its after commit discipline.
- No new infrastructure: no proxy to run, and no SDK thread in a Frappe worker.

**Cons**:
- Two code paths to keep up (TypeScript and Python).
- Ad blockers drop some `/books` events.

### Option 3: Server side events in /books too

Send `doc_submitted` and the rest from Python doc hooks in `frappe_books`, not the browser.

**Pros**:
- Exact counts, no ad blocker loss, and imports or API writes counted too.

**Cons**:
- Every save on every shop would add a job or an outgoing call on the shop's site.
- Pageviews and errors still need the browser, so it is two paths in one repo.
- You chose browser usage events.

### Option 4: Proxy /books events through rarebooks.cc/ingest

Reuse spec 0022's Worker proxy across origins.

**Pros**:
- Ad blockers see a first party looking host.

**Cons**:
- Needs CORS on `/ingest` and ties every shop's analytics to the marketing Worker.
- `/books` runs on custom domains, so the proxy is not first party there anyway.

## Rationale

Option 2 puts each event where the truth is. Payments are confirmed in `billing.confirm_*` after the provider answers, often from a webhook or a reconcile job; only server code sees that moment. Screen use is only visible in the browser. Sending from both, into the one project spec 0022 created, gives the full funnel without inventing a shared user id.

The privacy choices follow from what `/books` holds. Route templates, not paths, because `/edit/Customer/<name>` names a person. A keyed HMAC, not a plain hash, because a plain SHA256 of an email can be reversed by guessing likely emails. No company name in group properties, because the site name already tells you which shop it is. With nothing personal in PostHog, keeping history after removal is safe and keeps churn analysis possible. The opt out in Books System Settings, plus the privacy page line, is enough for analytics that carry no personal data, without a banner that would cut the data you get.

The control site path copies patterns already proven there. `providers/posthog.py` follows the ClickPesa, Frappe Cloud and Cloudflare provider rule, so tests patch one function. `enqueue_after_commit` means a rolled back payment sends nothing, and an outage only loses events. The date events (`trial_ended_unpaid`, `subscription_lapsed`) use a daily job by date, not a stored flag, because a lost event costs little and a schema change for analytics is not worth it. The 3 day lapse rule leaves room for PayPal renewals that land after `paid_until` (spec 0008 amendment on PayPal billing dates).

On groups: PostHog group analytics is a paid add on, and once on it bills every identified event in the project (confirmed in PostHog's group analytics docs through the PostHog connector). So every event also carries `site_key` as a plain property. Per shop breakdowns work for free today, and the group view lights up the day you turn the add on on, with no code change.

## References

**Project sources**:
- `rarebooks-web/docs/specs/0022-marketing-site-load-speed/index.md`: the existing PostHog EU project, init options and the no identify rule on marketing pages
- `rarebooks_control/AGENTS.md`: one provider module per outside service, credentials from site config never logged, `alerts.send_ops` and the after commit discipline
- `rarebooks-web/frontend/AGENTS.md`: lazy third party loading as in `pushNotifications.ts` and `supportChat.ts`
- `rarebooks-web/frappe_books/subscription/AGENTS.md`: a site counts as hosted only when `books_control_url` is set
- spec 0014 (self serve onboarding): `request_site` and the `marketing_secret` signature
- spec 0008: `billing.confirm_*`, the PayPal billing dates amendment

**Practices & standards**:
- Data minimisation (GDPR Article 5): send only what the question needs
- Keyed hashing (HMAC) for pseudonymous ids, not plain hashes of emails
- Transactional outbox style sending: side effects only after commit

**Links** (confirmed through the PostHog connector's docs search on 2026-11-28):
- Capture API (v1): https://posthog.com/docs/api/capture-v1
- Capture and batch API endpoints (legacy): https://posthog.com/docs/api/capture
- Group analytics, billing: https://posthog.com/docs/product-analytics/group-analytics
- Error tracking pricing, `capture_exceptions` options: https://posthog.com/docs/error-tracking/pricing
- Capture exceptions, `$exception_list` properties: https://posthog.com/docs/error-tracking/capture
- EU pricing: https://posthog.com/eu
