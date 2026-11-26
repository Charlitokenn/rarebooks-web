# 0024. Docs and blog restyle

**Date**: 2026-11-26
**Status**: In Progress

Scope: feature 25 (Slice 12, Docs and blog restyle) · Beta. Code lives in the `rarebooks-site` repo. Builds on spec 0017 (marketing design system) and spec 0018 (marketing nav and footer).

## Summary

The Starlight docs at `rarebooks.cc` get the marketing look, so moving from the homepage to the docs feels like one site. The `mk` design tokens (named colors, fonts and sizes) move into one shared file that both the marketing pages and a new `docs.css` read, and `docs.css` becomes the only stylesheet Starlight loads. The docs get one header bar that looks like the marketing nav but keeps Starlight's search, theme switch and phone menu, a slim marketing footer, Starlight's own sidebar again, and a dark palette made from the same brand colors. The unused blog plugin is removed, no chat or analytics scripts are added, and every docs URL stays the same.

## Requirements

**User stories**:
- As a visitor reading the docs, I want them to look and feel like the marketing pages so that I trust I am still on the RareBooks site.
- As a customer looking something up, I want search, the sidebar, the table of contents and next and previous links to keep working on my phone and by keyboard, in light or dark.
- As the engineer, I want the marketing and docs colors to come from one file so that they can never drift apart.
- As a customer on `/welcome` or a marketing page, I want nothing to change for me in this work.

