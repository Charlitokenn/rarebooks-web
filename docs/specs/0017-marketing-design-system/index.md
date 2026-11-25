# 0017. Marketing design system

**Date**: 2026-11-25
**Status**: In Progress

Scope: feature 16 (Slice 10, Marketing site redesign) · Beta. Code lives in the `rarebooks-site` repo. Features 17 to 20 (nav and footer, homepage, pricing, compare and alternatives) build on it.

## Summary

The marketing pages of `rarebooks.cc` get a new shared look: bright, friendly and roomy, in the spirit of Wave's site, but keeping the RareBooks purple, logo and copy. The look lives in one new stylesheet, `marketing.css`, that only the marketing layouts load. It sits on top of today's `global.css`, which stays exactly as it is, so `/dashboard` and the docs don't change. The system has a Fraunces serif for headlines and Plus Jakarta Sans for body text, color, type, spacing and shadow tokens (named design values) under an `mk` prefix, and ten small Astro components. A public preview page (hidden from search engines) shows all of them live. A unit test checks that every allowed text and background pair passes WCAG 2.2 AA contrast.

## Requirements

**User stories**:
- As a visitor on a phone, I want the marketing pages to load fast and read clearly so that I can understand RareBooks and start a trial.
- As the engineer building features 17 to 20, I want one set of tokens and components so that every redesigned page looks the same without copying styles.
- As a signed in customer, I want `/dashboard` and the docs to look exactly as before, so that this redesign does not disturb my work.

**Acceptance criteria**:
- **AC-1**: `rarebooks-site/src/styles/marketing.css` exists, imports `global.css` first, and defines every token in the *Token set* below under the `mk` prefix (Tailwind v4 `@theme static`, so classes like `bg-mk-canvas`, `text-mk-h2`, `rounded-mk-card` work). Every color token is a 6 digit hex value.
- **AC-2**: The source files `global.css`, `fonts.css`, `PortalLayout.astro` and the Starlight `customCss` entry in `astro.config.mjs` are unchanged byte for byte (`git diff` on them is empty; the built CSS for the dashboard may gain unrelated utility classes, since Tailwind scans the whole project, and that is allowed). `/dashboard`, `/dashboard/start`, `/docs` and one blog post render the same as before: screenshots taken before and after with the Playwright CLI, at 1280 and 390 pixel width, with Google Tag Manager, tawk.to and Clerk's scripts blocked, match pixel for pixel, or each difference is listed in the verify notes with its cause and accepted. The screenshots go in the session scratchpad, not the repo.
- **AC-3**: `Layout.astro` loads `marketing.css` instead of `global.css`, so every page on it gets the new file: the homepage, `/compare` and `/alternatives` and their pages (through `CompareLayout` and `AlternativesLayout`), `/auth/*` and the 404 page. Each of these looks as before by the same screenshot check as AC-2: the old tokens (`bg-brand`, `text-ink`, `text-muted`, `font-display`, `rounded-pill`, `shadow-card`, `shadow-soft`) keep their values because they still come from `global.css`, and the only page wide rule `marketing.css` adds is `scroll-padding-top` on `html`. Every other marketing rule (background, text color, focus ring) applies only inside an `MkSection` band.
- **AC-4**: These Astro components exist in `src/components/marketing/` with the props in *Component contracts*: `MkButton`, `MkSection`, `MkHeading`, `MkHighlight`, `MkCard`, `MkBadge`, `MkFeatureRow`, `MkScreenshotFrame`, `MkFaq`, `MkCheckList`. None of them ships client JavaScript.
- **AC-5**: A node test (`tests/marketing/contrast.test.ts`, run by `npm test`) reads the color tokens from the `@theme static` block of `marketing.css` and checks that: every `--color-mk-*` value there is a 6 digit hex; every token named in the *Allowed pairs* table exists; every allowed pair passes (normal text at 4.5:1 or more, large text and UI parts such as button borders, focus rings and check icons at 3:1 or more); and each pair in the *Forbidden pairs* list really fails, so it stays forbidden. A token change that breaks any of these fails the test.
- **AC-6**: Every interactive component (button, link button, FAQ summary) shows a visible focus ring on keyboard focus only (`:focus-visible`): a 2 pixel solid outline offset 3 pixels, in `mk-focus` on light bands and `mk-focus-on-dark` on the ink band, with 3:1 or more against the band. Buttons are at least 44 pixels tall.
- **AC-7**: Headline type is Fraunces (`@fontsource-variable/fraunces` 5.3.0, weight axis only, Latin subset), self hosted. Both Fraunces files (roman and italic) are preloaded, and only on pages that set `preloadSerif` because they render a display or h1 heading above the fold. The two files add no more than 85 KB (36.6 KB roman plus 45.7 KB italic, checked once the package is installed). Size adjusted fallback faces, one roman and one italic, keep the swap from shifting the layout: Cumulative Layout Shift from fonts on the preview page is 0.01 or less in Chrome's phone emulation (Moto G Power, slow 4G).
- **AC-8**: `/design-system` renders every token (color swatches with their names and hex values, the type scale, spacing, radii, shadows) and every component in each of its variants and on each band. It carries `<meta name="robots" content="noindex, nofollow">` and an `X-Robots-Tag: noindex` header, and no page links to it.
- **AC-9**: `rarebooks-site/src/components/marketing/README.md` lists each token group and each component with its props and one usage example, plus the rules in *Key invariants*.
- **AC-10**: The preview page scores 90 or more for Lighthouse mobile Performance and 100 for Accessibility, with no axe DevTools violations, on the deployed site.
- **AC-11**: With `prefers-reduced-motion: reduce`, no component animates (hover transitions and the FAQ open state change instantly).

