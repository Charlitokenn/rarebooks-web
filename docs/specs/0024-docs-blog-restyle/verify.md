# Verify: Docs and blog restyle · spec 0024 · updated 2026-11-26
_Steps derived from spec 0024 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Build notes from /develop (2026-11-26)

- Before snapshot: `tests/docs/docs-head-snapshot.json` (47 docs routes) was written from the build before any change; the build after matches it exactly.
- AC-13 before and after screenshots (local `astro preview` on workerd, third party scripts blocked): 9 of 10 match pixel for pixel. `home-390` differs only where two lazy loaded homepage screenshots had not loaded yet in the before capture; text and layout are identical. Retake on the deployed site to close this.
- AC-11: Clerk's integration did add its page script to docs pages. `src/lib/docs/clerkGuard.ts` (wired in `astro.config.mjs`) now loads Clerk only off the docs; checked: `/pricing` and `/auth/sign-in` still load Clerk, docs pages make no Clerk request.
- AC-5: Starlight 0.39 has only Ctrl+K and Cmd+K, so `DocsHeader` adds the `/` shortcut.
- AC-12: no page in `financial-reports` has a code block. The only docs page with both a table and a code block is `/settings/print-templates/`; use it as the long reference page.
- AC-3 header by width (spec update of 2026-11-26), built and checked locally: at 320, 390, 799, 800, 1024, 1151, 1152, 1215, 1216 and 1920 pixels the bar and the sidebar foot block never overflow, each control is visible exactly once, at most one landmark is named "Main", and at 1024 Tab goes bar, sidebar list, sidebar foot, then the page. Search is the icon button below 1216 and the full field from 1216.

## /check verify results (2026-11-26, local `astro preview` on workerd; the deployed site still serves the old docs)

Verdict: FAIL. Evidence in the session scratchpad (`verify/ledger.txt`, `verify/axe.txt`, `verify/lh.txt`).