**Acceptance criteria**:
- **AC-1**: `rarebooks-site/src/styles/mk-tokens.css` holds the single `@theme static` block of `mk` tokens, moved out of `marketing.css` unchanged, plus the new docs palette tokens in *Docs palette*. `marketing.css` imports it (and `mk-fonts.css`) directly after its `global.css` import, so every marketing token keeps its value. `design-system.astro` reads `mk-tokens.css` and still shows every token. `tests/marketing/contrast.test.ts` and `src/lib/marketing/tokens.ts` read `mk-tokens.css`, and every check they made before still passes.
- **AC-2**: `rarebooks-site/src/styles/docs.css` is the only entry in Starlight's `customCss`. It holds, in this order: the layer line `@layer base, starlight, theme, components, utilities;`, `@import "@astrojs/starlight-tailwind";`, `@import "tailwindcss/theme.css" layer(theme);`, `@import "tailwindcss/utilities.css" layer(utilities);` (no preflight, so Starlight's own reset stays), `@import "./mk-tokens.css";`, `@import "./mk-fonts.css";` (AC-6), the Plus Jakarta Sans weights 400, 600 and 700, and last, outside any layer so it wins over the bridge's own `--sl-*` values, the *Starlight mapping* for light and dark, the *Docs component variables* and the docs focus rule. It does not import `global.css`, `fonts.css`, shadcn, `tw-animate-css`, Inter or Bricolage Grotesque.
- **AC-3**: Every docs page shows one sticky header bar (a Starlight `Header` override) with, from start to end: `MkLogo` linking to `/`, the four `navLinks`, Starlight's `Search`, `SocialIcons`, `ThemeSelect`, then a Sign in link (`signInPath`) and a Start free trial button (`AppConfig.urls.signUpUrl`). The buttons are always the signed out pair, since docs pages are prerendered. The bar is Starlight's fixed header, 4rem tall at every width (`--sl-nav-height: 4rem`), laid out as a flex row inside `max-w-mk` with search pushed to the end group. Below 50rem (Starlight's own phone breakpoint, not Tailwind's `md`) the bar shows only the logo and search, and keeps `--sl-menu-button-size` plus a 1rem gap free on the inline end, since Starlight's `PageFrame` draws the menu toggle there (the header does not render it). The nav links, the two buttons, the social icons and the theme switch then live in the phone menu through a `MobileMenuFooter` override, below the sidebar list, in a wrapping row with 44 pixel targets. Every control is reachable by Tab in reading order, shows the docs focus ring (2 pixel solid outline, offset 3 pixels, `--mk-focus`) on `:focus-visible`, and is at least 44 pixels tall. In dark, the logo wordmark and the nav links use `mk-dark-strong`, hover and current use `mk-focus-on-dark`; the primary button stays white on `mk-brand` in both themes.
- **AC-4**: A Starlight `Footer` override renders `EditLink`, `LastUpdated` and `Pagination` imported from `virtual:starlight/components/*` (so the `Pagination` override is used), then a compact strip: `MkLogo`, then the columns from `visibleFooterColumns(footerColumns, false, AppConfig.legal.approved)` as inline link groups in one row that wraps below 50rem, then `© {year} RareBooks. All rights reserved.` with `year` from `new Date().getFullYear()` at build time. No Starlight credits. The strip is no taller than 240 pixels at 1280 pixels wide.
- **AC-5**: `src/components/Sidebar.astro` and the docs sidebar block in `global.css` (the `CUSTOM SIDEBAR ACCORDION STYLES` section) are deleted, and the `Sidebar` override is removed from `astro.config.mjs`. Starlight's own sidebar renders the seven configured groups, collapsed as configured, with the current page marked by `mk` brand color and `aria-current="page"`. On a 390 pixel wide screen and by keyboard alone: the phone menu opens and closes (Escape closes it), search opens with `/` and Ctrl+K and lands on a result with Enter, the mobile table of contents opens and jumps to a heading, and the previous and next links work. The restyled `Pagination` links are at least 44 pixels tall, use `--sl-color-gray-5` borders and `--sl-color-accent` on hover, and drop their opacity transition under reduced motion.
- **AC-6**: The page title (`h1`) uses Fraunces roman (weight 500) with the `Fraunces Fallback` roman face. The four Fraunces `@font-face` rules (roman, italic and their two fallbacks) move unchanged from `marketing.css` into `src/styles/mk-fonts.css`, which both `marketing.css` and `docs.css` import; all other text uses Plus Jakarta Sans; code uses Starlight's system monospace stack (`docs.css` sets `--sl-font-mono: var(--sl-font-system-mono)`, since the Tailwind bridge would otherwise swap in Tailwind's mono stack). A `Head` override preloads only the Fraunces roman file. No docs page requests the Fraunces italic, Bricolage Grotesque or Inter files. Font driven Cumulative Layout Shift on the docs home is 0.01 or less in Chrome's phone emulation.
- **AC-7**: The docs work in light, dark and auto (follow the device), switched by `ThemeSelect`, using the *Starlight mapping* values. A node test (`tests/docs/contrast.test.ts`) reads the docs palette from `mk-tokens.css` and checks every pair in *Docs allowed pairs*: normal text at 4.5:1 or more, UI parts and large text at 3:1 or more, in both themes. It also checks the text of Starlight's asides (note, tip, caution, danger) against their backgrounds in both themes; asides keep Starlight's own hues.
- **AC-8**: Code blocks use the Expressive Code themes `github-light` and `github-dark`, picked by the active theme, with `useStarlightUiThemeColors: true` so the frame, border and editor background follow the `--sl-*` mapping (no hex copied out of `mk-tokens.css`). axe reports no contrast violation inside code blocks on the AC-12 pages in either theme.
- **AC-9**: `starlight-blog` is removed from `package.json` and `package-lock.json`, and the `blogSchema` extend is removed from `src/content.config.ts` (the docs schema is plain `docsSchema()`). `/blog` and `/blog/anything` answer the site's 404 page with status 404, except the spec 0021 `/blog/rarebooks-vs-*` redirects, which still answer 301 to their final address in one hop. Checked on a `wrangler` preview of the build, not `astro dev`.
- **AC-10**: The set of docs URLs, and each page's `<title>`, meta description and canonical link, are identical before and after (`scripts/docs-head-snapshot.mjs` reads the built HTML under `dist/client` and writes every docs route with its title, description and canonical; `tests/docs/docs-head.test.ts` compares a fresh run with the committed `tests/docs/docs-head-snapshot.json` for an exact match, and skips with a clear message when there is no build). The Instagram social link's label reads "Instagram", and the three social links use the URLs in `AppConfig.socials` with the labels Facebook, Instagram and TikTok written in `astro.config.mjs` (if the config cannot import `src/constants/index.ts`, it copies the three URLs and a test checks they match).
- **AC-11**: No docs page loads tawk.to, PostHog, Google Tag Manager or Clerk's browser script. The only scripts on a docs page are Starlight's own (search, theme, menu, table of contents): inline scripts or scripts served from `/_astro/`. `tests/docs/no-scripts.test.ts` checks the built docs HTML (skipping when there is no build). If the Clerk integration adds its script to prerendered docs pages, the build limits Clerk so it does not run there.
- **AC-12**: On the deployed site, three docs pages score 90 or more for Lighthouse mobile Performance and 100 for Accessibility, with no axe violations, in light and in dark (Lighthouse mobile preset, best of 3 runs, results in `verify.md`): the docs home (`/getting-started/getting-started-with-rarebooks/`), a long reference page with a table and a code block (`/financial-reports/general-ledger/`, or the first page in `financial-reports` that has both if that one does not, recorded in `verify.md`), and `/getting-started/using-rarebooks-on-a-phone/`.
- **AC-13**: `/`, `/pricing`, one `/compare/*` page, `/auth/sign-in` and `/welcome` render the same as before: Playwright screenshots at 1280 and 390 pixels wide, with tawk.to, PostHog, Google Tag Manager and Clerk's scripts blocked, with the copyright year and any dates masked, match pixel for pixel, or each difference is listed in `verify.md` with its cause and accepted. `Layout.astro` and `WelcomeLayout.astro` are unchanged byte for byte.
- **AC-14**: With `prefers-reduced-motion: reduce`, nothing in the docs header, footer, sidebar or pagination animates.
- **AC-15**: `src/components/marketing/README.md` says the tokens live in `mk-tokens.css`, that the docs load `docs.css`, and lists the docs rules in *Key invariants*.

