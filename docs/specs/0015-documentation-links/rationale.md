# 0015. Rationale: point documentation links at the RareBooks docs

The decision record behind [index.md](index.md).

## Context

The /books app came from Frappe Books, and its help links still point at Frappe's docs. Three places build them. The sidebar's Documentation item (and its F1 shortcut) in `frontend/src/utils/appMenu.ts` opens `https://docs.frappe.io/` plus `docsPathRef`, a ref each screen sets when it opens. The search bar's docs link in `frontend/src/components/SearchBar.vue` opens `docsPathMap.Search`. The Get started cards in `frontend/src/utils/getStartedConfig.ts` hold seven full `docs.frappe.io` URLs. The `docsPathMap` in `frontend/src/utils/misc.ts` maps screen keys to Frappe paths such as `books/sales-invoices`, and `Dashboard.vue` hard codes `books/dashboard` instead of reading the map.

The RareBooks docs are Starlight pages in the `rarebooks-site` repo, served at the root of `https://rarebooks.cc` (no `/docs` prefix), one URL per file: `src/content/docs/transactions/sales-invoice.mdx` is `https://rarebooks.cc/transactions/sales-invoice/`. There are 42 pages in seven sections (getting-started, basics, transactions, masters, financial-reports, inventory, settings). Their slugs differ from Frappe's (`sales-invoice`, not `sales-invoices`), so a base address swap alone would break most links. Some screens have no page yet: Sales Quote, the GST reports (GSTR1, GSTR2) and Expenses (spec 0004). Some pages exist with no screen pointing at them: Lead, Point of Sale, Inventory settings.

The docs are public, English only, and the same for every hosted site. The marketing site links its own docs home as `/getting-started/getting-started-with-rarebooks/` (footer and hero). The two repos are deployed separately, so a renamed docs page can silently break a link in the app.

Leaving it means every hosted customer who presses F1 lands on another product's docs, with screenshots and names that do not match RareBooks.

## Options considered

### Option 1: Frontend constant and a frontend map (chosen)

`DOCS_BASE_URL`, `DOCS_HOME` and `docsPathMap` live together in a new `frontend/src/utils/docs.ts`, with `docsUrl(path, anchor?)` building every link. Map values are paths on the docs site.

**Pros**:
- No server path, no boot payload change, nothing to configure per site; the docs are the same for everyone.
- One file to read to see every link; easy to test offline.

**Cons**:
- Changing the docs address needs a frontend rebuild and release.

### Option 2: Site config sent in the boot payload

A `books_docs_url` site config value, defaulting to `https://rarebooks.cc`, sent at boot.

**Pros**:
- An operator could repoint the docs per site without a release.

**Cons**:
- Adds a server read, a boot field and a default in two languages for a link that never differs per site; a wrong value on one site fails silently.

### Option 3: Vite build environment variable

`VITE_DOCS_URL` read at build time, with a default.

**Pros**:
- A staging build could point at a staging docs site.

**Cons**:
- One more value that `yarn build`, bench builds and CI must agree on; a build missing it falls back silently. There is no staging docs site today.

## Rationale

The docs are public, identical for every hosted site, and change only when the marketing site changes, so the address is product configuration, not site configuration. Putting it in site config or a build variable buys a flexibility nobody needs today and adds a place where it can be silently wrong. A constant beside the map keeps the whole feature in one file a reviewer can read in a minute.

The real risk is not the base address but slug drift between two repos deployed apart. A live sitemap check in CI would be always current but makes CI depend on the network and the live site. A hand edited `docs_pages.json` is offline and fast; its cost (update it when a docs page moves) is the same discipline the repos already keep for `signing_vectors.json`. The fallback chain (nearest overview, else Getting started) reuses the fallbacks `ListView` and `Report` already have, now pointed at pages that exist.
