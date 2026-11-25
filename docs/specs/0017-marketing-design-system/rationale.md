# 0017. Marketing design system: rationale

## Context

Slice 10 gives the public pages of `rarebooks.cc` a fresh look with the feel of Wave's marketing site: bright, friendly and roomy, with rounded buttons, real product screenshots and alternating feature rows. It keeps the RareBooks purple, logo and copy. Four features (nav and footer, homepage, pricing, compare and alternatives) restyle pages, and each needs the same colors, type, spacing and building blocks. Without a shared base, each one invents its own values and the pages drift apart.

The site is one Astro app on one Cloudflare Worker, and three surfaces share a single stylesheet today. `src/styles/global.css` is imported by the marketing `Layout.astro`, by the customer dashboard's `PortalLayout.astro`, and by Starlight as `customCss` for the docs and blog. It mixes the current marketing tokens (`brand`, `ink`, `muted`, `display`, `pill`, `soft`, `card`) with the shadcn tokens the dashboard uses. The two sets already overlap: `--color-muted` is the marketing gray `#6b6776`, so shadcn's own `muted` never gets set, and dashboard code relies on that (`dashboard-header.tsx` uses `bg-muted` with light text). Shared components also use the marketing names: `dialog.tsx` uses `text-ink`, `font-display` and `bg-brand-soft`, and `nav-main.tsx` uses `bg-brand`. The scope requires that `/dashboard` and the docs look the same as before.

Speed and access are hard limits. Every page must stay fast on mobile (good Core Web Vitals) and meet WCAG 2.2 AA. The adapter runs with `imageService: "passthrough"` and the marketing pages render on demand, so there is no automatic image resizing. Fonts are self hosted through Fontsource. The repo has `node --test` unit tests and `astro check`, with no browser test runner. Wave's site can't be reached from the build container, so the look was studied from screenshots the engineer captured.

## Options considered

### Option 1: Put everything in `global.css` with a prefix

Add the new tokens and base rules to `global.css` under an `mk` prefix, and leave every layout importing the one file.

**Pros**:
- One stylesheet, one import, nothing new to wire up.
- Tailwind generates every class in one place.

**Cons**:
- The dashboard and docs download every marketing rule and the Fraunces faces' declarations.
- Any later edit to marketing base rules (body background, `scroll-padding-top`, focus rings) lands on the dashboard too, which breaks the "looks the same" rule the first time someone forgets to scope it.
- The AC-2 guard ("global.css unchanged") becomes impossible, so there's no cheap way to prove the dashboard is untouched.

### Option 2: A separate `marketing.css` layered on `global.css` (chosen)

`marketing.css` imports `global.css`, then adds `mk` tokens, the Fraunces faces and marketing base rules. Only the marketing layouts import it.

**Pros**:
- Nothing the dashboard or docs load changes, and that's checkable with an empty `git diff`.
- The old token names keep working on the current pages, so features 17 to 20 can restyle one page at a time.
- Marketing base rules can be global within marketing pages without scoping tricks.

**Cons**:
- Marketing pages still carry all of `global.css`, including rules they don't use.
- Two sets of marketing names coexist until the last restyle ships.

### Option 3: Split `global.css` into shared, dashboard and marketing files

Move shadcn tokens to a dashboard file, shared tokens to a base file, and marketing tokens to their own, then fix the `muted` overlap.

**Pros**:
- The cleanest end state: each surface loads only what it uses.
- Fixes the `muted` quirk properly.

**Cons**:
- Touches every layout and the Starlight config, and fixing `muted` changes how the dashboard looks, which this feature must not do.
- Much larger change for a Beta slice whose goal is the marketing pages.

### Option 4: Override shadcn variables inside a `.marketing` wrapper

Wrap marketing pages in a class that redefines `--primary`, `--background` and the rest, so shadcn components restyle themselves.

**Pros**:
- shadcn components on marketing pages (the contact dialog) pick up the new look for free.

**Cons**:
- Scoping mistakes leak: a portal rendered outside the wrapper (dialogs, toasts) loses the overrides.
- Ties the marketing look to shadcn's token meanings, which differ from the marketing ones (shadcn's `accent` is a background, not a color accent).

## Rationale

The forces that decide this are the dashboard rule and the shared stylesheet. Because `global.css` is loaded by all three surfaces and the dashboard leans on the current marketing names and the `muted` quirk, any edit to it is a dashboard change. Option 2 is the only choice that leaves every file the dashboard and docs load untouched, and makes that easy to prove. Option 3 is the better long term shape, and it fits the deferred dashboard restyle, where changing the dashboard's look is the point. Option 1 fails the dashboard rule by design, and Option 4 trades it for fragile scoping.

The engineer chose each part of the look in the design conversation:
- A serif for headlines and Plus Jakarta Sans for body text, which gives Wave's warm editorial feel.
- Fraunces as that serif. It's friendly, has a real italic for the highlighted word, and its weight only variable files are small (36.6 KB roman, 45.7 KB italic, Latin subset).
- Self hosted fonts, with a preload of the roman file and a size adjusted fallback, so the hero headline swaps without shifting the layout.
- The italic word with an SVG underline, rather than a marker band, or the current gradient text (which fails contrast on its light end).
- All four bands: warm off white, deep ink, brand tint and pink.
- Keeping the `#5b3df5` purple, which already passes AA for white text at 6.1:1.
- Light only, matching both Wave and the current pages.
- Astro components, so marketing pages ship no JavaScript for layout.
- A public, noindex preview page plus a README.
- A unit test on token pairs instead of a new browser test runner.
- Keeping the Wave screenshots out of the repo.

Calls made in writing the spec, each with its runner up:
- **Hex color tokens, not oklch.** Pick: hex, so the contrast test parses them with a regex and a 20 line WCAG function. Runner up: oklch with a color library, which adds a dependency for no visual gain.
- **Pre resized, committed screenshots.** Pick: `sharp` (already a dependency) through `npm run screenshots`, with AVIF and WebP at four widths. Runner up: switching the adapter's image service, which only helps prerendered pages, and these pages render on demand.
- **Text before the frame on phones in a feature row.** Pick: text first, so the claim reads before the image loads, as on Wave's phone layout. Runner up: keep alternation on phones, which puts some images first and pushes text below the fold.
- **44 pixel minimum button height.** Pick: 44, well above WCAG 2.2's 24 pixel target size and in line with phone guidelines. Runner up: 40, which looks lighter but is harder to tap.
- **Native `<details>` for the FAQ.** Pick: native, which is keyboard and screen reader ready with no JavaScript. Runner up: the shadcn collapsible as an island, which adds JS for the same behavior.
- **Fluid `clamp` type sizes.** Pick: `clamp`, which needs one token per size, not a size per breakpoint. Runner up: fixed sizes per breakpoint, which means more tokens and jumps between widths.
- **Wave patterns described in words, not images.** Pick: describe the patterns in the spec, so the spec keeps the reference without holding another company's pages. Runner up: committing the screenshots under `docs/`.