## Decision

**Chosen option**: Option 2: a shared token file and a separate `docs.css`, with Starlight component overrides for the header, phone menu footer, footer, head and pagination.

The `mk` tokens get one home, `mk-tokens.css`. Marketing pages keep reaching them through `marketing.css`; Starlight reaches them through its own `docs.css`, which maps Starlight's variables to `mk` values and carries nothing the docs don't use.

**Implementation skills**: `tailwindcss` (Tailwind v4 `@theme` tokens and layers) · `frameworks-on-cloudflare` (`cloudflare/skills`, `.agents/skills/frameworks-on-cloudflare/`) · `web-perf` (font preload and Lighthouse checks) · `playwright-cli` (the before and after screenshots)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Design source**: the shipped marketing system, spec 0017 (tokens, `MkButton`, `MkLogo`, focus ring) and spec 0018 (`MkNav` links and button order, `MkFooter` columns). No new visual source. The docs reuse the marketing look; they do not copy `MkNav` and `MkFooter` markup, since those decide the signed in state on the server.

**Data model sketch**: none. No storage, no schema. The blog removal deletes no content (there are no posts).

**API surface**: none. No new route. `/blog` stops existing (it already had no pages).

### Docs palette (new tokens in `mk-tokens.css`)

Hex only, so the contrast test can read them. Light values reuse existing `mk` tokens where one exists.

| Token | Value | Use |
|---|---|---|
| `--color-mk-docs-text` | `#3d3652` | body text, light |
| `--color-mk-docs-raised` | `#f3f0f7` | nav, inline code and card background, light |
| `--color-mk-docs-line` | `#cfc8d9` | strong borders, light |
| `--color-mk-docs-faint` | `#8a8499` | decoration only, light (never text) |
| `--color-mk-dark-canvas` | `#15111f` | page background, dark |
| `--color-mk-dark-raised` | `#2a2340` | nav, inline code and card background, dark |
| `--color-mk-dark-line` | `#352d4a` | borders, dark |
| `--color-mk-dark-text` | `#cfc8e6` | body text, dark |
| `--color-mk-dark-strong` | `#f3f0fa` | headings, dark |
| `--color-mk-dark-subtle` | `#b9b2cc` | secondary text, dark |
| `--color-mk-dark-faint` | `#7d7690` | decoration only, dark (never text) |
| `--color-mk-dark-brand` | `#8f78ff` | accent fills and the current page marker, dark |
| `--color-mk-dark-brand-low` | `#2e2266` | accent background, dark |
| `--color-mk-dark-white` | `#ffffff` | strongest text, dark (`--sl-color-white`) |

