# 0021. Compare and alternatives pages

**Date**: 2026-11-25
**Status**: In Progress

Scope: feature 20 (Slice 10, Marketing site redesign) · Beta. Code lives in the `rarebooks-site` repo. Builds on spec 0017 (the `mk` design system), spec 0018 (MkNav and MkFooter), spec 0019 (the homepage copy helpers and `HomeCta`) and spec 0020 (`/pricing`, the visitor currency rule and Layout's `jsonLd` prop).

## Summary

The `/compare/*` and `/alternatives/*` pages get the new look, and their content gets a full refresh. Today they describe RareBooks as an offline desktop app sold through AppSumo, which is no longer true, and several competitors on them are desktop only or no longer sold. So the list itself changes: a competitor stays only while it is sold, maintained and has a cloud version, and up to twelve cloud competitors are researched and added (each must pass the same rule) (Wave, QuickBooks, FreshBooks, Xero, Sage, ZipBooks, Zoho Books, NetSuite, FreeAgent, Hnry, Reckon, MYOB). Every page is built from one data list through two dynamic routes, uses one fixed set of comparison rows with a source and a check date for every competitor fact, shows the RareBooks price in the visitor's own currency, and carries a BreadcrumbList (structured data that tells search engines where the page sits). Dropped competitors' URLs redirect permanently (301) to their closest successor, or to the index page.

## Requirements

**User stories**:
- As a business owner choosing accounting software, I want an honest side by side of RareBooks and the tool I'm looking at, so that I can decide without trusting a sales pitch.
- As a visitor in Tanzania, I want the RareBooks price in shillings, and everyone else in dollars, so that the comparison speaks my money.
- As a visitor on a phone, I want the feature comparison to read top to bottom with no sideways scrolling, so that I don't have to zoom.
- As someone with an old link to a dropped comparison, I want to land on the closest current page, not an error.
- As the site owner, I want every competitor fact to carry its source and check date, so that I can trust the pages and refresh them later.

**Acceptance criteria**:
- **AC-1**: Competitor list rule. `competitors` in `src/data/competitors.ts` holds only products that, on the day they were checked, are (a) on sale to new customers anywhere a visitor could buy it (any country, not only Tanzania; a vendor announced end of sale counts as not on sale from its stated date), (b) maintained (a release, changelog entry or product update dated within the 12 months before the entry's `checkedOn`), and (c) offer a cloud version: an app the vendor hosts that the customer uses in a browser or a phone app. A desktop program run on a rented remote server or a remote desktop service counts as desktop only. Each of today's nine (`gnucash`, `busy-accounting`, `manager-io`, `quickbooks-desktop`, `reach-accountant`, `sage-50`, `tallyprime`, `turbocash`, `wings-accounting`) and each of the twelve candidates (`wave`, `quickbooks`, `freshbooks`, `xero`, `sage`, `zipbooks`, `zoho-books`, `netsuite`, `freeagent`, `hnry`, `reckon`, `myob`) is checked against (a), (b) and (c). The result and its source page are recorded in `verify.md` under *Competitor list*. A candidate that fails is left out with the reason recorded; a current one that fails moves to `retiredCompetitors` (AC-10). A case the rule doesn't settle cleanly is marked *borderline* in `verify.md` with the facts, and you decide it before step 5.
- **AC-2**: Every entry in `competitors` gets both `/compare/<slug>` and `/alternatives/<slug>`, rendered by `src/pages/compare/[slug].astro` and `src/pages/alternatives/[slug].astro`. The 18 per competitor files in `src/pages/compare/` and `src/pages/alternatives/` are deleted. A slug that is neither in `competitors` nor in `retiredCompetitors` returns the site's 404 page with status 404, through `return Astro.rewrite("/404")` in the route (`404.astro` already sets the 404 status itself). A check asserts both the status and that the body is the site 404 page.
- **AC-3**: Every competitor entry fills the nine fixed rows in this order and with these labels: Price (`price`), Free trial (`trial`), Point of sale (`pos`), Stock and batches (`stock`), Invoices and quotes (`invoicing`), More than one currency (`currency`), Users included (`users`), Mobile money accounts (`mobileMoney`), Support (`support`). No other rows, none skipped. A row where the competitor has nothing says so plainly ("Not available", "Not offered") rather than being left out. A vendor with no public price (for example NetSuite) gets "Quote only" in the Price row and in `pricingCompetitor`, sourced to the vendor's pricing or contact page; a vendor with no trial gets "No free trial", sourced the same way.
- **AC-4**: Every competitor fact has a source. For each entry, `sources` has a key for `pricing` and for each of the nine row keys, and each value is `{ url, checkedOn }`: an `https://` URL on the vendor's own site (or, for a product status such as "no longer sold", the vendor's announcement), and a `YYYY-MM-DD` date that is not in the future. A node test fails when a key is missing, a URL isn't `https://`, or a date is malformed or in the future.
- **AC-5**: RareBooks facts come from one place. The RareBooks cell of each row comes from `rareBooksRowsFor(local)[key]`, a template filled with the values in *Value sourcing*. Each RareBooks claim on these pages (row cells and the RareBooks prose fields of every entry) names nothing that `/books` doesn't do today: each is in `hostedPlan.included`, `hostedPlan.features` or the trial numbers, or is checked on the demo shop and recorded in `verify.md`. No page says RareBooks is offline, a desktop app, a device bound license, an AppSumo deal or has an offline grace period. A node test scans only the RareBooks fields (both `rareBooksRowsFor` results, and `bestForRareBooks`, `recommendationRareBooks`, `whySwitchToRareBooks`, each deep dive's `rarebooks` card, the `migrationSteps` and the `faqs` of every entry) for `offline`, `appsumo`, `licen`, `grace period` and `device` (case insensitive), and fails on any match. Competitor text may use those words.
- **AC-6**: Visitor currency. The Price row's RareBooks cell and the one price placeholder RareBooks prose may use, `{price}`, show TZS to a visitor whose `locals.countryCode` is `TZ` (through `isTanzania`), and USD to everyone else, unknown included. `{price}` is "TZS {tzsYear} a year" or "USD {usdMonth} a month or USD {usdYear} a year"; RareBooks prose uses no other price placeholder (`{tzsYear}`, `{usdYear}`, `{usdMonth}` are allowed only inside `rareBooksRowsFor`). A node test fills every entry for both visitors and checks that the Tanzania result holds no RareBooks USD figure and the abroad result no TZS figure. Competitor prices stay in the competitor's own currency on every page, so a Tanzania page may show a competitor's USD price. Each page renders per request (`export const prerender = false`) and sends `Cache-Control: private, no-cache`, as `/pricing` does.
- **AC-7**: The head is the same for every visitor (country and sign in state don't change it). Titles stay exactly as today: `RareBooks vs {shortName} | Platform Comparison`, `Best {shortName} Alternative for SMEs | RareBooks`, `Compare RareBooks to Other Accounting Software` and `RareBooks Alternatives Guides`, with new entries following the same patterns. Each page keeps its canonical path (`/compare/<slug>`, `/alternatives/<slug>`, `/compare`, `/alternatives`). Each `metaDescription` is 160 characters or fewer, names no price, and says nothing now false (AC-5); a new entry's follows the pattern "Compare RareBooks vs {shortName}: price, features and fit for small businesses, and which one suits how you work." trimmed to fit. The two index descriptions name only competitors on the final list. A node test checks every `metaDescription` and `summary` for length and for no `TZS`, `USD` or `$`. Every page sets `ogImage="/og/home.jpg"` with `ogImageAlt` imported from `homeCopy.abroad.hero.screenshotAlt` (spec 0019 AC-13, not copied), and `preloadSerif`.
- **AC-8**: Structured data. Each detail page passes Layout's `jsonLd` a `BreadcrumbList` with three `ListItem`s, matching its visible breadcrumb: Home (`https://rarebooks.cc/`), Compare (`/compare`) or Alternatives (`/alternatives`), then the page itself (`RareBooks vs {shortName}` or `{shortName} alternative`) with its canonical URL. Built by a pure `breadcrumbJsonLd(rootUrl, section, slug, name)` in `src/lib/marketing/breadcrumb.ts` (no imports, node tested), from constants and the entry only, and written through `jsonLdText`. The exact shape: `{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Home","item":"https://rarebooks.cc/"},{"@type":"ListItem","position":2,"name":"Compare","item":"https://rarebooks.cc/compare"},{"@type":"ListItem","position":3,"name":"RareBooks vs Xero","item":"https://rarebooks.cc/compare/xero"}]}` (for alternatives: "Alternatives", `/alternatives`, "Xero alternative", `/alternatives/xero`). The index pages carry no JSON-LD, and no page carries `FAQPage` or any other type. The Schema.org validator reports no errors on one deployed page of each kind.
- **AC-9**: Phone table. The feature table is one `<table>` with a `<caption>`, `<th scope="col">` column heads and a `<th scope="row">` capability per row. From 768 pixels (`md`) it shows as three columns. Below 768 pixels each row shows as a card: the capability as its title, then a line labelled "RareBooks" and a line labelled with the competitor's `shortName`, each label shown visually through `td::before { content: attr(data-label) }` under `md` (the label is hidden from screen readers there, which already hear the column head). Because a `display: block` change drops table semantics in some screen readers, the elements carry explicit roles: `role="table"` on `<table>`, `rowgroup` on `<thead>` and `<tbody>`, `row` on `<tr>`, `columnheader` on the column `<th>`, `rowheader` on the row `<th>`, `cell` on `<td>`. At 390 by 844 no page scrolls sideways, and the table keeps its table semantics for screen readers at every width.
- **AC-10**: Dropped URLs. `retiredCompetitors` maps each dropped slug to a successor slug in `competitors` or `null`. For each, `/compare/<old>` and `/alternatives/<old>` answer `301` to `/compare/<successor>` and `/alternatives/<successor>`, or to `/compare` and `/alternatives` when `null`. The two `[slug].astro` routes do this themselves (`return Astro.redirect(target, 301)` when the slug is in `retiredCompetitors`), so it needs no config import. Starting mappings, kept only when research drops the old one and keeps the new one: `quickbooks-desktop` → `quickbooks`, `sage-50` → `sage`. The existing `/blog/rarebooks-vs-*` redirects in `astro.config.mjs` come from one pure function, `blogRedirects(retired)` in `src/data/retiredCompetitors.ts` (no imports), over the nine old blog slugs, so each points straight to the final address. A node test asserts that no successor is itself retired, no slug is in both lists, and no `/blog/*` target is a retired URL (one hop). If importing that `.ts` file from `astro.config.mjs` fails in `astro build`, the data file becomes `retiredCompetitors.mjs` with a `.d.ts` beside it.
- **AC-11**: Page composition. A `/compare/<slug>` page renders MkNav, then in `<main id="main">` six `MkSection` bands in this order and tone: hero (canvas), price and fit (tint), feature table (canvas), deep dives (tint), recommendation with the switching guide link (canvas), closing call to action (`HomeCta`, ink), then MkFooter. An `/alternatives/<slug>` page renders: hero (canvas), is it time to switch (tint), side by side table (canvas), the four migration steps as an ordered list (tint), the two FAQs as `MkFaq` rows (canvas), closing call to action (`HomeCta`, ink). The index pages render: hero (canvas), card grid (canvas), cross link (tint). The words are those in *Page copy*. Each page has exactly one h1, and the h2 and h3 levels nest without skipping.
- **AC-12**: Highlights. Exactly one `MkHighlight` word in each h1 and in each closing call to action title, as marked in *Page copy*. No h2 or h3 on these pages has one.
- **AC-13**: Buttons and tracking. Every sign up button reads "Start free trial", links to `AppConfig.urls.signUpUrl` and keeps its `data-cta-location`: `compare_page_header`, `compare_page_footer`, `alternatives_page_header`, `alternatives_page_footer`. For a signed in visitor (`isSignedIn(Astro.locals)`) each of them reads "Go to your dashboard" (`dashboardLabel`) and links to `/dashboard`, and the hero's second button stays. Layout's click handler pushes `trial_interest` only for a click on a link to the sign up URL, as it does on the homepage and `/pricing`, so a dashboard button pushes none. "See pricing" links to `/pricing`. "Detailed vs Comparison" becomes "See the full comparison" and "View Alternatives Guide" becomes "Read the switching guide". `HomeCta` gains `location?: string` (default `final_cta_section`, so the homepage and `/pricing` don't change), used on both the signed in and the signed out button. These pages pass it a `{ title, lead, primary }` copy object built with `fill()` from the *Page copy* strings; the title keeps its `*word*` for `splitHighlight`, and the `home-cta-title` id stays (one per page).
- **AC-14**: Index pages. `/compare` and `/alternatives` list every entry in `competitors`, sorted alphabetically by `name` (case insensitive), each as one `MkCard` link holding the heading ("RareBooks vs {shortName}" or "{shortName} alternative"), the entry's `summary` (120 characters or fewer) and "See the comparison" or "Read the guide". The grid is one column on a phone, two from 640 pixels and three from 1024 pixels. The tint band under it links to the other index.
- **AC-15**: Fair comparison. Each entry keeps a real reason to choose the competitor (`bestForCompetitor`, `whenToChooseCompetitor`, `recommendationCompetitor`), written from the competitor's own strengths. No competitor text calls a product bad, outdated or similar, or states a fact that its `sources` entry doesn't support. Page copy has no em or en dash (the redesigned pages use none).
- **AC-16**: Quality. On one deployed `/compare/*` and one `/alternatives/*` page, and on both index pages, at 390 and 1280 pixels: axe reports no violations, Lighthouse mobile shows LCP ≤ 2.5 s, CLS ≤ 0.1, Accessibility 100 and SEO 100, every text and background pair is an allowed pair from spec 0017 (the *Allowed pairs* in `src/components/marketing/README.md`, held by `tests/marketing/contrast.test.ts`), and with only the keyboard you can reach every link, button and FAQ row with a visible focus ring. `npm test` and `npm run check` pass.
- **AC-17**: Old look removed. `CompareLayout.astro` and `AlternativesLayout.astro` and the four page files use only `mk` tokens: `grep -nE "bg-brand|text-ink|text-muted|font-display|rounded-pill|shadow-card|shadow-soft|dotted-bg|hero-glow" ` over them finds nothing.

## Decision

**Chosen option**: Option 2: one data list, two dynamic routes and shared layouts rebuilt on the `mk` components, with the content refresh researched during the build under the source rule.

`src/data/competitors.ts` becomes the single source for every comparison page: fixed rows, a source per competitor fact, shared RareBooks row templates filled per visitor, and a retired slug map that drives 301 redirects.

**Implementation skills**: `tailwindcss` (the `mk` classes and the phone table breakpoints) · `clerk-astro-patterns` (`clerk/skills`, `.agents/skills/clerk-astro-patterns/`, the signed in swap through `isSignedIn`) · `workers-best-practices` (`cloudflare/skills`, `.agents/skills/workers-best-practices/`, why these pages are never cached at the edge) · `web-perf` (the Lighthouse checks)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Design source**: the spec 0017 design system as built: `src/styles/marketing.css`, the components in `src/components/marketing/` and their README, and the `/design-system` preview page. Bands follow the homepage and `/pricing` rhythm (canvas and tint alternating, ink to close).

**Data model sketch**: no storage and no schema. `src/data/competitors.ts` changes to:

```ts
export type RowKey = "price" | "trial" | "pos" | "stock" | "invoicing" | "currency" | "users" | "mobileMoney" | "support";
export const rowLabels: Record<RowKey, string>;          // AC-3 labels, in AC-3 order
export const rowOrder: RowKey[];                         // the AC-3 order
export interface Source { url: string; checkedOn: string } // https URL, YYYY-MM-DD
export interface CompetitorEntry {
  slug: string;                 // unique, kebab-case, the URL part
  name: string;                 // "Zoho Books"
  shortName: string;            // headings: "RareBooks vs Zoho"
  summary: string;              // ≤ 120 characters, index card line (AC-14)
  metaDescription: string;      // ≤ 160 characters, no RareBooks price (AC-7)
  pricingCompetitor: string;    // the competitor's prices, in their own currency
  rows: Record<RowKey, string>; // the competitor cell per row (AC-3)
  sources: Record<RowKey | "pricing", Source>; // AC-4
  bestForCompetitor: string;
  bestForRareBooks: string;     // RareBooks prose: may use {placeholders}
  deepDives: [DeepDive, DeepDive]; // DeepDive and DualCard keep today's shape
  recommendationCompetitor: string;
  recommendationRareBooks: string;
  whenToChooseCompetitor: string;
  whySwitchToRareBooks: string;
  migrationSteps: [string, string, string, string];
  faqs: [Faq, Faq];             // Faq keeps today's { q, a }; both plain text, may use {placeholders}
}
export function rareBooksRowsFor(local: boolean): Record<RowKey, string>; // filled per visitor (Value sourcing)
export function rareBooksValues(local: boolean): Record<string, string | number>; // homeValues plus {price}
export const competitors: CompetitorEntry[];             // sorted by name when read (AC-14)
export function getCompetitor(slug: string): CompetitorEntry | undefined;
```

`src/data/retiredCompetitors.ts` (no imports, so `astro.config.mjs` and `node --test` can load it): `export const retiredCompetitors: Record<string, string | null>`. Removed fields: `pricingRareBooks` and `featureMatrix`. Every RareBooks prose field and both FAQ fields are filled with `fill()` from `src/lib/marketing/home.ts` and `rareBooksValues(local)`, so an unknown `{placeholder}` throws at render, never shows raw. `src/lib/marketing/escapeHtml.ts` (no imports, node tested with `<`, `>`, `&`, `"` and `'`) exports `escapeHtml`, and the layout passes `MkFaq` `{ question: fill(q), answer: escapeHtml(fill(a)) }`, since `MkFaq` writes the answer with `set:html`.

**State transitions**: none.

**API surface**: pages only, no API routes.

| Route | Renders | Inputs | Output | Auth | Errors |
|---|---|---|---|---|---|
| `/compare/[slug]` | `CompareLayout` | `slug` (path), `locals.countryCode`, Clerk session | HTML, `Cache-Control: private, no-cache` | public | 404 for an unknown slug |
| `/alternatives/[slug]` | `AlternativesLayout` | same | same | public | 404 for an unknown slug |
| `/compare`, `/alternatives` | the index pages | Clerk session (nav only) | HTML | public | none |
| `/compare/<retired>`, `/alternatives/<retired>` | the same `[slug]` routes, `Astro.redirect(target, 301)` from `retiredCompetitors` | `slug` | 301 with `Location` | public | none |
| `/blog/rarebooks-vs-<old>` | `redirects` in `astro.config.mjs`, from `blogRedirects(retiredCompetitors)` | none | 301 with `Location`, one hop | public | none |

**Page copy** (word for word; `{name}`, `{shortName}` and `{slug}` come from the entry; `{freeDays}` from `AppConfig.trial`; a `*word*` is the one `MkHighlight` word; per entry content comes from the data file under AC-1, AC-4, AC-5 and AC-15):

`/compare/<slug>`:
1. Hero: breadcrumb `Home / Compare / RareBooks vs {shortName}` (a `<nav aria-label="Breadcrumb">` with an `<ol>`, the last item `aria-current="page"`). Overline "Comparison". h1 "RareBooks vs *{shortName}*". Lead "How RareBooks and {name} compare on price, features and fit, so you can pick the one that suits how your business runs." Buttons: "Start free trial" (primary, `compare_page_header`), "See pricing" (secondary, `/pricing`).
2. Price and fit (tint): h2 "Price and fit". Two pairs of `MkCard`s, RareBooks first: h3 "RareBooks pricing" (the filled `rareBooksRowsFor(local).price` plus "Free for {freeDays} days, no card needed.") and h3 "{shortName} pricing" (`pricingCompetitor`); then h3 "Best for RareBooks" (`bestForRareBooks`) and h3 "Best for {shortName}" (`bestForCompetitor`). The RareBooks cards carry a 2 pixel `mk-brand` border.
3. Feature table (canvas): h2 "Feature by feature". Caption (visually hidden) "RareBooks and {shortName} compared on nine capabilities". Column heads "Capability", "RareBooks", "{shortName}".
4. Deep dives (tint): for each dive, h2 `dive.title`, the `dive.intro`, then two `MkCard`s with h3 headings from the dive, RareBooks first.
5. Recommendation (canvas): h2 "Our recommendation", `recommendationCompetitor`, then `recommendationRareBooks`. Then an `MkCard`: h3 "Switching from {shortName}?", "Read our step by step guide to moving your books.", and the button "Read the switching guide" (secondary, `/alternatives/{slug}`).
6. Closing (`HomeCta`, ink): title "Ready to switch to *RareBooks*?", lead "Try every feature free for {freeDays} days, with no card needed.", primary "Start free trial", location `compare_page_footer`.

`/alternatives/<slug>`:
1. Hero: breadcrumb `Home / Alternatives / {shortName} alternative`. Overline "Switching guide". h1 "Looking for an alternative to *{shortName}*?". Lead "Meet RareBooks: accounting, stock and point of sale in one app for small businesses, in any browser." Buttons: "Start free trial" (primary, `alternatives_page_header`), "See the full comparison" (secondary, `/compare/{slug}`).
2. Is it time to switch (tint): h2 "Is it time to switch?". Two `MkCard`s: h3 "When to choose {shortName}" (`whenToChooseCompetitor`), h3 "Why businesses switch to RareBooks" (`whySwitchToRareBooks`, brand border).
3. Side by side (canvas): h2 "Side by side", lead "How RareBooks compares to {shortName} on what a small business uses every day." The same table as compare item 3.
4. Migration (tint): h2 "Moving from {shortName} to RareBooks", lead "Moving your books over takes four steps." The four `migrationSteps` as an `<ol>` with numbered markers.
5. FAQ (canvas): h2 "Questions about switching", `MkFaq` with the two `faqs` (filled, and the answer escaped with `escapeHtml`, as in the data model).
6. Closing (`HomeCta`, ink): title "Ready to make the *switch*?", lead "Try every feature free for {freeDays} days, with no card needed.", primary "Start free trial", location `alternatives_page_footer`.

`/compare`: overline "Comparisons", h1 "Compare RareBooks to other *accounting* software", lead "Side by side breakdowns of price, features and fit, so you know exactly how RareBooks stacks up." Cards: "RareBooks vs {shortName}", `summary`, "See the comparison". Cross link (tint): h2 "Thinking of switching?", "Each guide covers when to stay, why businesses move and how to bring your books over.", button "Read the switching guides" (secondary, `/alternatives`).

`/alternatives`: overline "Switching guides", h1 "Switching accounting *software*?", lead "See why businesses move to RareBooks, what to expect when you bring your books over, and answers to common switching questions." Cards: "{shortName} alternative", `summary`, "Read the guide". Cross link (tint): h2 "Want the full comparison?", "Price, features and fit, side by side for every tool.", button "See all comparisons" (secondary, `/compare`).

**RareBooks row templates** (`rareBooksRowsFor`; you approve this wording when you confirm the spec, and AC-5 checks each on the demo shop):

| Row | Template |
|---|---|
| Price | Tanzania: "TZS {tzsYear} a year, everything included"; abroad: "USD {usdMonth} a month or USD {usdYear} a year, everything included" |
| Free trial | "{freeDays} days, no card needed" |
| Point of sale | "Included, with barcode scanner support" |
| Stock and batches | "Stock levels, batches and serial numbers" |
| Invoices and quotes | "Quotes, invoices, payments and print templates" |
| More than one currency | "Yes, accounts in more than one currency" |
| Users included | "Unlimited users and devices" |
| Mobile money accounts | "Yes, each wallet as its own account" |
| Support | "WhatsApp support and step by step guides" |

The Price row is stored as two templates (`priceLocal`, `priceAbroad` inside the module) and `rareBooksRowsFor(local)` picks one; the other eight rows are the same for every visitor. `local` is `isTanzania(...)` from the route.

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| Render a detail page | the entry | `getCompetitor(Astro.params.slug)`; undefined → 404 (AC-2) |
| Render a detail page | local or abroad | `isTanzania(Astro.locals.countryCode ?? "US")` (spec 0019, spec 0020) |
| Render a detail page | signed in | `isSignedIn(Astro.locals)` (spec 0018) |
| RareBooks price cell | `{tzsYear}`, `{usdYear}`, `{usdMonth}` | `hostedPlan.priceTZS.yearly`, `hostedPlan.priceUSD.yearly`, `.monthly` in `src/constants/pricing.ts`, through `homeValues` |
| RareBooks prose | `{price}` | `rareBooksValues(local)`: the AC-6 string for the visitor's version |
| 404 for an unknown slug | page and status | `Astro.rewrite("/404")`; `404.astro` sets the status |
| Social card alt | text | `homeCopy.abroad.hero.screenshotAlt` (imported) |
| Free trial cell, closing leads | `{freeDays}` | `AppConfig.trial.freeDays` (spec 0005 numbers), through `homeValues` |
| The other RareBooks cells | text | `rareBooksRowsFor(local)`, each claim traced to `hostedPlan.included` or the demo shop (AC-5) |
| Competitor cells, prices, prose | text | the entry, each fact backed by `sources` (AC-4), researched in the build |
| Row labels and order | text | `rowLabels`, `rowOrder` (AC-3) |
| Breadcrumb JSON-LD URLs | absolute URLs | `new URL(path, AppConfig.urls.rootUrl)` |
| Social card | image and alt | `/og/home.jpg` and the homepage `screenshotAlt` (spec 0019 AC-13) |
| Redirect target | path | `retiredCompetitors[old]`, `null` → the index; `/blog/*` targets from `blogRedirects` |
| Index order | list | `competitors` sorted by `name.toLowerCase()` |
| Tracking location | `data-cta-location` | fixed strings in AC-13 |
| Competitor list membership | keep or drop | the AC-1 rule, recorded in `verify.md` |

**Phone layout**: bands stack under 768 pixels; card pairs go one column under 768 pixels with the RareBooks card first; the table turns into one card per row (AC-9) with the capability as the card title and each value under its visible label; buttons go full width under 640 pixels; the hero breadcrumb wraps rather than truncates.

**Key invariants**:
- One data list drives every comparison page, both index grids and the redirects. No competitor fact lives in a layout.
- A competitor fact without a source does not ship (AC-4 test). A RareBooks claim that `/books` can't show does not ship (AC-5).
- The head never varies by visitor; the body may (AC-6, AC-7).
- No slug is in both `competitors` and `retiredCompetitors`, and no retired slug maps to another retired slug (a test checks both).
- A redirect is one hop: no `/blog/*` redirect points at a retired URL (AC-10, tested on `blogRedirects`).
- Escaped before `set:html`: every FAQ answer goes through `escapeHtml`.
- Section h2s carry no highlight; one highlight per h1 and per closing title (AC-12).

**Security model**: public, read only pages. The only identity read is the signed in flag from the Clerk session, on the server. No visitor input reaches the HTML except the slug, which only selects an entry from the list (never echoed for an unknown slug). JSON-LD is built from the entry and constants and escapes `<` through `jsonLdText`. FAQ answers are plain text we write, escaped before `MkFaq` renders them. No form, payment or PII.

**Configuration required**: none. No new bindings, secrets or environment variables.

**Critical test scenarios**:
- Happy path: open `/compare/xero` (or the first kept entry) with `cf-ipcountry: TZ`, then `KE`: six bands in order, the TZS then USD price in the Price row, nine rows in order, one h1 with one highlight, verifies **AC-3**, **AC-6**, **AC-11**, **AC-12**
- Phone: the same page at 390 by 844 shows each row as a labelled card and no sideways scroll; a screen reader still announces the table, verifies **AC-9**
- Sources: remove one `sources` key from an entry in a scratch copy and `npm test` fails; set a `checkedOn` to tomorrow and it fails, verifies **AC-4**
- Escaping: an FAQ answer holding `<b>` and `&` shows as text, not markup (node test on `escapeHtml` plus one rendered page), verifies **AC-11**
- Redirects: `curl -sI /compare/quickbooks-desktop` answers 301 to `/compare/quickbooks` (if both research outcomes hold), and an old `/blog/rarebooks-vs-*` link lands in one hop, verifies **AC-10**
- Unknown slug: `/compare/not-a-tool` answers status 404 with the site 404 page in the body, verifies **AC-2**
- Signed in: every sign up button reads "Go to your dashboard" and pushes no `trial_interest`, verifies **AC-13**
- Head: the title, description, canonical and BreadcrumbList are identical for `TZ`, `KE` and signed in; the validator shows no errors, verifies **AC-7**, **AC-8**
- Stale claims: put "offline" in one `bestForRareBooks` in a scratch copy and the AC-5 test fails, verifies **AC-5**

## Build plan

Tracer Bullet: one competitor goes end to end (data, route, layout, head, redirect) and is deployed before the rest of the list is researched and filled in.

1. The thread, data side: check `xero` against the AC-1 rule first and record it in `verify.md` (if it fails, use the next candidate that passes). Then the new types, `rowLabels`, `rowOrder`, `rareBooksRowsFor` and `rareBooksValues` in `src/data/competitors.ts`; research and write that one entry with all sources; `retiredCompetitors.ts` with an empty map and `blogRedirects`; `escapeHtml.ts` and `breadcrumb.ts`; the node tests for sources, row coverage, lengths and no price in meta or summary, the RareBooks field scan, the both visitor fill, escaping, the breadcrumb shape and the slug and one hop invariants, satisfies **AC-1**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**, **AC-8**, **AC-10**
2. The thread, page side: `[slug].astro` for both sections, `CompareLayout` and `AlternativesLayout` rebuilt in `mk` bands with the *Page copy*, the phone table, the `HomeCta` `location` prop, the signed in swap, the cache header, the head (titles, meta, canonical, social card, `preloadSerif`) and the BreadcrumbList. The old pages keep serving unchanged until step 5: first rename today's data file to `src/data/competitorsLegacy.ts` and today's layouts to `LegacyCompareLayout.astro` and `LegacyAlternativesLayout.astro`, and point the 18 old page files and both index pages at them. Astro routes a static file ahead of `[slug]`, so an old URL never reaches the new route. Deploy with the one new entry, satisfies **AC-2**, **AC-6**, **AC-8**, **AC-9**, **AC-11**, **AC-12**, **AC-13**, **AC-17**
3. The list: check all 21 products against the AC-1 rule and record the outcome and source in `verify.md`; settle `retiredCompetitors` and the successors, satisfies **AC-1**, **AC-10**
4. The content: research and write every kept and added entry (rows, sources, prose, summary, meta), rewriting the RareBooks side of kept entries; check each RareBooks claim on the demo shop; you review the copy in `verify.md` before deploy. A kept slug still serves its legacy page until step 5, so review a kept entry's new page in `astro dev` with its legacy file moved aside, not on the deployed URL, satisfies **AC-3**, **AC-4**, **AC-5**, **AC-7**, **AC-15**
5. Redirects and indexes, in one commit: fill `retiredCompetitors` and wire the redirect branch in both `[slug]` routes, build the `/blog/*` entries in `astro.config.mjs` from `blogRedirects` (confirm `astro build` loads it, else the `.mjs` fallback in AC-10), delete the 18 old page files and the three legacy files, then curl each retired URL and each `/blog/*` URL on `wrangler dev` or a preview for a single 301; rebuild `/compare` and `/alternatives` (alphabetical card grid, cross link, fixed index descriptions), satisfies **AC-2**, **AC-7**, **AC-10**, **AC-14**, **AC-17**
6. Checks: the phone pass, axe, Lighthouse, keyboard and the Schema.org validator on the deployed pages, recorded in `verify.md`, satisfies **AC-8**, **AC-9**, **AC-16**

## Migration plan

**Strategy**: strangler (old and new pages run side by side). New entries go live on the new routes while the old pages keep serving through the legacy files, then one deploy swaps the old URLs for the new pages or 301s.
**Phases**:
1. Steps 1 and 2: the new routes serve the first new entry; every old URL and both index pages are unchanged (static files win over `[slug]`).
2. Steps 3 and 4: entries are researched and added one by one on the new routes; still no old URL changes.
3. Step 5, one deploy: kept slugs move from the legacy files to the new route (delete their files), retired slugs get 301s, the `/blog/*` redirects are repointed, and the indexes switch.
**Rollback**: phases 1 and 2 revert by removing the new entry or route. Phase 3 is one commit; reverting it restores the legacy files and the old redirects, as long as the legacy files are deleted in that same commit.
**Risks**: a 301 is cached hard by browsers and search engines, so a wrong successor is slow to undo (check the AC-10 map before phase 3); a kept slug whose new entry isn't finished would 404 if its legacy file is deleted early (delete only slugs present in `competitors`); search rankings may dip while engines process the 301s; until the deferred sitemap exists, search engines find the new pages only through links (the index pages and footer), so they are discovered more slowly.

## Consequences

**Positive**:
- The pages stop making false claims about RareBooks, and every competitor fact can be traced and refreshed.
- One data list, two routes and two layouts: adding a competitor is one entry, with tests that refuse a half filled one.
- The comparison set moves to the cloud tools your visitors actually weigh RareBooks against, which are the searches worth ranking for.
- Prices can't drift from the real plan: they come from `src/constants/pricing.ts`.

**Negative / tradeoffs**:
- The build is mostly research and writing, for up to 21 products at two pages each. It is far bigger than a restyle, and the copy is not pinned word for word in this spec: you review it in `verify.md` before deploy.
- Competitor facts age. The `checkedOn` dates make it visible, but nothing refreshes them on its own.
- Dropping desktop competitors gives up pages that may rank today; 301s keep most of that value only where a successor exists.
- Pages render per request (no edge cache), a small cost per visit, the same one `/pricing` accepted.
- The fixed nine rows hide a competitor's distinct strengths (payroll, bank feeds) from the table; the deep dives and the "Best for" cards carry those instead.

**Neutral**:
- `HomeCta` gains a `location` prop with a default, so the homepage and `/pricing` don't change.
- The scope's "eighteen pages" and "keeps its URL" wording no longer holds: the count follows the list, and retired URLs redirect.

## Follow-up

- [ ] Add a sitemap with `/pricing`, `/compare/*` and `/alternatives/*` (already deferred in the scope, from spec 0020); the list is now dynamic, so build it from `competitors`.
- [ ] Decide how often competitor facts are checked again (for example every six months, with a test that warns on a `checkedOn` older than that).
- [ ] When feature 21 (sign up conversion tracking) is designed, the four `data-cta-location` values here are its comparison page events.