## Decision

**Chosen option**: Option 2: a separate marketing stylesheet layered on top of `global.css`, with prefixed tokens and Astro components.

Marketing pages load `marketing.css`, which imports `global.css` and then adds the `mk` tokens, the Fraunces faces and the base rules. Only the marketing layouts import it, so nothing the dashboard or docs load changes.

**Implementation skills**: `tailwindcss` (Tailwind v4 `@theme` tokens) · `frameworks-on-cloudflare` (`cloudflare/skills`, `.agents/skills/frameworks-on-cloudflare/`) · `web-perf` (font and image loading checks)

## Feature design

**Design source**: Wave's marketing pages (waveapps.com), studied from screenshots the engineer captured on 2026-11-25 (homepage on desktop and phone, the pricing page, a comparison page). The screenshots stay with the engineer and are not committed. Patterns taken from them: big serif headlines with one italic word marked by a hand drawn underline; a small uppercase overline in the brand color; a warm off white page with full width bands of deep ink, light tint and soft pink; pill buttons, solid for the main action and outlined for the second; a large product screenshot in a rounded, shadowed frame; thin bordered cards with small corners, and bold solid quote cards; native looking FAQ rows; check mark lists for plan features. Wave's colors, illustrations, photos and words are not used.

**Data model sketch**: none. No storage, no schema.

**API surface**: none. The only new route is the static `/design-system` page (GET, public, no inputs).

### Token set

All tokens go in one `@theme static` block in `marketing.css`. `static` makes Tailwind output every variable even when no class uses it, so the `var(--color-mk-*)` rules in `marketing.css` always resolve. The `mk` prefix keeps them apart from the shadcn names (`muted`, `accent`, `primary`) and from the old marketing names in `global.css`.

Colors (hex only, so the contrast test can read them):

