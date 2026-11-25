# Verify: Marketing design system · spec 0017 · updated 2026-11-25 (last run 2026-11-25, local dev and preview: BLOCKED on the three unticked steps)
_Steps derived from spec 0017 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. All paths are in the `rarebooks-site` repo._

## UI / manual
- [x] Open `/design-system` at 1280 and 390 pixels wide → every color swatch (name and hex), the type scale, spacing, widths, radii, shadows and ease show, and every component shows in each variant on the canvas, tint, pink and ink bands → AC-1, AC-4, AC-8
- [x] Tab through `/design-system` → every button, link button and FAQ summary shows a 2 px solid ring offset 3 px: `#5b3df5` on light bands and inside white cards, `#c9bdfb` on the ink band; clicking with a mouse shows no ring → AC-6
- [x] Measure the buttons → `md` is 44 px tall and `lg` 52 px → AC-6
- [x] Focus an FAQ row and press Enter, then Space → it opens, then closes; the plus becomes a minus with no animation → AC-4, AC-6, AC-11
- [x] Turn on reduced motion in the OS, hover a button and open an FAQ row → both change instantly (computed `transition-duration` is `0s`) → AC-11
- [x] In Chrome phone emulation (Moto G Power, slow 4G), load `/design-system` → CLS from fonts is 0.01 or less, the Network tab shows only the two Fraunces Latin files, and both are preloaded → AC-7
- [x] Take before and after screenshots (Playwright, 1280 and 390, GTM, tawk.to, Clerk and Turnstile blocked) of `/`, `/compare`, `/compare/gnucash`, `/alternatives`, `/alternatives/gnucash`, `/auth/sign-in`, `/auth/sign-up` and the 404 page → pixel identical → AC-3
- [ ] Take the same screenshots of `/dashboard`, `/dashboard/start` (signed in), a docs page and a blog post → pixel identical, or each difference listed with its cause → AC-2
- [ ] On the deployed site, run Lighthouse mobile and axe DevTools on `/design-system` → Performance 90 or more, Accessibility 100, no axe violations → AC-10
- [x] Search the site's pages for a link to `/design-system` → none → AC-8

## Commands
- [x] `npm test` → the marketing contrast tests pass → AC-5
- [x] Change `--color-mk-subtle` to `#8a8597`, then run `npm test` → "every allowed pair" fails and names the four subtle pairs; revert → AC-5
- [x] Change `--color-mk-brand` to `#b8a8ff`, then run `npm test` → the allowed pair and forbidden pair tests both fail; revert → AC-5
- [x] `git diff --stat <base> -- src/styles/global.css src/styles/fonts.css src/layouts/PortalLayout.astro astro.config.mjs` → empty → AC-2
- [ ] `curl -sI https://rarebooks.cc/design-system | grep -i x-robots-tag` → `noindex`; the HTML has `<meta name="robots" content="noindex, nofollow">` → AC-8
- [x] `npm run build`, then list `dist/client/_astro/fraunces-*` → two files totalling 85 KB or less; the preload `href`s on `/design-system` match the hashed names in the Layout CSS → AC-7
- [x] `grep -c -- '--color-mk-canvas' dist/client/_astro/PortalLayout.*.css` → 0 (the dashboard CSS has no `mk` tokens) → AC-2
- [x] Read `src/components/marketing/README.md` → each token group, each of the ten components with props and an example, and the Key invariants → AC-9

## Value sourcing
- [x] Contrast test token values: add a `--color-mk-test: #000000;` line outside the `@theme static` block → the test ignores it (`parseTokens` reads that block only); a non hex value inside the block fails "6 digit hex" → AC-5
- [x] Contrast test pairs and ratios: they come from the constants in `tests/marketing/contrast.test.ts`, which match the spec's Allowed pairs table and Forbidden pairs list → AC-5
- [x] `contrastRatio`: `#000000` on `#ffffff` gives 21, and the result is the same either way round → AC-5
- [x] Preview page tokens: change one token in `marketing.css` and reload `/design-system` (after a rebuild in production) → the page shows the new value with no other edit, because it reads the CSS through `?raw` → AC-8
- [x] Swatch label color: each light swatch (canvas, tint, pink) has an ink label; each dark swatch (ink, brand, brand-strong, subtle) has a white label → AC-8
- [x] Font preload URLs: in a production build, the preload `href`s equal the CSS `url()`s (same hash) → AC-7
- [x] Fallback overrides: `node scripts/font-fallback.mjs` prints the same four values per style as the `"Fraunces Fallback"` faces in `marketing.css` → AC-7
- [x] Screenshot `srcset`: it lists only the widths in `src/data/screenshots.json` (640, 960, 1280 for `sample-dashboard`, with no 1920 since the source is 1366 wide), and every listed file returns 200 → AC-4, AC-7
- [x] Screenshot width and height: the `<img>` carries 1366 × 695, the source's size → AC-7
- [x] An unknown `name` on `MkScreenshotFrame` fails `astro check` and throws when rendered → AC-4

## Acceptance-criteria coverage
- AC-1: preview page check, contrast tests · AC-2: dashboard and docs screenshots, git diff, PortalLayout CSS grep · AC-3: marketing page screenshots · AC-4: preview page, FAQ keyboard, screenshot checks · AC-5: npm test and the two token changes · AC-6: keyboard pass and button heights · AC-7: font loading, build sizes, fallback values · AC-8: preview page, robots header and meta, no links · AC-9: README · AC-10: deployed Lighthouse and axe · AC-11: reduced motion
