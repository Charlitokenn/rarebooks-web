# 0018. Marketing nav and footer

**Date**: 2026-11-25
**Status**: In Progress

Scope: feature 17 (Slice 10, Marketing site redesign) · Beta. Code lives in the `rarebooks-site` repo. Builds on spec 0017 (the `mk` design system).

## Summary

Every marketing page gets a new header and footer built from the spec 0017 design system. The header is a full width sticky bar with four flat links (Features, Pricing, Compare, Docs), with no dropdowns. On the right it shows Sign in and Start free trial to visitors, and one Dashboard button to signed in customers, decided on the server so nothing flashes. On a phone the links move into a native `<dialog>` sheet (the browser's own modal, which traps focus and closes on Escape). The footer has four link columns, social icons and the support email. Two new pages, `/privacy` and `/terms`, are drafted here, and the footer links to them only once you approve the wording.

## Requirements

**User stories**:
- As a visitor on a phone, I want a menu that opens, closes and reads cleanly so that I can reach pricing, comparisons and the trial from any page.
- As a keyboard or screen reader user, I want to skip the nav, move through it in a sensible order and know which page I'm on.
- As a signed in customer, I want one Dashboard button instead of trial prompts, so the header fits me.
- As the operator, I want trial clicks from the header and footer counted by location, and I want the legal pages kept out of sight until I approve their text.

**Acceptance criteria**:
- **AC-1**: `src/components/marketing/MkNav.astro` and `MkFooter.astro` exist and replace `src/components/Navbar.astro` and `src/components/Footer.astro`. Both old files are deleted, and no file imports them. Every page on `Layout.astro` except `/auth/sign-in`, `/auth/sign-up` and `/design-system` renders MkNav first and MkFooter last: the homepage, `/compare`, `/alternatives` and every page under them (through `CompareLayout` and `AlternativesLayout`), the 404 page (which gains the header and gets `export const prerender = false`, so an unknown URL is rendered on demand through the Clerk middleware; a request for a made up path shows the new header) and `/privacy` and `/terms`. The auth pages and `/design-system` don't render MkNav or MkFooter, and AC-6 doesn't apply to them.
- **AC-2**: The header is `position: sticky; top: 0`, 64 pixels tall at every width, full width on `mk-canvas` with a 1 pixel `mk-border` bottom line, carries `class="mk-band" data-tone="canvas"` so the spec 0017 band values and focus ring apply, and sits at `z-40` so page content and the tawk.to and Turnstile widgets don't cover it. A focused element or an anchored section (`/#features`, `/#pricing`) is never hidden under it: it stays within the 5rem `scroll-padding-top` from spec 0017 (WCAG 2.2, 2.4.11). No page keeps the top padding the old fixed pill needed: `pt-36 sm:pt-40` (and the `-mt-8` in `Hero.astro`) in `Hero.astro`, `CompareLayout.astro`, `AlternativesLayout.astro`, `compare/index.astro` and `alternatives/index.astro` become `pt-16`, and `grep -rn "pt-36" src` finds none of them.
- **AC-3**: The links come from one list in `src/constants/navigation.ts`, in this order: Features `/#features`, Pricing `/#pricing`, Compare `/compare`, Docs `/getting-started/getting-started-with-rarebooks/`. From 768 pixels wide (Tailwind `md`) they show in a row beside the logo. Below 768 pixels, the row and the right side buttons are hidden, and a Menu button shows.
- **AC-4**: The right side is decided on the server from `Astro.locals.auth()`. Signed out: a `Sign in` link to `/auth/sign-in` and a primary `MkButton` `Start free trial` to `/auth/sign-up` (spec 0014 AC-7, which lands on `/dashboard/start`). Signed in: one primary `MkButton` `Dashboard` to `/dashboard`, and neither Sign in nor Start free trial appears. The first HTML byte already holds the right set: no Clerk client component decides it, and nothing swaps after load. If `auth()` is missing or throws, the signed out set renders and the page still answers 200.
- **AC-5**: The phone menu is a `<dialog id="mk-nav-menu" aria-label="Menu">` inside the header, opened by the Menu button (`data-open-modal="mk-nav-menu"`, `aria-haspopup="dialog"`, `aria-controls="mk-nav-menu"`, accessible name "Open menu") through the existing Layout handler with `showModal()`. The dialog has `p-0`, and one inner wrapper fills the whole sheet. While it is open: focus moves to its first link (the browser default, no `autofocus`), Tab and Shift+Tab stay inside it, the page behind is inert and doesn't scroll, and it holds the four links, then the same signed in or signed out set as AC-4, then a Close button (`<form method="dialog">`, accessible name "Close menu"). It closes on Escape, on Close, on a tap on the backdrop, on a tap on any link inside it (so `/#pricing` on the homepage both closes and scrolls), and when the window grows to 768 pixels or more. On every close, focus goes back to the Menu button, except the resize close, where the Menu button is hidden, so focus moves to the first desktop link. With `prefers-reduced-motion: reduce` it opens and closes with no animation.
- **AC-6**: A skip link, "Skip to content", is the first focusable element on every page from AC-1. It stays hidden until it gets focus, then shows above the header, and it moves focus to `<main id="main">`. Each page (or its layout) keeps its own `<main>` and gives it `id="main"`; `Layout.astro` adds none. Each of those pages has exactly one `<main>`, checked by a test that counts them.
- **AC-7**: The Compare link has `aria-current="page"` on `/compare` and `aria-current="true"` on any `/compare/*` page, and it shows a 2 pixel `mk-brand` underline both times. No other nav link is ever marked: section anchors aren't pages, Docs leaves the marketing layout, and `/alternatives` pages mark nothing, since Alternatives isn't in the nav.
- **AC-8**: Every Start free trial link (header, phone menu, footer) is `<a href="/auth/sign-up">` with `data-cta-location` set to `nav`, `nav-mobile` or `footer`, so the existing Layout click handler pushes `trial_interest` with that location and no new tracking code.
- **AC-9**: The footer is an `MkSection` (`as="footer"`, `tone="tint"`, `class="py-12 md:py-16"` in place of the band's default padding) with four columns, each a heading and a list: **Product**: Features, Pricing, Start free trial (signed out only, as AC-8), Sign in (signed out) or Dashboard (signed in). **Compare**: All comparisons `/compare`, Alternatives guides `/alternatives`. **Resources**: Docs (the AC-3 address), Support (`mailto:` `AppConfig.emails.supportEmail`). **Legal**: Privacy `/privacy`, Terms `/terms`. Under the columns: the logo, `AppConfig.description`, icons linking to Facebook, Instagram and TikTok from `AppConfig.socials`, and `© <year> RareBooks. All rights reserved.` with the year taken from the server clock. Each social icon is a link with an accessible name ("RareBooks on Facebook"), opens in a new tab with `rel="noopener noreferrer"`, and is at least 24 by 24 pixels (WCAG 2.2, 2.5.8). Columns stack on a phone, sit two across from 640 pixels and four across from 1024 pixels.
- **AC-10**: The Legal column shows only while `AppConfig.legal.approved` is `true`. `/privacy` and `/terms` exist (each `export const prerender = false`, on `Layout` in the new style, with a "Last updated" date from `AppConfig.legal.updated` shown as a long English date, such as 25 November 2026, and, while `approved` is `false`, a draft banner: "Draft for review. Not yet in force."). While `approved` is `false`, both carry `<meta name="robots" content="noindex, nofollow">` and an `X-Robots-Tag: noindex` header (set with `Astro.response.headers.set` in each page's front matter), and no page links to them. `approved` may only be set to `true` once `AppConfig.legal.controller` is filled in. Once you set `approved` to `true`, the column shows, the noindex is gone, and the draft banner goes away. This feature does no sitemap work: the only sitemap is the one Starlight builds, and it lists prerendered pages only.
- **AC-11**: The draft privacy page names each outside service the site and a hosted Books site send personal data to, and why: Clerk (sign in), Cloudflare (hosting, D1, Turnstile), Google Tag Manager (analytics), tawk.to (support chat, spec 0009), Resend (email), ClickPesa and PayPal (payments, spec 0008) and Frappe Cloud (hosting the Books site, spec 0010). It names the controller (the legal name and postal address from `AppConfig.legal.controller`, which you supply) and the contact for privacy requests (`AppConfig.emails.supportEmail`). It also states the trial clock with the numbers from spec 0005 (free trial on days 1 to 21, the window to pay on days 22 to 30, read only from day 26) and that an unpaid site's records are emailed to the owner and the site removed on day 30 (spec 0007). The draft terms page covers the trial, the plans and how they renew, the read only lock from day 26 and the day 30 removal (the same spec 0005 and 0007 numbers), acceptable use, and the support contact. Both drafts are marked for your review and are not legal advice.
- **AC-12**: The logo in MkNav and MkFooter is a static Astro component (`MkLogo.astro`, a link to `/` with the logo image and the name, `alt=""` on the image since the name is the link text). Marketing pages ship no React for the logo, and the social icons are inline SVG paths in `MkSocialIcon.astro`, with no React and no client JavaScript. The only client JavaScript this feature adds is one inline script of under 1 KB for the menu's close rules in AC-5. The script never calls `preventDefault`, so the Layout trial click handler still fires.
- **AC-13**: On the homepage and one `/compare/*` page, at 1280 and 390 pixel width, axe DevTools reports no violations in the header, menu or footer, every text and background pair in them is an allowed pair from spec 0017, and a keyboard pass meets AC-5 to AC-7. The deployed homepage keeps Lighthouse mobile Accessibility at 100, and its Cumulative Layout Shift (how much the page jumps while loading) doesn't get worse than the baseline. The baseline Lighthouse and layout shift numbers are recorded in `verify.md` before step 1 of the build plan.

## Decision

**Chosen option**: Option 1: a flat, server rendered nav with a native dialog phone menu.

MkNav and MkFooter are plain Astro components on the `mk` tokens, the signed in state is read on the server, and the phone menu is a `<dialog>` opened by the existing `data-open-modal` handler, with one small inline script for the close rules.

**Implementation skills**: `clerk-astro-patterns` (`clerk/skills`, `.agents/skills/clerk-astro-patterns/`, reading `locals.auth()` in an Astro component) · `tailwindcss` (the `mk` classes and breakpoints) · `playwright-best-practices` (the keyboard and dialog tests)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**: none. No storage and no schema. Two constant objects are added:

| Constant | File | Shape |
|---|---|---|
| `navLinks` | `src/constants/navigation.ts` | `{ label: string; href: string }[]`, the four AC-3 links in order |
| `footerColumns` | `src/constants/navigation.ts` | `{ title: string; links: { label: string; href: string; auth?: "signed-in" \| "signed-out"; ctaLocation?: string }[]; legal?: true }[]`, the four AC-9 columns |
| `AppConfig.legal` | `src/constants/index.ts` | `{ approved: boolean; updated: string; controller: { name: string; address: string } }`, with `approved: false`, `updated: "2026-11-25"` (ISO date, bumped when the text changes) and `controller` empty until you supply it |
| `AppConfig.urls.docsHomePath` | `src/constants/index.ts` | `"/getting-started/getting-started-with-rarebooks/"` (with the trailing slash Starlight serves; the build checks it answers 200 with no redirect), used by `navLinks`, `footerColumns` and the 404 page |

**API surface**: no new endpoints. New and changed routes, all GET, public, no inputs:

| Route | Change | Auth | Key errors |
|---|---|---|---|
| `/privacy` | new page, AC-10, AC-11 | public | none |
| `/terms` | new page, AC-10, AC-11 | public | none |
| every AC-1 page | new header and footer | public; reads the Clerk session if present | `auth()` failing renders signed out (AC-4) |

Components (all in `src/components/marketing/`):

| Component | Props | Renders |
|---|---|---|
| `MkLogo` | `href?` (default `/`) | the logo image (`alt=""`) and "RareBooks" in `font-mk-serif`, as one link |
| `MkNav` | none (reads `Astro.locals.auth()` and `Astro.url.pathname`) | the skip link, the sticky header, the desktop row, the right side set, the Menu button, the dialog and its inline script |
| `MkFooter` | none (reads `Astro.locals.auth()`) | the AC-9 footer |
| `MkSocialIcon` | `name`: `facebook` \| `instagram` \| `tiktok` | a 24 pixel inline SVG with `aria-hidden="true"`; the link around it carries the name |

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Render nav | the four links and their order | `navLinks` in `src/constants/navigation.ts` |
| Render nav | signed in or not | `Astro.locals.auth().isAuthenticated` (set by `clerkMiddleware` in `src/middleware.ts`, which reads the same field), read inside `try { … } catch { … }`: `auth` undefined, or a call that throws, counts as signed out. One helper, `isSignedIn(Astro.locals)`, is shared by MkNav and MkFooter, and tests mock `locals.auth`. |
| Render nav | Compare's `aria-current` value | derived from `Astro.url.pathname`: `"page"` when it is `/compare` or `/compare/`, `"true"` when it starts with `/compare/` and has more after it |
| Render nav | Sign in, sign up and dashboard paths | `/auth/sign-in` (the existing page), `AppConfig.urls.signUpUrl` (`/auth/sign-up`, spec 0014 AC-7), `/dashboard` |
| Render nav | where the trial sends the visitor after sign up | `forceRedirectUrl="/dashboard/start"` in `src/pages/auth/sign-up.astro`, unchanged |
| Trial click | `cta_location` in `trial_interest` | the link's `data-cta-location` (`nav`, `nav-mobile`, `footer`), read by the existing Layout handler |
| Render footer | columns and links | `footerColumns`, filtered by the `auth` flag and by `AppConfig.legal.approved` for the Legal column |
| Render footer | support address | `AppConfig.emails.supportEmail` |
| Render footer | social links | `AppConfig.socials` (`facebook`, `instagram`, `tiktok`) |
| Render footer | social icons | `MkSocialIcon.astro`, the SVG paths copied once from `@hugeicons/core-free-icons` (`Facebook01Icon`, `InstagramIcon`, `TiktokIcon`) |
| Render footer | tagline | `AppConfig.description`, unchanged here (see Follow-up) |
| Render footer | copyright year | `new Date().getFullYear()` on the server at request time |
| Render legal page | noindex on or off | `AppConfig.legal.approved` |
| Render legal page | "Last updated" date | `AppConfig.legal.updated`, formatted with `toLocaleDateString("en-GB", { dateStyle: "long" })` |
| Render legal page | controller name and address | `AppConfig.legal.controller`, supplied by you |
| Render legal page | trial and removal days | spec 0005 (days 21, 22, 26, 30) and spec 0007 (the day 30 export and removal) |
| Close menu at 768 px | the width | `matchMedia("(min-width: 48rem)")`, the same value as Tailwind `md` |

**Phone menu, exact behavior** (AC-5):
- Open: the Layout handler finds `[data-open-modal]` and calls `showModal()`. The browser moves focus to the first link in the dialog, traps Tab inside it, makes the page inert and closes on Escape.
- The inline script (`is:inline`, in MkNav, under 1 KB) adds three rules: a click whose target is the dialog element itself closes it (that is only the backdrop, because the dialog has `p-0` and an inner wrapper fills the sheet); a click on any `a` inside the dialog closes it and lets the browser follow the link, never calling `preventDefault`; a `change` on the 48rem media query to matching closes it only if it is open, then focuses the first desktop link.
- Scroll lock: MkNav's style holds `:global(body:has(#mk-nav-menu[open])) { overflow: hidden; }`, on `body`, as `ContactUsModal.astro` already does, never on `html` (that would stop body's overflow from reaching the viewport and break the sticky header). It only applies while the menu is open, so it doesn't break the spec 0017 rule that `marketing.css` adds no other page wide rule.
- Focus return: the browser returns focus to the element that was focused before `showModal()`, which is the Menu button (the resize close moves it to the first desktop link instead).
- Style: a full height sheet from the right, `max-width: 20rem`, `mk-surface`, `::backdrop` in `mk-ink` at 50% opacity. Links are at least 44 pixels tall. Any slide in transition sits behind `motion-safe:`.

**Key invariants**:
- The nav and footer link lists live only in `src/constants/navigation.ts`. Features 18 and 19 must keep the `features` and `pricing` ids on the homepage, or update `navLinks` in the same change (feature 19 may move pricing to `/pricing`).
- Marketing pages now vary by visitor (the nav shows Dashboard to signed in visitors), so no marketing response may carry a public, shared `Cache-Control` (`public`, `s-maxage`) or be cached at Cloudflare's edge. Today none is; keep it that way.
- New code uses only `mk` tokens and allowed pairs from spec 0017. No `brand`, `ink`, `muted`, `pill`, `card` or `soft` classes in MkNav, MkFooter, MkLogo or the legal pages.
- `AppLogo.tsx` stays for the dashboard sidebar (`app-sidebar.tsx`); only the marketing pages stop using it.
- A legal page is linked from somewhere only when `AppConfig.legal.approved` is `true`.

**Security model**: everything here is public and read only. The only identity read is the signed in flag, from the Clerk session on the server, never from a cookie parsed by hand or a form field (AGENTS.md rule). No user data is shown in the nav, only which button set to render. Social and outside links use `rel="noopener noreferrer"`.

**Configuration required**: none. No new bindings, secrets or environment variables.

**Critical test scenarios**:
- Happy path: on a 390 pixel phone, open the menu, Tab through it (focus stays inside), tap Pricing on the homepage: the menu closes, the page scrolls to pricing and the header doesn't cover the heading, verifies **AC-2**, **AC-5**
- Failure case: with `Astro.locals.auth` made to throw in a test, the homepage still answers 200 with Sign in and Start free trial, verifies **AC-4**
- Auth: signed in, the header, menu and footer show Dashboard and no Start free trial or Sign in anywhere, in the very first HTML response, verifies **AC-4**, **AC-9**
- Keyboard: on `/compare/gnucash`, Tab once shows the skip link, Enter moves focus to `main`; Compare carries `aria-current="true"`, verifies **AC-6**, **AC-7**
- Legal gate: with `approved: false`, `/privacy` answers with `X-Robots-Tag: noindex` and no page's HTML contains `href="/privacy"`; with `true`, the footer shows the Legal column, verifies **AC-10**
- Tracking: a click on the header Start free trial pushes `trial_interest` with `cta_location: "nav"`, verifies **AC-8**

## Build plan

Tracer Bullet: the first slice puts the new header on one real page, signed in and out, end to end, before it spreads.

1. Baseline, then the thread: record the homepage Lighthouse and layout shift numbers in `verify.md`; then `navigation.ts`, `AppConfig.urls.docsHomePath`, `MkLogo`, `MkNav` with the desktop row and the server side right set, the skip link and `id="main"`, on the homepage only, with the old top padding removed there; a node test that renders the nav signed in, signed out and with `auth()` throwing, satisfies **AC-2**, **AC-3**, **AC-4**, **AC-6**, **AC-8**, **AC-12**
2. Phone menu: the dialog, the inline close script, scroll lock and reduced motion; a Playwright test for open, Tab trap, Escape, backdrop, link tap, resize and focus return, satisfies **AC-5**, **AC-12**
3. Footer: `MkFooter` and `MkSocialIcon` with the four columns, the signed in filter, social icons, support email and copyright, on the homepage, satisfies **AC-8**, **AC-9**, **AC-12**
4. Spread: MkNav and MkFooter on `CompareLayout`, `AlternativesLayout`, the two index pages and 404 (with `docsHomePath` and `prerender = false`, plus a made up path test), `id="main"` and the `<main>` count test, the `aria-current` rule, the old top offsets removed, `Navbar.astro` and `Footer.astro` deleted, satisfies **AC-1**, **AC-2**, **AC-7**
5. Legal pages: `AppConfig.legal`, `/privacy` and `/terms` with drafted copy and the draft banner, noindex while not approved, the gated Legal column, satisfies **AC-10**, **AC-11**
6. Checks: README entries for MkLogo, MkNav, MkFooter and MkSocialIcon, and README line 13 ("Components ship no client JavaScript") rewritten to name the one MkNav inline script exception, then axe, keyboard and contrast checks at 1280 and 390 pixels, and the deployed Lighthouse and layout shift check, satisfies **AC-13**
7. Your approval: you supply `AppConfig.legal.controller`, review the legal wording, set `approved: true`, and the column and indexing turn on, satisfies **AC-10**

## Consequences

**Positive**:
- One header and footer, from one list of links, on every marketing page; a link change is one edit.
- Signed in customers get a header that fits them, with no flash and no Clerk script just for the nav.
- The phone menu gets focus trapping, Escape and inert background from the browser, not from hand written code.
- React no longer loads on marketing pages just to draw the logo.

**Negative / tradeoffs**:
- Marketing pages can't be cached at the edge as one shared copy, since the header depends on the visitor. Today they aren't cached anyway, but a later speed effort must cache per visitor or move the signed in check to the client.
- The menu adds a small inline script, a narrow exception to spec 0017's "no client JavaScript" rule.
- Flat links leave Alternatives in the footer only; a growing page set will one day need a menu.
- Legal links wait on your approval, so the scope's "footer lists legal links" isn't met until you review the text.

**Neutral**:
- Features 18 to 20 inherit the header and footer; they must not add their own.
- The homepage hero loses its top padding offset now; feature 18 rebuilds it anyway.

## Follow-up

- [ ] `AppConfig.description` still says "Modern desktop accounting app", but every trial is now a hosted site (spec 0014). Fix the tagline in feature 18, since the footer, meta description and social cards all show it.
- [ ] Before the legal pages go live, supply the legal name and postal address of whoever runs RareBooks (`AppConfig.legal.controller`).
- [ ] `/blog` is not live (`starlightBlog` is imported but not in Starlight's `plugins`, and there are no posts), so the footer leaves Blog out. Add it to `footerColumns` once the blog ships.
- [ ] Spec 0009's rollout task wants the privacy policy to name tawk.to; AC-11 covers it, so tick that task once you approve the page.
- [ ] `AppConfig.urls.documentationUrl` has no `https://` (used in `enquiry-email.tsx`). Out of scope here; fix it next time that email is touched.