| Token | Value | Use |
|---|---|---|
| `--color-mk-canvas` | `#faf8f5` | page base, the default band |
| `--color-mk-surface` | `#ffffff` | cards and frames on any light band |
| `--color-mk-ink` | `#1b1530` | headings and body text; the deep ink band |
| `--color-mk-subtle` | `#5c566b` | secondary text on light bands |
| `--color-mk-brand` | `#5b3df5` | primary buttons, links, overline, check icons, highlight underline |
| `--color-mk-brand-strong` | `#4a2ee0` | primary button hover and pressed |
| `--color-mk-tint` | `#efeafe` | brand tint band, brand badge background |
| `--color-mk-pink` | `#fce4f2` | pink band, pink badge and quote card background |
| `--color-mk-pink-strong` | `#f7a8d8` | decoration only (never behind text) |
| `--color-mk-border` | `#e6e1ec` | decorative card and FAQ borders |
| `--color-mk-on-dark` | `#ffffff` | text on the ink band and on brand fills |
| `--color-mk-on-dark-subtle` | `#cfc8e6` | secondary text on the ink band |
| `--color-mk-focus` | `#5b3df5` | focus ring on light bands |
| `--color-mk-focus-on-dark` | `#c9bdfb` | focus ring on the ink band |

Fonts:
- `--font-mk-serif`: `"Fraunces Variable", "Fraunces Fallback", Georgia, serif`
- `--font-mk-sans`: `"Plus Jakarta Sans", system-ui, sans-serif` (already loaded by `fonts.css`)

Type scale (Tailwind v4 `--text-*` with `--line-height` companions; sizes are fluid with `clamp`):

| Token | Size | Line height | Family and weight |
|---|---|---|---|
| `mk-display` | `clamp(2.5rem, 1.6rem + 4vw, 4.5rem)` | 1.05 | serif 500, letter spacing -0.02em |
| `mk-h1` | `clamp(2.25rem, 1.7rem + 2.4vw, 3.5rem)` | 1.1 | serif 500, -0.015em |
| `mk-h2` | `clamp(1.875rem, 1.5rem + 1.6vw, 2.75rem)` | 1.15 | serif 500, -0.01em |
| `mk-h3` | `1.25rem` | 1.35 | sans 700 |
| `mk-lead` | `clamp(1.125rem, 1rem + 0.5vw, 1.25rem)` | 1.6 | sans 400 |
| `mk-body` | `1rem` | 1.65 | sans 400 |
| `mk-small` | `0.875rem` | 1.5 | sans 500 |
| `mk-overline` | `0.8125rem` | 1.2 | sans 700, uppercase, letter spacing 0.12em, `mk-brand` |

Display, h1 and h2 count as large text for contrast (24 pixels or more at their smallest). Tailwind's `--text-*` tokens can carry line height, letter spacing and weight, but not the font family, so `MkHeading` adds `font-mk-serif` (display, h1, h2) or `font-mk-sans` (h3) itself.

Spacing and layout. Responsive spacing can't be a single token, so it is written as Tailwind's own spacing classes inside the components, and only the widths are tokens:
- Band padding (in `MkSection`): `py-16 md:py-28` (4rem on phones, 7rem from the `md` breakpoint, 768 pixels)
- Side gutter (in `MkSection`): `px-5 md:px-8` (1.25rem, then 2rem)
- Between feature rows: `gap-16 md:gap-24` (4rem, then 6rem)
- `--container-mk`: `75rem` (1200 pixels) content width (`max-w-mk`); `--container-mk-narrow`: `48rem` for text heavy sections (`max-w-mk-narrow`)
- `scroll-padding-top` on `html` in marketing pages: `5rem` (the one page wide rule), so a sticky nav (feature 17) never covers a focused or anchored element (WCAG 2.2, 2.4.11)

Radii and shadows:
- `--radius-mk-pill`: `999px` (buttons, badges)
- `--radius-mk-sm`: `0.5rem` (FAQ rows, table cells)
- `--radius-mk-card`: `1rem`
- `--radius-mk-frame`: `1.25rem` (screenshot frame)
- `--shadow-mk-card`: `0 8px 30px -12px rgba(27, 21, 48, 0.14)`
- `--shadow-mk-frame`: `0 24px 60px -24px rgba(27, 21, 48, 0.28)`

Motion: `--ease-mk`: `cubic-bezier(0.2, 0, 0, 1)`, 150 ms for color and shadow changes, wrapped so `prefers-reduced-motion: reduce` turns them off.

### Allowed pairs

