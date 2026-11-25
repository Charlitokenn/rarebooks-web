# 0021. Compare and alternatives pages: rationale

## Context

The `rarebooks-site` comparison pages are nine `/compare/<slug>` and nine `/alternatives/<slug>` pages, each an 8 line file that hands an entry from `src/data/competitors.ts` to `CompareLayout` or `AlternativesLayout`, plus two index pages. They still use the old purple tokens (`bg-brand`, `text-ink`, `dotted-bg`), while the homepage and `/pricing` moved to the spec 0017 `mk` system. Scope feature 20 asked for a restyle that keeps every URL, title and meta.

Reading the data file changed the problem. The RareBooks side of all nine entries describes a product that no longer exists: an offline first desktop app with a device bound license, sold as a one time AppSumo deal with a 7 day offline grace period (27 matches). RareBooks is now hosted (spec 0010) with a 21 day trial and a yearly or monthly plan (specs 0005, 0020). Restyling these pages as they are would ship false claims with a newer look. Several competitors on the list are also desktop programs, and at least one has stopped new sales, so they are no longer the products a visitor weighs RareBooks against.

Forces at play: the pages are public and indexed, so URLs, titles and canonicals carry search value; the price must match the real plan in the visitor's currency, as `/pricing` already does; competitor facts go stale quickly and need a trail; the build is done by one engineer with an AI builder, so the shape must make a half filled entry impossible to ship; and the phone layout must read cleanly at 390 pixels (spec 0017, WCAG 2.2 AA).

The engineer decided, during the design conversation: a full content refresh on both sides; RareBooks is online only; drop any competitor that is discontinued, no longer sold, unmaintained or desktop only; research and add Wave, QuickBooks, FreshBooks, Xero, Sage, ZipBooks, Zoho Books, NetSuite, FreeAgent, Hnry, Reckon and MYOB; 301 dropped URLs to the closest successor; both page types for every competitor; one fixed row set; alphabetical order; titles kept and meta fixed only where false; BreadcrumbList only; stacked cards on phones; the existing design system; canvas and tint bands with an ink close; highlights in h1s and closing titles; `HomeCta` reused; button labels unified; MkFaq rows; `/og/home.jpg`; research done during `/develop` with sources recorded.

## Options considered

### Option 1: Restyle the two layouts, keep the per competitor files and free form rows

Rebuild `CompareLayout` and `AlternativesLayout` on `mk` components, edit the copy in place entry by entry, add new competitors as new 8 line files.

**Pros**:
- The smallest diff to the routing; each page stays a visible file.
- No new data shape to learn.

**Cons**:
- Free form rows make pages hard to compare and give research no checklist.
- Nothing stops an entry shipping without sources or with a stale RareBooks claim.
- Up to 42 near identical page files to keep in step, and redirects maintained by hand.

### Option 2: One data list, two dynamic routes, fixed rows with sources (chosen)

`competitors.ts` becomes the single source: nine fixed row keys, a source per competitor fact, shared RareBooks row templates filled per visitor, and a `retiredCompetitors` map that builds the 301s. Two `[slug].astro` routes replace the 18 files.

**Pros**:
- Adding or dropping a competitor is one data change; tests refuse a half filled entry.
- RareBooks facts are written once and filled from the plan constants, so prices can't drift.
- Redirects and index grids follow the list automatically.

**Cons**:
- A bigger change up front, and the data file grows large (about 21 entries).
- A dynamic route hides which pages exist unless you read the list.

### Option 3: Move the content to an Astro content collection (Markdown or JSON per competitor)

One file per competitor in `src/content/`, validated by a Zod schema.

**Pros**:
- Schema validation at build, one file per competitor is easy to review.
- Familiar to people who edit content in Markdown.

**Cons**:
- The site already keeps marketing copy in TypeScript constants (`home.ts`, `pricingPage.ts`) with `fill()` placeholders; a second content system splits the convention.
- The Starlight docs already own `src/content/`; mixing marketing data into it adds config to a shared area.
- The node tests in `tests/marketing/` read TypeScript directly; a collection needs the Astro runtime.

## Rationale

Option 2 fits the forces best. The real risk in this feature is not the look, it's shipping a false or unsourced fact, and the fixed row keys with a `sources` record turn that risk into a failing test rather than a review habit. Writing the RareBooks side once, as templates filled from `hostedPlan` and the trial numbers, follows exactly how spec 0019 and spec 0020 already keep prices honest, and the visitor currency rule then costs nothing extra. Option 1 would leave the same discipline to memory across up to 42 files; Option 3 is a sound pattern elsewhere, but here it would introduce a second content convention beside the constants the redesigned pages already use.

Doing the research in the build rather than in this spec keeps the facts freshest at ship time, but it means the copy isn't pinned word for word here, unlike specs 0019 and 0020. The spec compensates by pinning everything structural (bands, headings, buttons, row labels, the RareBooks row wording) and by making the source rule testable; the engineer reviews the researched copy in `verify.md` before deploy.

On structured data: Google limited FAQ rich results to a few authoritative government and health sites in 2023, so FAQPage markup would add maintenance without a search result payoff; BreadcrumbList is still shown and matches the visible breadcrumb. On the phone table: a single `<table>` restyled into labelled cards under `md` keeps table semantics for screen readers while removing sideways scrolling; a separate card list would duplicate content, and a scrolling table cramps long cells at 390 pixels. Runner up for the table: a sticky first column (still scrolls sideways). For retired slugs, the 301 is answered by the `[slug]` routes themselves rather than by `astro.config.mjs` redirects: the route already reads the data list, so no config import of a TypeScript file is needed for them, and a redirect can never be lost to a config that failed to load. The `/blog/*` redirects stay in the config, generated from the same data file so they never chain (the cross check's suggestion).

## Evidence: what the current pages say

- `src/data/competitors.ts`, July 2026: nine entries, free form `featureMatrix` rows (7 to 8 each), `pricingRareBooks` text naming AppSumo, a device bound license and a 7 day offline grace period; an "Offline-first" row on every entry; 41 lines mention offline.
- `astro.config.mjs` redirects `/blog/rarebooks-vs-<slug>` to `/compare/<slug>` for all nine current slugs.
- No comparison page sets `jsonLd`, `ogImage` or `preloadSerif` today; titles are as listed in AC-7.
