# frontend (Vue app at /books)

## Overview

The Books user interface: a Vue 3 + frappe-ui 1.0.0 single page app that renders forms, lists and reports from Frappe's DocType meta and talks to the `frappe_books` app over `/api/v2` and whitelisted methods. It holds no business rules of its own.

## Key files

| File | Owns |
|---|---|
| `src/frappe/` | The Frappe data layer: meta, schema, `FrappeDoc`, `/api/v2` calls, field state. Mapped in [docs/framework-backed-doctypes.md](../docs/framework-backed-doctypes.md) |
| `src/web/api.ts` | `call()` for whitelisted methods, server errors, session expiry |
| `src/utils/supportChat.ts` | The tawk.to support chat: the only place that loads the tawk.to script or calls `Tawk_API`, from the server signed `books.support_chat` boot block, on the first pick only (spec 0009) |
| `src/utils/docs.ts` | Every help link: the RareBooks docs address `DOCS_BASE_URL`, the screen to page map `docsPathMap`, `docsUrl`/`openDocs`, and `holdDocsPath` for overlays (spec 0015) |
| `models/index.ts` | `frappeModels`: one model per schema name, extending `FrappeDoc` ([models/README.md](models/README.md)) |
| `fyo/` | Shared primitives: the `fyo` singleton, translation, formatting, money, observer events ([fyo/README.md](fyo/README.md)) |
| `src/web/main.ts`, `src/initFyo.ts`, `src/router.ts` | Startup and routes ([src/README.md](src/README.md)) |
| `reports/` | Client classes for the server script reports ([reports/README.md](reports/README.md)) |
| `src/pages/`, `src/components/`, `src/mobile/` | Screens (the dashboard is `src/pages/Dashboard/`), shared components, the POS and phone views |
| `tests/*.test.mjs`, `tests/helpers/` | Node unit tests (`server.mjs` stubs the server) |
| `tests/ui/` | Playwright browser tests ([tests/ui/README.md](tests/ui/README.md)) |

## Commands

```bash
yarn dev         # Vite on :6969, set BOOKS_SITE_URL if the bench site is not on :8000
yarn test        # node --test tests/*.test.mjs
yarn test:ui     # Playwright, needs a running site at BOOKS_TEST_URL (default http://books-test.localhost:8000)
yarn typecheck   # vue-tsc --noEmit
yarn lint        # eslint .
```

## Conventions

- Models extend `FrappeDoc` and carry no `formulas`, `defaults` or data code. Presentation only settings go in `static presentation`; see the "Where each part goes" table in the framework doc.
- The schema name (for example `SalesInvoice`, `Item`) is the route key and the `frappeModels` key. Table rows use the child DocType name without `Books ` (for example `SalesInvoiceItem`).
- Talk to the server through `src/frappe/` and `src/web/api.ts`. No raw `fetch` in components, and no `createResource`.
- Screens never handle server messages. A `msgprint` sent with a successful write or `call()` shows as a toast through `src/frappe/serverMessages.ts`, which only `request()` in `src/frappe/api.ts` and the `serverMessagesHandler` set in `src/web/api.ts` call. The form's preview passes `quiet` (spec 0006).
- On a locked hosted site a write fails with `SiteLockedError` (403) or `InReadOnlyMode` (503). `src/web/api.ts` turns both into the lock notice by error type (`isLockErrorType` in `src/utils/subscription.ts`), never by status alone, so screens don't handle them (spec 0005).
- Before it words that notice, `getLockStatus` in `src/web/api.ts` awaits a fresh status (`fetchLockStatus`, one shared `get_subscription` call with `with_plans: false`): always for `InReadOnlyMode`, which may be Frappe's own maintenance mode, and for `SiteLockedError` while the stored status says open. The status call itself passes `skipLockStatus`, so it can't start another one (spec 0007 lock hardening).
- No store library: shared state is the `fyo` singleton (`fyo.singles`, `fyo.observer`), refs in `src/utils/refs.ts`, and `provide`/`inject` with keys from `src/utils/injectionKeys.ts`.
- Dashboard cards extend `src/pages/Dashboard/BaseDashboardChart.vue` (the `period` prop, `loadData` around their own `setData`, `cardClass` for phones) and show `ChartLoadError` on a failed load.
- Charts come from `frappe-ui/charts`; check that frappe-ui 1.0.0 has a prop before you use it, since `develop` is on a newer frappe-ui.
- Styling is Tailwind with the frappe-ui preset; use logical (RTL safe) classes from `tailwindcss-rtl`.
- Translate with the `t` tag at runtime, never in module level constants (they run before translations load).
- Docs links go through `src/utils/docs.ts`, never a hand built URL. A screen sets `docsPathRef` from `docsPathMap` in `activated` and clears it in `deactivated`; an overlay over a screen (the Settings dialog) uses `holdDocsPath`, so a screen that activates under it can't take over (spec 0015 AC-2, AC-7).
- The Import Wizard writes Int, Float and Currency cells with `getImportNumberText` in `src/utils/precision.ts`, in the user's import number format (`boot.books.number_format`, not `sysdefaults.number_format`). The site's control site import uses the same rule, checked by the shared `frappe_books/tests/import_csv_cases.json` (spec 0025 AC-17).
- Import with the path aliases (`fyo/`, `src/`, `models/`, `utils/`, `reports/`, `schemas/`), not long relative paths.
- Components are PascalCase `.vue`; utils camelCase `.ts`; tests kebab case `*.test.mjs` and `*.spec.ts`.

## Gotchas

- A save waits for a running preview; in node tests call `await doc.whenFilled()` before asserting server filled values.
- `fyo/core/types.ts` and `schemas/types.ts` are only shared types now. The old camelCase bridge they belonged to is gone; do not rebuild it.
- Node tests load TypeScript through esbuild (`tests/helpers/fyo.mjs`), so run `yarn install` first.
- Prettier and ESLint pre-commit hooks run from `frontend/node_modules`, so they fail until it is installed.
- Run the guard tests (`settings-readers`, `settings-models`, `link-create`) after a merge from another branch.
- `tests/docs_pages.json` lists the `rarebooks-site` docs pages that `docsPathMap` may point at. Update it when a docs page there is added, renamed or removed; the drift check against `../rarebooks-site` runs only when that checkout sits next to this repo, so CI skips it (spec 0015 AC-8).
- frappe-ui's `text-<size>` classes set their own font weight (420), which beats `font-semibold`. Use the combined `text-<size>-semibold` (or `-medium`, `-bold`) class instead.
- Every tawk.to `setAttributes` call must carry the signed visitor identity (`hash` included): with Secure Mode on, tawk.to answers `UNAUTHORIZED_API_CALL` to one without it (spec 0009 AC-5).

## Agent skills

- [vue-best-practices](../.agents/skills/vue-best-practices/): `vuejs-ai/skills`, Vue 3 patterns
- [vue-router-best-practices](../.agents/skills/vue-router-best-practices/): `vuejs-ai/skills`, vue-router 4
- [vite](../.agents/skills/vite/): `antfu/skills`, Vite config and usage (this app is on Vite 5, so ignore Vite 8 only advice)
- [tailwindcss](../.agents/skills/tailwindcss/): `hairyf/skills`, Tailwind (this app is on v3, so ignore v4 only advice)
- [playwright-best-practices](../.agents/skills/playwright-best-practices/): `currents-dev/playwright-best-practices-skill`, writing tests in `tests/ui/`
- [playwright-cli](../.agents/skills/playwright-cli/): `microsoft/playwright-cli`, driving Playwright from the command line

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