Measured with the WCAG 2.x formula. The test in AC-5 holds every row; a pair not listed is not allowed.

| Foreground | Background | Ratio | Needs |
|---|---|---|---|
| `mk-ink` | `mk-canvas`, `mk-surface` | 16.6, 17.5 | 4.5 |
| `mk-ink` | `mk-tint`, `mk-pink` | 14.9, 14.6 | 4.5 |
| `mk-subtle` | `mk-canvas`, `mk-surface` | 6.6, 7.0 | 4.5 |
| `mk-subtle` | `mk-tint`, `mk-pink` | 6.0, 5.8 | 4.5 |
| `mk-brand` | `mk-canvas`, `mk-surface` | 5.8, 6.1 | 4.5 |
| `mk-brand` | `mk-tint`, `mk-pink` | 5.2, 5.1 | 4.5 |
| `mk-on-dark` | `mk-brand`, `mk-brand-strong` | 6.1, 7.6 | 4.5 |
| `mk-on-dark` | `mk-ink` | 17.5 | 4.5 |
| `mk-on-dark-subtle` | `mk-ink` | 10.9 | 4.5 |
| `mk-ink` | `mk-on-dark` (white button on the ink band) | 17.5 | 4.5 |
| `mk-focus` | `mk-canvas`, `mk-tint`, `mk-pink`, `mk-surface` | 5.1 or more | 3 |
| `mk-focus-on-dark` | `mk-ink` | 10.2 | 3 |
| `mk-pink-strong` (highlight underline, decorative) | `mk-ink` | 9.7 | 3 |

**Forbidden pairs** (the test checks that each really fails, so nobody adds it later by mistake):
- `mk-brand` on `mk-ink` (2.9): on the ink band, the overline uses `mk-on-dark-subtle`, the highlight underline uses `mk-pink-strong`, check icons and focus rings use `mk-focus-on-dark`, and buttons use the `on-dark` and `secondary-on-dark` variants. A `primary` button is never placed on ink.

`mk-border` (1.2 on canvas) is decorative only: no component relies on it to show where a control is. The secondary button's outline uses `mk-brand`.

### Fonts and loading

- Add `@fontsource-variable/fraunces` at exactly `5.3.0`. In `marketing.css` declare two `@font-face` rules for `"Fraunces Variable"` (`font-style: normal` and `italic`) pointing at `files/fraunces-latin-wght-normal.woff2` and `files/fraunces-latin-wght-italic.woff2` (weight range 100 to 900, `font-display: swap`, Latin `unicode-range`). Write the `url()` as a relative path into `node_modules` (for example `../../node_modules/@fontsource-variable/fraunces/files/...`) unless a build shows the bare package path resolves. Confirm in build task 1 that both files exist and the total stays within 85 KB. Don't import the package's `index.css`, which pulls every subset.
- Fallback faces: two `@font-face` rules named `"Fraunces Fallback"`, one `font-style: normal` and one `italic`, each with `src: local("Georgia"), local("Noto Serif"), local("Times New Roman")` (Georgia on Windows, macOS and iOS; Noto Serif on Android; Times New Roman elsewhere) and `size-adjust`, `ascent-override`, `descent-override` and `line-gap-override`. The values come from `scripts/font-fallback.mjs`, a one off script that reads the Fraunces woff2 files and the Georgia metrics with `fontkit`, a dev dependency added for this script only, and prints the four overrides per style. Georgia is the reference, and the values are written into `marketing.css` with a comment naming the script.
- Preload: `Layout.astro` takes a `preloadSerif` prop (default `false`). When true, it adds a `<link rel="preload" as="font" type="font/woff2" crossorigin href=...>` for both the roman and the italic file, with the URLs from Vite `?url` imports so the hashed paths are right. Pages with a display or h1 heading above the fold (homepage, pricing, compare and alternatives, the preview page) set it. Their heroes usually hold an `MkHighlight`, so the italic is needed at once.
- Plus Jakarta Sans stays as `fonts.css` loads it today. Bricolage Grotesque stays declared but is only downloaded where a page still uses `font-display` (browsers fetch a face only when text uses it).

