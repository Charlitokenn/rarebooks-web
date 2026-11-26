# Verify: Docs and blog restyle · spec 0024 · updated 2026-11-26
_Steps derived from spec 0024 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Build notes from /develop (2026-11-26)

- Before snapshot: `tests/docs/docs-head-snapshot.json` (47 docs routes) was written from the build before any change; the build after matches it exactly.
- AC-13 before and after screenshots (local `astro preview` on workerd, third party scripts blocked): 9 of 10 match pixel for pixel. `home-390` differs only where two lazy loaded homepage screenshots had not loaded yet in the before capture; text and layout are identical. Retake on the deployed site to close this.
- AC-11: Clerk's integration did add its page script to docs pages. `src/lib/docs/clerkGuard.ts` (wired in `astro.config.mjs`) now loads Clerk only off the docs; checked: `/pricing` and `/auth/sign-in` still load Clerk, docs pages make no Clerk request.
- AC-5: Starlight 0.39 has only Ctrl+K and Cmd+K, so `DocsHeader` adds the `/` shortcut.
- AC-12: no page in `financial-reports` has a code block. The only docs page with both a table and a code block is `/settings/print-templates/`; use it as the long reference page.
- AC-3 header by width (spec update of 2026-11-26), built and checked locally: at 320, 390, 799, 800, 1024, 1151, 1152, 1215, 1216 and 1920 pixels the bar and the sidebar foot block never overflow, each control is visible exactly once, at most one landmark is named "Main", and at 1024 Tab goes bar, sidebar list, sidebar foot, then the page. Search is the icon button below 1216 and the full field from 1216.

## UI / manual
- [ ] Open `/` on the deployed site, click Docs in the marketing nav → docs home with the mk header, logo, four links (Docs underlined), search, social icons, theme switch, Sign in, Start free trial → AC-3
- [ ] Switch the theme to Dark, then Auto with the device set to dark and light → page, sidebar, header, code blocks and asides follow; the Start free trial button stays white on brand purple → AC-3, AC-7, AC-8
- [ ] At 320, 390, 799, 800, 1024, 1151, 1152, 1215, 1216 and 1920 pixels wide: nothing in the bar or the sidebar foot block is cut off or scrolls sideways, and each control shows exactly once (bar, sidebar foot, or the open phone menu) → AC-3
- [ ] From 800 to 1151 pixels: the bar holds the logo, search icon, Sign in and Start free trial; the sidebar foot holds the nav links (a nav named "Site"), the social icons and the theme switch, with no Sign in row; from 1152 the sidebar foot block is gone and the bar holds everything → AC-3
- [ ] At 1024 by keyboard: Tab goes bar, sidebar list, sidebar foot, then the page; the Skip to content link jumps past the sidebar → AC-3
- [ ] At 390 pixels, by keyboard only: Tab to the menu button, Enter opens it, Tab reaches the four links, Sign in, Start free trial, social links and theme switch (each 44 pixels tall), Escape closes it and returns focus to the button → AC-3, AC-5
- [ ] Press `/` and then Ctrl+K on a docs page → search opens; type "invoice", Tab to a result, Enter → that page opens → AC-5
- [ ] At 390 pixels open "On this page", pick a heading → the page jumps to it → AC-5
- [ ] Use the Previous and Next links at the page foot → they navigate; each is at least 44 pixels tall; hover shows the accent border → AC-5
- [ ] The current page in the sidebar is marked with the brand color and has `aria-current="page"`; the seven groups collapse as configured → AC-5
- [ ] Every header, menu, footer strip and pagination control shows a 2 pixel focus outline on Tab → AC-3
- [ ] Footer: edit link and last updated (if set), pagination, then logo, the Product, Compare and Resources link groups (Legal only once approved), and "© <year> RareBooks. All rights reserved."; no "Built with Starlight"; the strip is at most 240 pixels tall at 1280 wide → AC-4
- [ ] The page title is in Fraunces, body in Plus Jakarta Sans, code in the system monospace; DevTools Network shows only the Fraunces roman file (no italic, Inter or Bricolage) → AC-6
- [ ] With `prefers-reduced-motion: reduce` emulated, hover header links, footer links and pagination → no transitions → AC-14
- [ ] Lighthouse mobile (best of 3) on `/getting-started/getting-started-with-rarebooks/`, `/settings/print-templates/` and `/getting-started/using-rarebooks-on-a-phone/`, light and dark: Performance 90 or more, Accessibility 100, axe clean (no contrast issue in code blocks); font CLS on the docs home 0.01 or less → AC-6, AC-8, AC-12
- [ ] Before and after Playwright screenshots of `/`, `/pricing`, `/compare/quickbooks`, `/auth/sign-in`, `/welcome` at 1280 and 390 (tawk.to, PostHog, GTM, Clerk blocked; year and dates masked) match or each difference is listed here → AC-13

## Commands
- [ ] `npm test` (in `rarebooks-site`, after `npm run build`) → all pass, including `tests/docs/*` and `tests/marketing/contrast.test.ts` → AC-1, AC-7, AC-10, AC-11
- [ ] Change `--color-mk-dark-text` to `#7d7690` in `mk-tokens.css`, run `node --test tests/docs/contrast.test.ts` → fails; revert → AC-7
- [ ] `git diff main -- src/layouts/Layout.astro src/layouts/WelcomeLayout.astro` → empty → AC-13
- [ ] `grep -c starlight-blog package.json package-lock.json` → 0 and 0 → AC-9
- [ ] On a `wrangler` preview: `curl -I /blog` and `/blog/anything` → 404; `/blog/rarebooks-vs-quickbooks-desktop` → 301 to `/compare/quickbooks` in one hop → AC-9
- [ ] View source of a docs page: the three social links point at `AppConfig.socials` and the Instagram label reads "Instagram" → AC-10
- [ ] `src/components/marketing/README.md` names `mk-tokens.css`, `docs.css` and the docs rules → AC-15

## Value sourcing
- [ ] Change a label in `navLinks` locally and rebuild → the docs header and phone menu show it → nav links source
- [ ] Docs header Sign in goes to `/auth/sign-in`, Start free trial to `/auth/sign-up` → `signInPath`, `AppConfig.urls.signUpUrl`
- [ ] Sign in, then open a docs page → still Sign in and Start free trial (prerendered, by design) → signed out decision
- [ ] Set `AppConfig.legal.approved` to true locally and rebuild → the Legal group appears in the docs footer strip → `visibleFooterColumns`
- [ ] The copyright year equals the build year → `new Date().getFullYear()` at build time
- [ ] The preloaded font URL equals the hashed Fraunces roman file the page title uses → `?url` import
- [ ] Change one `mk-docs-*` token locally → the docs color changes with no other edit → `mk-tokens.css` mapping

## Acceptance-criteria coverage
- AC-1 tests, Commands 1 · AC-2 Fonts and Network step, no hex test · AC-3 UI 1 to 5, 9 · AC-4 UI 10 · AC-5 UI 4 to 8 · AC-6 UI 11, 13 · AC-7 UI 2, Commands 1 and 2 · AC-8 UI 2, 13 · AC-9 Commands 4 and 5 · AC-10 Commands 1 and 6 · AC-11 Commands 1 · AC-12 UI 13 · AC-13 UI 14, Commands 3 · AC-14 UI 12 · AC-15 Commands 7