- AC-3 not met: at 1152 px and wider axe reports `landmark-unique` because the bar's nav and Starlight's sidebar nav are both named "Main" (Starlight's `sidebarNav.accessibleLabel` is "Main"). New with the restyle.
- AC-6 not met: font driven layout shift on the docs home is 0.011 to 0.020 (Lighthouse mobile, 6 runs); the shift is Plus Jakarta Sans 400, 600 and 700 swapping in (no size matched fallback, not preloaded). The live old docs home measured 0.000.
- AC-12 not met: axe on `/settings/print-templates/` at 390 px reports `scrollable-region-focusable` (two wide tables) and `landmark-unique` (an Expressive Code block); both also exist on the live old site. `/getting-started/using-rarebooks-on-a-phone/` in dark has a 0.238 shift from Markdown screenshots with no width and height. Accessibility scored 100 on all 18 local runs. Performance can't be judged locally (the preview serves files uncompressed; the live site uses Brotli): local best scores 87, 78, 79 (light) and 87, 77, 66 (dark). Deployed runs are still owed.
- AC-13: all 10 screenshots match the before set pixel for pixel on the local preview; the deployed retake is still owed.
- Met with evidence: AC-1, AC-2 (via tests), AC-4, AC-5, AC-7, AC-9, AC-10, AC-11, AC-14, AC-15; AC-8 frames follow the mapping and axe found no contrast issue in code blocks.

## /check verify results, second run (2026-11-26, local `astro preview` on workerd at `ba09cb0`; the deployed site still serves the old docs)

Verdict: BLOCKED. Every check that can run locally passed; AC-12 Performance can only be judged on the deployed site.

- AC-12 blocked: Lighthouse mobile best of 3, local: docs home 85 light, 84 dark; phone page 78, 78; `/settings/print-templates/` 77, 77. Accessibility 100 on all 18 runs, CLS 0.001 or less. The local preview sends no `content-encoding`; the live site sends `br`, so these scores understate the deployed result. axe clean on the three pages at 390, 1024 and 1280 in both themes.
- AC-13: 9 of 10 match the before set pixel for pixel. `home-1280` differs only inside the first homepage screenshot frame (41,2318 to 607,2777): in the before capture its lazy loaded image had not arrived (an empty frame), in the after capture it shows. Same result on 3 retakes. Cause: capture timing, not the change; needs your acceptance, or a retake of both sets on the deployed site.
- "Open `/` on the deployed site" was run on the local preview, since the deployed site still has the old docs.
- Not run: the Value sourcing edits that change constants and rebuild (nav label, `AppConfig.legal.approved`, one `mk-docs-*` token), and signing in before opening a docs page.
- Observed, not a failure: all seven sidebar groups render open. The `collapsed: true` in the config sits on `autogenerate`, which Starlight applies to subfolders only, and there are none. The live old docs also show all seven open.

## /debug fixes for the FAIL (2026-11-26, local `astro preview` on workerd)

- AC-3 `landmark-unique` from 1152 px: Starlight's sidebar nav was also named "Main". `src/content/i18n/en.json` (new `i18n` collection in `content.config.ts`) renames it "Docs". axe clean at 1024 and 1280 on the three AC-12 pages, both themes.
- AC-6 font shift: size adjusted `Plus Jakarta Sans Fallback` faces (400, 600, 700, Arial or Liberation Sans as reference, values from `scripts/font-fallback-sans.mjs`) in `docs.css`, added to `--sl-font`. Docs home CLS now 0.000 to 0.001 (Lighthouse mobile, 6 runs).
- AC-12 axe: `src/lib/docs/rehypeDocsContent.ts` gives tables `tabindex="0"` (scrollable-region-focusable) and gives `/images/...` Markdown images their real width and height (the phone page CLS drops from 0.238 to 0.000). Expressive Code now wraps long lines (`defaultProps: { wrap: true }`), so no unnamed `role="region"` blocks (landmark-unique). axe clean at 390, 1024 and 1280 on all three pages in both themes; Accessibility 100 on all 18 runs.
- Still owed: Performance on the deployed site (local best, uncompressed: 87, 78, 77) and the deployed AC-13 retake.

## UI / manual
- [x] Open `/` on the deployed site, click Docs in the marketing nav → docs home with the mk header, logo, four links (Docs underlined), search, social icons, theme switch, Sign in, Start free trial → AC-3
- [x] Switch the theme to Dark, then Auto with the device set to dark and light → page, sidebar, header, code blocks and asides follow; the Start free trial button stays white on brand purple → AC-3, AC-7, AC-8
- [x] At 320, 390, 799, 800, 1024, 1151, 1152, 1215, 1216 and 1920 pixels wide: nothing in the bar or the sidebar foot block is cut off or scrolls sideways, and each control shows exactly once (bar, sidebar foot, or the open phone menu) → AC-3
- [x] From 800 to 1151 pixels: the bar holds the logo, search icon, Sign in and Start free trial; the sidebar foot holds the nav links (a nav named "Site"), the social icons and the theme switch, with no Sign in row; from 1152 the sidebar foot block is gone and the bar holds everything → AC-3
- [x] At 1024 by keyboard: Tab goes bar, sidebar list, sidebar foot, then the page; the Skip to content link jumps past the sidebar → AC-3
- [x] At 390 pixels, by keyboard only: Tab to the menu button, Enter opens it, Tab reaches the four links, Sign in, Start free trial, social links and theme switch (each 44 pixels tall), Escape closes it and returns focus to the button → AC-3, AC-5
- [x] Press `/` and then Ctrl+K on a docs page → search opens; type "invoice", Tab to a result, Enter → that page opens → AC-5
- [x] At 390 pixels open "On this page", pick a heading → the page jumps to it → AC-5
- [x] Use the Previous and Next links at the page foot → they navigate; each is at least 44 pixels tall; hover shows the accent border → AC-5
- [x] The current page in the sidebar is marked with the brand color and has `aria-current="page"`; the seven groups collapse as configured → AC-5
- [x] Every header, menu, footer strip and pagination control shows a 2 pixel focus outline on Tab → AC-3
- [x] Footer: edit link and last updated (if set), pagination, then logo, the Product, Compare and Resources link groups (Legal only once approved), and "© <year> RareBooks. All rights reserved."; no "Built with Starlight"; the strip is at most 240 pixels tall at 1280 wide → AC-4
- [x] The page title is in Fraunces, body in Plus Jakarta Sans, code in the system monospace; DevTools Network shows only the Fraunces roman file (no italic, Inter or Bricolage) → AC-6
- [x] With `prefers-reduced-motion: reduce` emulated, hover header links, footer links and pagination → no transitions → AC-14
- [ ] Lighthouse mobile (best of 3) on `/getting-started/getting-started-with-rarebooks/`, `/settings/print-templates/` and `/getting-started/using-rarebooks-on-a-phone/`, light and dark: Performance 90 or more, Accessibility 100, axe clean (no contrast issue in code blocks); font CLS on the docs home 0.01 or less → AC-6, AC-8, AC-12
- [x] Before and after Playwright screenshots of `/`, `/pricing`, `/compare/quickbooks`, `/auth/sign-in`, `/welcome` at 1280 and 390 (tawk.to, PostHog, GTM, Clerk blocked; year and dates masked) match or each difference is listed here → AC-13

## Commands
- [x] `npm test` (in `rarebooks-site`, after `npm run build`) → all pass, including `tests/docs/*` and `tests/marketing/contrast.test.ts` → AC-1, AC-7, AC-10, AC-11
- [x] Change `--color-mk-dark-text` to `#7d7690` in `mk-tokens.css`, run `node --test tests/docs/contrast.test.ts` → fails; revert → AC-7
- [x] `git diff main -- src/layouts/Layout.astro src/layouts/WelcomeLayout.astro` → empty → AC-13
- [x] `grep -c starlight-blog package.json package-lock.json` → 0 and 0 → AC-9
- [x] On a `wrangler` preview: `curl -I /blog` and `/blog/anything` → 404; `/blog/rarebooks-vs-quickbooks-desktop` → 301 to `/compare/quickbooks` in one hop → AC-9
- [x] View source of a docs page: the three social links point at `AppConfig.socials` and the Instagram label reads "Instagram" → AC-10
- [x] `src/components/marketing/README.md` names `mk-tokens.css`, `docs.css` and the docs rules → AC-15

## Value sourcing
- [ ] Change a label in `navLinks` locally and rebuild → the docs header and phone menu show it → nav links source
- [x] Docs header Sign in goes to `/auth/sign-in`, Start free trial to `/auth/sign-up` → `signInPath`, `AppConfig.urls.signUpUrl`
- [ ] Sign in, then open a docs page → still Sign in and Start free trial (prerendered, by design) → signed out decision
- [ ] Set `AppConfig.legal.approved` to true locally and rebuild → the Legal group appears in the docs footer strip → `visibleFooterColumns`
- [x] The copyright year equals the build year → `new Date().getFullYear()` at build time
- [x] The preloaded font URL equals the hashed Fraunces roman file the page title uses → `?url` import
- [ ] Change one `mk-docs-*` token locally → the docs color changes with no other edit → `mk-tokens.css` mapping

## Acceptance-criteria coverage
- AC-1 tests, Commands 1 · AC-2 Fonts and Network step, no hex test · AC-3 UI 1 to 5, 9 · AC-4 UI 10 · AC-5 UI 4 to 8 · AC-6 UI 11, 13 · AC-7 UI 2, Commands 1 and 2 · AC-8 UI 2, 13 · AC-9 Commands 4 and 5 · AC-10 Commands 1 and 6 · AC-11 Commands 1 · AC-12 UI 13 · AC-13 UI 14, Commands 3 · AC-14 UI 12 · AC-15 Commands 7