### Component contracts

All in `src/components/marketing/`, Astro only, no `client:*` directive, classes from the `mk` tokens. Extra attributes (`data-open-modal`, `target`, `rel`, `aria-*`, and the `data-cta` names feature 21 will add) pass through with `...rest`.

**Bands and focus.** `marketing.css` holds the shared rules that components read, so no component hard codes a band color:
- `.mk-band` sets `color: var(--color-mk-ink)` and `--mk-focus: var(--color-mk-focus)`.
- `[data-tone="canvas"]`, `[data-tone="tint"]` and `[data-tone="pink"]` set the band background (`mk-canvas`, `mk-tint`, `mk-pink`).
- `[data-tone="ink"]` sets background `mk-ink`, `color: var(--color-mk-on-dark)`, `--mk-focus: var(--color-mk-focus-on-dark)`, `--mk-overline: var(--color-mk-on-dark-subtle)`, `--mk-underline: var(--color-mk-pink-strong)` and `--mk-check: var(--color-mk-focus-on-dark)`. Light bands set `--mk-overline` and `--mk-check` to `mk-brand` and `--mk-underline` to `mk-brand`.
- `.mk-band :focus-visible { outline: 2px solid var(--mk-focus); outline-offset: 3px; }`
- Hover transitions sit inside `@media (prefers-reduced-motion: no-preference)`.

