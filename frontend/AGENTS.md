# frontend (Vue app at /books)

## Overview

The Books user interface: a Vue 3 + frappe-ui 1.0.0 single page app that renders forms, lists and reports from Frappe's DocType meta and talks to the `frappe_books` app over `/api/v2` and whitelisted methods. It holds no business rules of its own.

## Key files

| File | Owns |
|---|---|
| `src/frappe/` | The Frappe data layer: meta, schema, `FrappeDoc`, `/api/v2` calls, field state. Mapped in [docs/framework-backed-doctypes.md](../docs/framework-backed-doctypes.md) |
| `src/web/api.ts` | `call()` for whitelisted methods, server errors, session expiry |
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
- No store library: shared state is the `fyo` singleton (`fyo.singles`, `fyo.observer`), refs in `src/utils/refs.ts`, and `provide`/`inject` with keys from `src/utils/injectionKeys.ts`.
- Charts come from `frappe-ui/charts`; check that frappe-ui 1.0.0 has a prop before you use it, since `develop` is on a newer frappe-ui.
- Styling is Tailwind with the frappe-ui preset; use logical (RTL safe) classes from `tailwindcss-rtl`.
- Translate with the `t` tag at runtime, never in module level constants (they run before translations load).
- Import with the path aliases (`fyo/`, `src/`, `models/`, `utils/`, `reports/`, `schemas/`), not long relative paths.
- Components are PascalCase `.vue`; utils camelCase `.ts`; tests kebab case `*.test.mjs` and `*.spec.ts`.

## Gotchas

- A save waits for a running preview; in node tests call `await doc.whenFilled()` before asserting server filled values.
- `fyo/core/types.ts` and `schemas/types.ts` are only shared types now. The old camelCase bridge they belonged to is gone; do not rebuild it.
- Node tests load TypeScript through esbuild (`tests/helpers/fyo.mjs`), so run `yarn install` first.
- Prettier and ESLint pre-commit hooks run from `frontend/node_modules`, so they fail until it is installed.
- Run the guard tests (`settings-readers`, `settings-models`, `link-create`) after a merge from another branch.

## Agent skills

- [vue-best-practices](../.agents/skills/vue-best-practices/): `vuejs-ai/skills`, Vue 3 patterns
- [vue-router-best-practices](../.agents/skills/vue-router-best-practices/): `vuejs-ai/skills`, vue-router 4
- [vite](../.agents/skills/vite/): `antfu/skills`, Vite config and usage (this app is on Vite 5, so ignore Vite 8 only advice)
- [tailwindcss](../.agents/skills/tailwindcss/): `hairyf/skills`, Tailwind (this app is on v3, so ignore v4 only advice)
- [playwright-best-practices](../.agents/skills/playwright-best-practices/): `currents-dev/playwright-best-practices-skill`, writing tests in `tests/ui/`
- [playwright-cli](../.agents/skills/playwright-cli/): `microsoft/playwright-cli`, driving Playwright from the command line

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
