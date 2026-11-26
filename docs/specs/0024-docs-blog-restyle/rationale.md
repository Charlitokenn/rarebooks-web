# 0024. Docs and blog restyle: rationale

The decision record for [index.md](index.md). `/develop` builds from `index.md`; this file says why.

## Context

The marketing pages of `rarebooks.cc` were rebuilt on the `mk` design system (spec 0017) with a new nav and footer (spec 0018). The Starlight docs, served at the site root from the same Astro app, were left on purpose with their old look: Starlight's default blue accent and gray, Starlight's own header with a site title and social icons, a custom accordion sidebar, and `global.css` (Tailwind, shadcn, Inter, Bricolage and the sidebar rules) as the only custom stylesheet. A visitor who clicks Docs in the marketing nav lands on what looks like a different product.

The `mk` tokens live inside `marketing.css`, which imports `global.css` and adds marketing band rules. That file is light only by design, while Starlight readers have a light, dark and auto switch today. Docs pages are prerendered (built once, with no Clerk session), unlike the marketing pages, which render on each request and decide signed in or signed out on the server. Spec 0022 worked to keep marketing pages fast on phones, and the docs carry no third party scripts today.

The `starlight-blog` plugin is installed and its schema extends the docs collection, but the plugin is switched off and there are no posts. The old `/blog/rarebooks-vs-*` addresses already redirect to the comparison pages (spec 0021). The scope also mentioned `/dashboard`, which spec 0023 has since replaced with `/welcome`.

Left alone, the docs keep looking unrelated to the marketing site, and any brand change has to be made twice.

## Options considered

### Option 1: Point Starlight's `customCss` at `marketing.css`

Swap `global.css` for `marketing.css` in the Starlight config and add `--sl-*` overrides there.

**Pros**:
- Fewest new files; tokens are already there.

**Cons**:
- The docs would pull shadcn, Inter, Bricolage, `tw-animate-css` and the marketing band rules they never use, which works against docs speed.
- `marketing.css` is light only by rule; dark docs rules would break that rule or need exceptions.
- Any marketing change risks the docs, and the reverse.

### Option 2: Shared token file plus a separate `docs.css` (chosen)

Move the `@theme static` block into `mk-tokens.css`, import it from `marketing.css` and from a new `docs.css`. `docs.css` maps Starlight's variables to `mk` tokens for both themes and is the only docs stylesheet. Override Starlight's `Header`, `MobileMenuFooter`, `Footer` and `Head`, composing Starlight's own parts.

**Pros**:
- One source of truth for colors; each surface loads only its own rules.
- Dark mode lives in the docs file only, so marketing stays light only.
- Starlight keeps owning search, menu, theme and table of contents behavior.

**Cons**:
- `marketing.css` and the contrast test change, though only to import and read from the new file.
- Four overrides to keep in step with Starlight releases.

### Option 3: Copy the token values into `docs.css`

Leave `marketing.css` alone and write the same hex values again for the docs.

**Pros**:
- Zero change to the marketing files.

**Cons**:
- Two copies of every brand color, which drift the first time someone edits one.

### Option 4: Restyle Starlight's header and footer only, no marketing nav

Keep Starlight's layout and only recolor it.

**Pros**:
- Least work and fewest overrides.

**Cons**:
- The docs still don't share the marketing nav links or Start free trial, so the "one site" goal is only half met.

## Rationale

The force that settles this is that the docs and the marketing pages must look the same while staying separately safe to change. Option 2 is the only one that gives both: one token file means a brand color cannot drift (which rules out Option 3), and a separate docs stylesheet means the docs never load marketing band rules, shadcn or extra fonts, and marketing stays light only (which rules out Option 1). Option 4 misses the scope's goal of a header that feels like the marketing nav.

The hybrid header (marketing links and buttons, Starlight's search, theme switch and phone menu) was chosen over dropping `MkNav` in as is, because `MkNav` decides the signed in state on the server and uses its own dialog for the phone menu, and the docs have both a prerendered page and Starlight's own menu. Two menus on a phone would be confusing. For the same prerender reason the header always shows the signed out buttons: a small script reading Clerk's cookie would fix the label for signed in users but add a script and a visible swap on every docs page, and rendering docs on demand would cost Worker time on every view. Clerk already sends a signed in user who clicks Sign in on to their account, so the cost is low.

Going back to Starlight's sidebar was chosen over keeping the custom accordion because the accordion builds HTML from strings with its own script, and Starlight's version already collapses groups with native details and summary elements, which keyboard and screen reader users get for free. `@astrojs/starlight-tailwind` was chosen over hand written layers because it is Starlight's own bridge and keeps Tailwind's reset from fighting Starlight's; the runner up (importing Tailwind's theme and utilities by hand) would work but leaves the layer order to us. `github-light` and `github-dark` code themes were chosen because they ship with Expressive Code, read well beside a purple accent, and are widely used; a custom `mk` theme would be more on brand but every token color would need its own contrast check. The blog is removed rather than turned on empty, since an empty blog looks abandoned and the plugin adds weight for nothing; it can return as its own feature.

Decisions made while writing (not asked): the dark palette values (measured and listed in `index.md`, all passing AA), the exact Starlight variable mapping, deleting the docs sidebar block from `global.css` (dead once the override goes; runner up was leaving dead CSS), and keeping only Plus Jakarta Sans weights 400, 600 and 700 on docs (runner up: all five weights from `fonts.css`).