| Component | Props | Renders |
|---|---|---|
| `MkButton` | `variant`: `primary` \| `secondary` \| `on-dark` \| `secondary-on-dark` \| `link` (default `primary`); `size`: `md` \| `lg` (default `md`); `href?`; `type?` (`button` default); `class?` | `<a>` when `href` is set, else `<button>`. Pill shape. `primary` (light bands only): brand fill, white text, hover `brand-strong`. `secondary` (light bands only): transparent, 2 pixel `mk-brand` border, brand text, hover `mk-tint`. `on-dark` (ink band): white fill, ink text. `secondary-on-dark` (ink band): transparent, 2 pixel white border, white text. `md` is 44 pixels tall, `lg` is 52. `link`: inline brand text (`mk-on-dark` on ink), underlined on hover and focus, no minimum height (inline links are exempt from the WCAG 2.5.8 target size), same focus ring. |
| `MkSection` | `tone`: `canvas` \| `ink` \| `tint` \| `pink` (default `canvas`); `width`: `default` \| `narrow`; `as?`: `section` \| `div` \| `footer` \| `aside` (default `section`); `id?`; `labelledby?` (optional; set it to the section heading's `id` when the band is a `section` with a heading, so screen readers name the region) | A full width element with class `mk-band` and `data-tone`, padding `py-16 md:py-28 px-5 md:px-8`, and an inner `max-w-mk` (or `max-w-mk-narrow`) centred container. The band rules above switch text, overline, underline, check and focus colors. |
| `MkHeading` | `level`: 1 \| 2 \| 3; `size`: `display` \| `h1` \| `h2` \| `h3` (defaults to match `level`); `overline?`; `align`: `start` \| `center`; `id?` | An optional `<p>` overline (`text-mk-overline`, color `var(--mk-overline)`) above an `<hN>` with the size class and `font-mk-serif` or `font-mk-sans`. Default slot is the heading text, which may hold one `MkHighlight`. |
| `MkHighlight` | none (slot) | `<em>` in serif italic with an inline SVG underline stroke (color `var(--mk-underline)`, `aria-hidden="true"`, `focusable="false"`), stretched to the word's width. The word stays real text. |
| `MkCard` | `variant`: `plain` \| `quote`; `tone` (quote only): `brand` \| `pink` \| `ink`; `as?` (`div` default) | `plain`: white surface, `mk-border`, `rounded-mk-card`, `shadow-mk-card`, 24 to 32 pixel padding. `quote`: solid tone fill (`brand` and `ink` use on dark text), serif quote text, slot `cite` for the name and role. |
| `MkBadge` | `tone`: `brand` \| `pink` \| `ink` | Small pill, `mk-small` 700 text. `brand`: tint background, brand text. `pink`: pink background, ink text. `ink`: ink background, white text. |
| `MkFeatureRow` | `screenshot`: `{ name, alt, sizes?, priority? }` (passed straight to `MkScreenshotFrame`); `reverse?`; slot `overline`, `title`, default slot for text and buttons | Two columns from `md` (text and frame, the frame on the right unless `reverse`), rows spaced `gap-16 md:gap-24` when stacked by the page. On phones it stacks with text first, then the frame. |
| `MkScreenshotFrame` | `name` (a key in `src/data/screenshots.json`); `alt`; `sizes?` (default `(min-width: 1200px) 1200px, 100vw`); `priority?` (default `false`) | Reads `width`, `height` and the list of widths that exist from `screenshots.json` (a static import; an unknown `name` fails the build). `<picture>` with AVIF and WebP `srcset` built from those widths only, pointing at `public/screenshots/<name>-<width>.<ext>`. `width` and `height` are set to stop layout shift. `loading="lazy"` and `decoding="async"` unless `priority`, which sets `loading="eager"` and `fetchpriority="high"`. Wrapped in `rounded-mk-frame`, `shadow-mk-frame`, a 1 pixel `mk-border` and a slim browser bar (three dots, decorative). |
| `MkFaq` | `items`: `{ question: string; answer: string }[]`, where `answer` is trusted HTML written by us (links and emphasis allowed, rendered with `set:html`; never visitor input) | One `<details>`/`<summary>` per item, thin bordered rows, a plus icon drawn in CSS that turns to minus when open, with no transition. Rows open independently (no shared `name`). No heading inside `<summary>`; the section's `MkHeading` names the FAQ. No JavaScript; keyboard and screen reader work through the native element. |
| `MkCheckList` | `items`: `string[]` | `<ul>` with a check icon per item (`aria-hidden`, color `var(--mk-check)`: `mk-brand` on light bands, `mk-focus-on-dark` on ink, 3:1 or more either way). Item text takes the band's text color. |

### Screenshots

The adapter uses `imageService: "passthrough"` and the marketing pages render on demand, so Astro can't resize images. Screenshots are resized once and committed:
- `scripts/screenshots.mjs` (run with `npm run screenshots`) reads each PNG or JPG in `src/assets/screenshots/source/` and writes `public/screenshots/<name>-<width>.avif` and `.webp` at 640, 960, 1280 and 1920 wide with `sharp` (already a dependency), skipping widths larger than the source. It then writes `src/data/screenshots.json`, mapping each `name` (the file name without extension) to `{ width, height, widths }`, where `width` and `height` are the source's and `widths` lists only the files it wrote.
- The source files and the JSON are committed too, so a resize can be done again and the component never points at a missing file.
- The preview page's sample is a copy of `src/assets/light-dashboard.jpg` placed in the source folder as `sample-dashboard.jpg`. Features 18 to 20 take their own.

### Preview page

`src/pages/design-system.astro`, `export const prerender = false` (repo rule), using `Layout` with a new `noindex` prop that adds the robots meta, and `Astro.response.headers.set("X-Robots-Tag", "noindex")`, with a comment that the header only works while the page renders on demand. Sections: colors (swatch, token name, hex), type scale (each size with a sample line), spacing and radii, shadows, then each component in every variant, on each of the four bands. It doubles as the page for the manual keyboard, axe and Lighthouse checks.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Contrast test | each token's value | `parseTokens(css)` in `src/lib/marketing/tokens.ts`, a pure function (no imports, no path aliases, so plain `node --test` runs it) that reads every `--<group>-mk-*` declaration inside the `@theme static` block only; the test gets the CSS with `fs.readFileSync` |
| Contrast test | the pairs, the ratio each needs, the forbidden pairs | the *Allowed pairs* table and *Forbidden pairs* list, written as constants in the test |
| Contrast test and preview page | the contrast ratio | `contrastRatio(a, b)` in the same `tokens.ts` (WCAG 2.x relative luminance) |
| Preview page | every token name and value (colors, type scale, widths, radii, shadows, ease) | `parseTokens` on the CSS imported with Vite `?raw` (inlined at build, no file access on the Worker) |
| Preview page | each swatch's label color | `mk-ink` or `mk-on-dark`, whichever has the higher `contrastRatio` against the swatch |
| Font preload links | the hashed font URLs | Vite `?url` imports of the two Fontsource files |
| Fallback face overrides | `size-adjust` and the three overrides, per style | `scripts/font-fallback.mjs`, run once, values written into `marketing.css` |
| Screenshot `srcset` | file URLs and widths | `src/data/screenshots.json` `widths`, written by `npm run screenshots` |
| Screenshot `width` and `height` | intrinsic size | `src/data/screenshots.json`, from the source file |

**Key invariants**:
- `global.css`, `fonts.css`, `PortalLayout.astro` and the Starlight `customCss` are not edited by this feature or by features 17 to 20. Anything new for marketing goes in `marketing.css`.
- `marketing.css` adds one page wide rule (`scroll-padding-top` on `html`). Every other rule is scoped to `.mk-band` or `[data-tone]`, so a page keeps its current look until it is rebuilt with `MkSection`.
- New marketing code uses only `mk` tokens. The old names (`brand`, `ink`, `muted`, `display`, `pill`, `soft`, `card`) stay in use only where the current pages use them, and each restyle feature removes them from the pages it rewrites.
- Every color token is a hex value, and any text and background pair used on a page is in *Allowed pairs*.
- Marketing components ship no client JavaScript. An interaction that truly needs JS (the pricing toggle in feature 19) is a React island styled with `mk` classes.
- No component uses `mk-pink-strong` or `mk-border` as the only sign of a control or as a text background.
- Light only: no `.dark` rules in `marketing.css`.

**Security model**: no data, no sign in, no secrets. The preview page is public and holds only styles and sample text.

**Configuration required**: none. One new npm dependency, `@fontsource-variable/fraunces` pinned at `5.3.0`, and one dev dependency, `fontkit`, for the fallback metrics script (lockfile updated with both, since Cloudflare installs with `npm clean-install`).

**Critical test scenarios**:
- Happy path: open `/design-system` on a phone and on desktop; every token and component shows, on every band, verifies **AC-1**, **AC-4**, **AC-8**
- Contrast guard: change `--color-mk-subtle` to `#8a8597` and run `npm test`; the test fails and names the pairs. Change `--color-mk-brand` to `#b8a8ff`; brand on ink now passes, so the forbidden pair check fails (and the brand text pairs fail too), verifies **AC-5**
- No dashboard change: `git diff` on the four files is empty, and before and after screenshots of `/dashboard`, `/dashboard/start`, `/docs` and a blog post match, verifies **AC-2**
- Current pages unchanged: before and after screenshots of `/`, `/compare`, one `/compare/*`, `/alternatives`, one `/alternatives/*`, `/auth/sign-in`, `/auth/sign-up` and the 404 page match, verifies **AC-3**
- Keyboard: tab through the preview page; every button, link and FAQ row shows the ring, including on the ink band, and the FAQ opens with Enter and Space, verifies **AC-6**
- Font loading: in Chrome's phone emulation with slow 4G, the headline (with its highlighted word) swaps from the fallback with CLS of 0.01 or less, and the network tab shows only the two Fraunces Latin files, both preloaded, verifies **AC-7**
- Lighthouse and axe on the deployed preview page, verifies **AC-10**
- Reduced motion: with the OS setting on, hovering a button and opening an FAQ row change instantly, verifies **AC-11**
- Search engines: `curl -I` on `/design-system` shows `X-Robots-Tag: noindex`, and the HTML has the robots meta, verifies **AC-8**

## Build plan

Tracer Bullet: first one thin thread from token to rendered page, with its guard test, then widen.

1. **Thread.** First take the before screenshots (Playwright CLI, third party scripts blocked) of every page named in AC-2 and AC-3. Add `@fontsource-variable/fraunces@5.3.0` and confirm the two file names and sizes; create `marketing.css` (imports `global.css`, the `@theme static` color tokens, the Fraunces faces, the `mk-display` and `mk-body` sizes, the band rules); switch `Layout.astro` to import it and add the `noindex` and `preloadSerif` props; build `MkSection`, `MkHeading` and `MkButton`; create `/design-system` showing the colors, one heading and the buttons on all four bands; write `src/lib/marketing/tokens.ts` (`parseTokens`, `contrastRatio`) and `tests/marketing/contrast.test.ts`. Satisfies **AC-1**, **AC-3**, **AC-5**, **AC-8**
2. **Full tokens and focus.** The rest of the type scale, widths, radii, shadows, motion and `scroll-padding-top`; the focus ring rules for light bands and the ink band; reduced motion; `scripts/font-fallback.mjs` and both fallback faces; the preload links. Run a local Lighthouse mobile pass on the preview page here, so a font or speed problem shows before deploy. Satisfies **AC-1**, **AC-6**, **AC-7**, **AC-11**
3. **Content components.** `MkHighlight` (with the SVG underline), `MkCard`, `MkBadge`, `MkCheckList`, `MkFaq`, each added to the preview page in every variant and band. Satisfies **AC-4**, **AC-6**, **AC-8**
4. **Screenshots.** `scripts/screenshots.mjs`, `npm run screenshots`, the source folder with `sample-dashboard.jpg`, `src/data/screenshots.json`, then `MkScreenshotFrame` and `MkFeatureRow`, shown on the preview page. Satisfies **AC-4**, **AC-7**
5. **Documentation.** `src/components/marketing/README.md`. Satisfies **AC-9**
6. **Checks.** `git diff` on the four files AC-2 names; after screenshots and the comparison for AC-2 and AC-3; deploy; Lighthouse mobile, axe, keyboard pass and the font loading check on the deployed preview page. Satisfies **AC-2**, **AC-3**, **AC-7**, **AC-10**

## Consequences

**Positive**:
- Features 17 to 20 restyle pages by composing ten components and one token set, with no copied styles.
- The dashboard and docs can't drift, because nothing they load is edited.
- Contrast is guarded by a test, not by memory; a later token change that breaks AA fails `npm test`.
- Fraunces with only the weight axis costs about 82 KB, and the italic loads only on pages that use a highlight.

**Negative / tradeoffs**:
- Two sets of marketing names live side by side (`brand` and `mk-brand`) until feature 20 finishes. Someone could pick the old one in new code; the README and the invariant say not to.
- Marketing pages still carry the whole of `global.css`, including the Starlight sidebar rules and shadcn tokens they don't need. Splitting it was rejected to protect the dashboard.
- Screenshots need a manual `npm run screenshots` step and committed image files, since the adapter can't resize at request time.
- The `bg-muted` quirk (the dashboard's `muted` is the marketing gray `#6b6776`, not shadcn's light gray) stays as it is.
- Hand written `clamp` sizes and fallback metrics are numbers someone must keep in step if the fonts change.

**Neutral**:
- `Layout.astro` gains two props (`noindex`, `preloadSerif`), both off by default.
- A new `tests/marketing/` folder joins `tests/onboarding/`, and `src/data/screenshots.json` is a generated file that is committed.

## Follow-up

- [ ] When feature 20 finishes, check that no marketing page uses the old token names, then note in `rarebooks-site/AGENTS.md` that new marketing code uses only `mk` tokens and `src/components/marketing/` (for `/sync`).
- [ ] The dashboard restyle (deferred in the scope) should fix the `bg-muted` and `text-muted` quirk in `global.css` and drop `@fontsource-variable/inter` if nothing uses it.
- [ ] Feature 21 (conversion tracking) can rely on `MkButton` passing `data-cta` through.
- [ ] `tailwindcss` and `web-perf` aren't listed in `rarebooks-site/AGENTS.md` `## Agent skills`. They're project wide for that repo's styling and speed, so they belong in its root `AGENTS.md`.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