The dark link and focus color is the existing `--color-mk-focus-on-dark` (`#c9bdfb`).

### Starlight mapping (in `docs.css`)

Set on `:root` (dark, Starlight's default) and `:root[data-theme="light"]`. Starlight derives the rest (`--sl-color-text`, `--sl-color-bg-nav`, and so on) from these.

| Starlight variable | Light | Dark |
|---|---|---|
| `--sl-color-white` | `mk-ink` `#1b1530` | `mk-dark-white` |
| `--sl-color-gray-1` | `#2a2340` | `mk-dark-strong` |
| `--sl-color-gray-2` | `mk-docs-text` | `mk-dark-text` |
| `--sl-color-gray-3` | `mk-subtle` `#5c566b` | `mk-dark-subtle` |
| `--sl-color-gray-4` | `mk-docs-faint` | `mk-dark-faint` |
| `--sl-color-gray-5` | `mk-docs-line` | `mk-dark-line` |
| `--sl-color-gray-6` | `mk-border` `#e6e1ec` | `mk-dark-raised` |
| `--sl-color-gray-7` | `mk-docs-raised` | (not used by Starlight dark) |
| `--sl-color-black` | `mk-canvas` `#faf8f5` | `mk-dark-canvas` |
| `--sl-color-accent-low` | `mk-tint` `#efeafe` | `mk-dark-brand-low` |
| `--sl-color-accent` | `mk-brand` `#5b3df5` | `mk-dark-brand` |
| `--sl-color-accent-high` | `mk-brand-strong` `#4a2ee0` | `mk-focus-on-dark` |
| `--sl-color-bg-nav` | `var(--color-mk-canvas)` | `var(--color-mk-dark-canvas)` |
| `--sl-color-hairline`, `--sl-color-hairline-light` | `mk-border` | `mk-dark-line` |
| `--sl-color-hairline-shade` | `mk-border` | `mk-dark-canvas` |
| `--sl-font` | `var(--font-mk-sans)` | same |
| `--sl-font-mono` | `var(--sl-font-system-mono)` | same |
| orange, green, red, blue, purple hues | Starlight defaults, unchanged | same |
| page title `h1#_top` (a rule, not a variable) | `font-family: var(--font-mk-serif); font-weight: 500` | same |

Values must be written as `var(--color-mk-*)`, never repeated hex, so the token file stays the only source.

### Docs component variables (in `docs.css`, unlayered)

The marketing components read `--mk-focus`, `--mk-subtle` and `--mk-link`, which `marketing.css` defines only inside `.mk-band`. `docs.css` defines them on `:root` (dark) and `:root[data-theme="light"]`: light `--mk-focus: var(--color-mk-focus)`, `--mk-subtle: var(--color-mk-subtle)`, `--mk-link: var(--color-mk-brand)`; dark `--mk-focus: var(--color-mk-focus-on-dark)`, `--mk-subtle: var(--color-mk-dark-subtle)`, `--mk-link: var(--color-mk-focus-on-dark)`. The focus rule is `:focus-visible { outline: 2px solid var(--mk-focus); outline-offset: 3px; }` scoped to the docs header, footer strip, phone menu footer and pagination. `MkLogo` and the nav links take a class that sets their text to `--sl-color-white` so they follow the theme.

### Docs allowed pairs (checked by `tests/docs/contrast.test.ts`)

Measured while writing this spec; all pass.

| Theme | Foreground | Background | Ratio | Bar |
|---|---|---|---|---|
| light | docs text `#3d3652` | canvas `#faf8f5` | 10.72 | 4.5 |
| light | docs text | docs raised `#f3f0f7` | 10.08 | 4.5 |
| light | docs text | border `#e6e1ec` (inline code) | 8.85 | 4.5 |
| light | subtle `#5c566b` | canvas | 6.61 | 4.5 |
| light | subtle | docs raised | 6.21 | 4.5 |
| light | brand `#5b3df5` (links) | canvas | 5.77 | 4.5 |
| light | brand | docs raised | 5.43 | 4.5 |
| light | brand strong `#4a2ee0` | tint `#efeafe` (current page) | 6.48 | 4.5 |
| light | on dark `#ffffff` | brand (button) | 6.12 | 4.5 |
| dark | dark text `#cfc8e6` | dark canvas `#15111f` | 11.54 | 4.5 |
| dark | dark text | dark raised `#2a2340` | 9.24 | 4.5 |
| dark | dark text | dark line `#352d4a` (inline code) | 8.03 | 4.5 |
| dark | dark subtle `#b9b2cc` | dark canvas | 9.10 | 4.5 |
| dark | dark subtle | dark raised | 7.29 | 4.5 |
| dark | focus on dark `#c9bdfb` (links) | dark canvas | 10.74 | 4.5 |
| dark | focus on dark | dark raised | 8.60 | 4.5 |
| dark | focus on dark | dark brand low `#2e2266` (current page) | 7.91 | 4.5 |
| dark | on dark `#ffffff` | brand `#5b3df5` (button, both themes) | 6.12 | 4.5 |
| dark | dark strong `#f3f0fa` (logo, nav) | dark canvas | 16.48 | 4.5 |
| dark | dark faint `#7d7690` | dark canvas | 4.30 | 3 (UI only) |
| light | docs faint `#8a8499` | canvas | 3.39 | 3 (UI only) |

Forbidden: `mk-docs-faint` and `mk-dark-faint` as body text (the test asserts both fail 4.5:1, so they stay decoration only).

### Components and files

| File | Change |
|---|---|
| `src/styles/mk-tokens.css` | new: the moved `@theme static` block plus the docs palette |
| `src/styles/mk-fonts.css` | new: the four Fraunces `@font-face` rules, moved from `marketing.css` |
| `src/styles/marketing.css` | the token block and font faces replaced by `@import "./mk-tokens.css";` and `@import "./mk-fonts.css";` |
| `src/styles/docs.css` | new: the only Starlight `customCss` (AC-2) |
| `src/styles/global.css` | the docs sidebar block deleted (AC-5); nothing else changes |
| `src/components/docs/DocsHeader.astro` | new `Header` override (AC-3) |
| `src/components/docs/DocsMobileMenuFooter.astro` | new `MobileMenuFooter` override (AC-3) |
| `src/components/docs/DocsFooter.astro` | new `Footer` override; renders Starlight's default footer parts, then the strip (AC-4) |
| `src/components/docs/DocsHead.astro` | new `Head` override; renders Starlight's default head, then the Fraunces roman preload (AC-6) |
| `src/components/Pagination.astro` | restyled with `mk` tokens, same markup and route data (AC-5) |
| `src/pages/design-system.astro`, `src/lib/marketing/tokens.ts` | read `mk-tokens.css?raw` instead of `marketing.css?raw` (AC-1) |
| `src/components/marketing/MkSection.astro` | comment updated to name `mk-tokens.css` (AC-15) |
| `scripts/docs-head-snapshot.mjs`, `tests/docs/*` | new: snapshot script, head, contrast and no scripts tests (AC-7, AC-10, AC-11) |
| `src/components/Sidebar.astro` | deleted (AC-5) |
| `astro.config.mjs` | `customCss: ["./src/styles/docs.css"]`; overrides for `Header`, `MobileMenuFooter`, `Footer`, `Head`, `Pagination` (no `Sidebar`); `expressiveCode: { themes: ["github-dark", "github-light"] }`; `social` built from `AppConfig.socials` with the right labels; no `starlight-blog` import |
| `src/content.config.ts` | `docsSchema()` without the blog extend (AC-9) |

Each override composes Starlight's own parts (`Search`, `ThemeSelect`, `SocialIcons`, the default `Head`, and `EditLink`, `LastUpdated`, `Pagination` in the footer) through `virtual:starlight/components/*` imports, so other overrides are honored and Starlight upgrades keep fixing them. The menu toggle stays in Starlight's `PageFrame`. The `Head` override is needed (not the `head` config) because the hashed font URL comes from a `?url` import; its preload link carries `crossorigin`. `MkLogo` and `MkButton` are reused as is.

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| Docs header | nav link labels and paths | `navLinks` in `src/constants/navigation.ts` |
| Docs header | Sign in path | `signInPath` in `navigation.ts` |
| Docs header | Start free trial path | `AppConfig.urls.signUpUrl` |
| Docs header | signed in or out | decided: always signed out (docs are prerendered; no session at build time) |
| Docs header and phone menu | social links | `AppConfig.socials`, passed to Starlight's `social` config |
| Docs header and phone menu | social labels | written in `astro.config.mjs`: Facebook, Instagram, TikTok |
| Footer strip | link columns | `visibleFooterColumns(footerColumns, false, AppConfig.legal.approved)` |
| Footer strip | copyright line | `© {year} RareBooks. All rights reserved.`, `year` from `new Date().getFullYear()` at build time |
| Head | Fraunces roman file URL | `@fontsource-variable/fraunces/files/fraunces-latin-wght-normal.woff2?url`, as `Layout.astro` does |
| Every docs page | colors | `mk-tokens.css` through the *Starlight mapping* |
| Code blocks | syntax colors | Expressive Code `github-light` and `github-dark` |
| URL and head snapshot (AC-10) | the before list | `tests/docs/docs-head-snapshot.json`, written by `scripts/docs-head-snapshot.mjs` from the build before step 1 and committed |

**Key invariants**:
- `mk-tokens.css` is the only place an `mk` color value is written, and `mk-fonts.css` the only place a Fraunces face is declared. `docs.css` and `marketing.css` only reference tokens.
- `docs.css` never imports `global.css` or `marketing.css`, and `marketing.css` never imports `docs.css`.
- No marketing band rule (`.mk-band`, `[data-tone]`) and no `.dark` rule enter the docs; dark docs use Starlight's `data-theme`.
- Docs pages stay prerendered and script light: no third party scripts, no Clerk, no `client:` islands.
- Docs URLs live at the site root, as Starlight serves them today; `AppConfig.urls.docsHomePath` stays the docs home.

**Security model**: public, read only pages. No auth, no inputs. Removing Clerk's script from consideration on docs keeps the header to plain links; Sign in hands off to the existing `/auth/sign-in` route.

**Configuration required**: none. One new dev dependency, `@astrojs/starlight-tailwind` 5.0.0 (peers: Starlight 0.38 or newer, Tailwind 4); `starlight-blog` removed. Keep `package-lock.json` in sync (Cloudflare installs with `npm clean-install`).

**Critical test scenarios** (each maps to an acceptance criterion):
- Happy path: open the docs home from the marketing nav's Docs link, read in light, switch to dark, search for "invoice", open the result, go Next, verifies **AC-3**, **AC-5**, **AC-7**
- Phone and keyboard: at 390 and at 790 pixels, Tab through the header, open the menu, reach Start free trial, Escape out, open the mobile table of contents, verifies **AC-3**, **AC-5**
- Contrast drift: change `--color-mk-dark-text` to `#7d7690`, the docs contrast test fails, verifies **AC-7**
- Token move: the existing marketing contrast test still passes against `mk-tokens.css`, verifies **AC-1**
- Blog gone: `/blog` is 404, `/blog/rarebooks-vs-quickbooks` is 301 to its compare page, verifies **AC-9**
- SEO guard: a docs page with a changed title fails the snapshot test, verifies **AC-10**
- No scripts: the built docs HTML has no `tawk.to`, `posthog`, `googletagmanager` or `clerk` script, verifies **AC-11**
- Nothing else moved: before and after screenshots of the AC-13 pages match, verifies **AC-13**

## Build plan

Tracer Bullet: step 1 runs one docs page end to end on the new stylesheet and header, then each step thickens it.

1. Snapshot first: write `scripts/docs-head-snapshot.mjs`, build, write `tests/docs/docs-head-snapshot.json`, check whether Clerk's script appears in a built docs page, (every docs route with its title, description and canonical) and take the AC-13 before screenshots into the scratchpad, satisfies **AC-10**, **AC-13**
2. Thin thread: create `mk-tokens.css` (move the block, add the docs palette), import it from `marketing.css`, repoint `tokens.ts`, `design-system.astro` and the marketing contrast test; add `@astrojs/starlight-tailwind`; create `docs.css` with the light mapping and switch `customCss`; add `DocsHeader` with logo, `Search`, `ThemeSelect` and the menu toggle, satisfies **AC-1**, **AC-2**, **AC-3**
3. Dark palette: the dark mapping and `tests/docs/contrast.test.ts` with the *Docs allowed pairs* and forbidden pairs, satisfies **AC-7**
4. Full header: nav links, social icons from `AppConfig.socials` (label fix), Sign in and Start free trial, and `DocsMobileMenuFooter` for the phone menu, satisfies **AC-3**, **AC-10**
5. Fonts: move the Fraunces faces to `mk-fonts.css`, Fraunces roman h1, the Jakarta weights, `DocsHead` preload, satisfies **AC-6**
6. Sidebar and reading parts: delete `Sidebar.astro`, its override and its `global.css` block; restyle Starlight's sidebar, table of contents, search modal and `Pagination.astro`, satisfies **AC-5**, **AC-14**
7. Footer strip: `DocsFooter`, satisfies **AC-4**, **AC-14**
8. Code blocks: Expressive Code themes and frame colors, satisfies **AC-8**
9. Blog removal: uninstall `starlight-blog`, plain `docsSchema()`, check the 404 and the spec 0021 redirects, satisfies **AC-9**
10. Guards and docs: the snapshot test, the no scripts test (`tests/docs/no-scripts.test.ts` over the build output), the README update, satisfies **AC-10**, **AC-11**, **AC-15**
11. Verify on the deployed site: the AC-13 after screenshots, Lighthouse and axe on the AC-12 pages in both themes, reduced motion, recorded in `verify.md`, satisfies **AC-12**, **AC-13**, **AC-14**

## Consequences

**Positive**:
- The docs and marketing pages share one look and one token file, so a brand color change reaches both at once.
- The docs load less CSS than today (no shadcn, no Inter, no Bricolage, no accordion script).
- Going back to Starlight's sidebar removes about 300 lines of custom HTML string code and gains native keyboard and screen reader support.

**Negative / tradeoffs**:
- Signed in users see Sign in and Start free trial on docs pages; clicking Sign in still lands them in their account, but the header doesn't greet them.
- Four Starlight overrides are now ours to keep working on Starlight upgrades; composing Starlight's own parts limits this but doesn't remove it.
- `marketing.css` changes (the block becomes an import), so spec 0017's "only `marketing.css` holds tokens" note is now out of date.
- One more dev dependency (`@astrojs/starlight-tailwind`).
- No chat widget on docs, so a stuck reader must click through to support.

**Neutral**:
- The blog can come back later as its own feature; it would need the plugin again and its own styles.
- `global.css` is now loaded only by `marketing.css` and `WelcomeLayout.astro`.

## Follow-up

- [ ] Spec 0017's index and the marketing README say tokens live in `marketing.css`; once this ships, /sync should note the move to `mk-tokens.css` (AC-15 covers the README).
- [ ] `src/constants/welcome.ts` line 11 notes a `/docs/...` prefix question flagged for /architect; this spec keeps docs at the site root, so that note can be closed.
- [ ] If a blog returns, enroll it as its own scope feature (posts, author, RSS, the `/blog` route).
- [ ] The scope's Deferred list still holds the `/dashboard` restyle; `/dashboard` now redirects to `/welcome` (spec 0023), so that item should be reworded to `/welcome` or dropped.
