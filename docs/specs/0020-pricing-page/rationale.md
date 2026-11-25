# 0020. Pricing page: rationale

The decision record behind [index.md](index.md).

## Context

The redesigned homepage (spec 0019) has a pricing teaser: one price, four feature points and Start free trial. The nav and footer Pricing links point at its `/#pricing` anchor. The full pricing that used to sit there (the old `Pricing.astro`, deleted in spec 0019) showed the plan with the setup offers in Tanzania, and Yearly and Monthly cards abroad. Nothing in the new style replaces it yet, so a visitor who wants to compare billing periods, see what setup costs or find out what happens after the trial has nowhere to go.

The forces: RareBooks sells one hosted plan at two currencies and three prices (TZS 300,000 yearly through ClickPesa; $39 monthly or $399 yearly through PayPal), picked from the visitor's country. The prices live in `src/constants/pricing.ts` and must match the control site's Books Plan rows. The site is one Astro app on a Cloudflare Worker that renders the marketing pages per request, because they vary by country and by Clerk sign in state. Mobile Core Web Vitals and WCAG 2.2 AA are already the bar for every new page (specs 0017 to 0019). Old `/#pricing` links exist in the wild and must keep landing on pricing.

Search matters: people look for the price of accounting software before they try it, and the homepage can't rank for that query and for the product at the same time. Google crawls mostly from the United States, so a country based page shows crawlers only the USD version.

The billing promises the page makes have to match what specs 0005, 0007 and 0008 actually do: the trial clock (free to day 21, read only from day 26, removed on day 30), the 7 day grace after a paid period, removal 60 days after that, ClickPesa yearly with no auto renewal, PayPal with cancellation in PayPal, and no self serve plan switch or refund policy.

## Options considered

### Option 1: A server rendered `/pricing` page, teaser kept

A new `/pricing` route rendered per request, like the homepage, choosing the Tanzania or abroad version from `cf-ipcountry` and the buttons from the Clerk session. The homepage teaser stays as the `/#pricing` landing spot and links to the page. Fixed JSON-LD lists all three prices for crawlers.

**Pros**:
- Its own URL to rank and share, with the price shown in search results through the JSON-LD.
- It follows the homepage's pattern exactly (`isTanzania`, `isSignedIn`, `fill`, `mk` bands), so there's nothing new to learn and no flash of the wrong currency.
- Old `/#pricing` links keep working with no script.

**Cons**:
- Every visit is a Worker render with no edge cache.
- Prices show in one more place (the page plus the teaser), though both read the same constants.

### Option 2: Expand the homepage section

Make the teaser the full pricing: both cards, setup offers, the included list and the billing FAQ, all on the homepage at `/#pricing`.

**Pros**:
- No new route, and the nav link stays as it is.
- One fewer page to keep in step.

**Cons**:
- The homepage grows by three bands, which undoes spec 0019's short story and adds weight below the fold on a phone.
- Pricing has no URL of its own, so it can't rank for price searches or carry its own structured data.

### Option 3: A prerendered `/pricing` with both currencies, switched in the browser

Build `/pricing` once at deploy time with both versions in the HTML, cache it at the edge, and show one version with a small script that reads the country (from a cookie or a header echo endpoint) and the sign in state on the client.

**Pros**:
- Served from the edge cache, so it's the fastest possible first byte.
- Crawlers see both currencies in the HTML.

**Cons**:
- The wrong currency or the wrong buttons can flash before the script runs, which costs layout shift (CLS) and trust.
- The country and the session have to be read in the browser, which is a new pattern this site doesn't use, and it needs a new endpoint or cookie.
- Both versions ship to every visitor, so the page is heavier on a phone.

## Rationale

Option 1 is the only one that meets all the forces without a new pattern. The country and session choice already happens on the server for the homepage, and copying that exactly means the currency and buttons are right in the first HTML, with no flash and no layout shift (the spec 0017 bar). A Worker render per visit is the cost the homepage already pays, and no traffic measurement says it's a problem, so edge caching (Option 3) would be optimizing a cost nobody has measured while adding a client side country read and a flash risk.

Option 2 keeps things smaller, but it gives up the one thing a pricing page earns: a URL that answers "how much does RareBooks cost". It would also make the homepage, which spec 0019 just cut to seven focused bands, carry billing detail most homepage visitors never open. Keeping the teaser gives both: the homepage keeps a price in view, and the old anchor still lands on pricing.

The crawler problem (Google sees only USD) is handled by a fixed JSON-LD block and a country neutral meta description that name all three prices, built from the same constants. Both are the same for every visitor, so they are a superset of any one version of the body: every price they name shows only in the body of the version whose visitors can pay it (see the update below). The setup offers, the included list and the FAQ were chosen so that a visitor can work out the full cost and the consequences of not paying before starting a trial. Every promise in them maps to an existing spec, and the page leaves out what isn't built or decided yet (the plan switch and refunds).

### Update 2026-11-25: one currency per visitor

The first version of AC-6 put a second line under the plan cards naming the other version's prices ("Outside Tanzania: …" or "In Tanzania: …"), so that every price in the JSON-LD was also visible in every version of the body. After seeing the built page, you decided that a visitor should see only their own currency: showing a Tanzanian shop owner a dollar price, or a business abroad a shilling price, adds noise and invites the "why can't I pay that one" question.

Options weighed:
- **Keep the line.** It keeps the markup strictly matched to the body, but it shows every visitor a price they can't pay.
- **Drop the line, make the JSON-LD and description follow the visitor.** The markup would match the body, but the head would then vary by country (breaking AC-12), and crawlers, which mostly come from outside Tanzania, would never see the TZS price at all.
- **Drop the line, keep the fixed JSON-LD and description (chosen).** The body stays clean for each visitor, crawlers still learn all three prices, and the head stays the same for everyone. The cost is that the markup names prices the crawled body doesn't show. Since `/pricing` can't get a price rich result (it has no ratings, AC-13), the realistic downside is Google ignoring the markup, and every price in it is real and payable. If Search Console ever reports an issue, dropping the TZS `Offer` is the first fix.
