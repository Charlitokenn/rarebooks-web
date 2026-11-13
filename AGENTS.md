# RareBooks (rarebooks, version-16 line)

A Frappe app (`frappe_books/`, Python) plus a Vue app (`frontend/`) served at `/books`. This branch line targets Frappe version-16 on MariaDB. `develop` is on Frappe 17 with three databases and renamed fields, so do not copy its rules or code here unchanged.

## Stack

- **Language / Runtime**: Python 3.14 (Frappe app), TypeScript 5.9 + Vue 3.5 (frontend), Node 24 in CI
- **Framework**: Frappe 16 (`>=16.36.0,<17`, installed by bench), frappe-ui 1.0.0, Vite 5, Tailwind 3
- **Key dependencies**: vue-router 4, @vueuse/core, reka-ui, pesa (money), luxon, CodeMirror 6, Babel (Python, translations)
- **Database**: MariaDB only (CI runs MariaDB 11.8 with Redis 7)
- **Package manager**: yarn 1 (`frontend/yarn.lock` is the real lockfile); bench for the Python side

## Build approach

Tracer Bullet: each feature is built end to end (server query, permission check, Vue card and tests) and works before the next starts. Source: [docs/scope/scope.md](docs/scope/scope.md).

## Commands

```bash
# Install (root postinstall also installs frontend/)
yarn install
bench get-app --soft-link <path-to-repo> && bench setup requirements --dev

# Dev server (Vite on :6969, proxies /api, /assets, /files to BOOKS_SITE_URL, default http://localhost:8000; needs a running bench site)
yarn dev

# Build (writes the /books assets and page into frappe_books/)
yarn build

# Test (Python needs `bench --site <site> set-config allow_tests 1 --parse` once)
bench --site <site> run-tests --app frappe_books   # Python
cd frontend && yarn test && yarn test:ui           # node --test, then Playwright

# Lint and typecheck (what CI runs)
uvx ruff@0.14.10 check frappe_books && uvx ruff@0.14.10 format --check frappe_books
cd frontend && yarn lint && yarn typecheck
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

- Every /books screen is Frappe backed: read [docs/framework-backed-doctypes.md](docs/framework-backed-doctypes.md) before adding or changing a doctype or screen.
- Business rules, defaults and validation live in the Python controller. The client only mirrors a check to show a message at a field.
- Frappe fieldnames (snake_case) are used end to end, frontend included. No camelCase mapping layer.
- Use the domain words in [GLOSSARY.md](GLOSSARY.md) and avoid the synonyms it lists.
- Roles are Books User, Books Manager and Books Cashier. A whitelisted method checks the caller's rights on the server, not only in the UI.
- User facing strings are translated at runtime (`t` tags in TS/Vue, `_()` with `{0}` placeholders in Python); see `babel_extractors.csv`.
- Python: tabs, double quotes, ruff 0.14.10. Keep the ruff version in sync across CI and `.pre-commit-config.yaml`.
- Frontend: 2 spaces, single quotes, Prettier plus ESLint flat config. Doctype JSON: 1 space indent (`.editorconfig`).

## Agent skills

- [code-style](.agents/skills/code-style/): `frappe/skills`, Frappe's Python and JS code style
- [frappe-code-review](.agents/skills/frappe-code-review/): `frappe/skills`, checklist for reviewing Frappe changes
- [paypal-best-practices](.agents/skills/paypal-best-practices/): `paypal/AI-Toolkit`, PayPal checkout, subscriptions and webhooks (for the planned billing control site)

Area skills are listed in each nested doc. MCP servers: Frappe built in MCP (recommended), Playwright MCP (recommended), MariaDB MCP (recommended)

## Context files

- [frappe_books/AGENTS.md](frappe_books/AGENTS.md): the Frappe app, its `books_*` DocTypes, reports, hooks and Python tests
- [frontend/AGENTS.md](frontend/AGENTS.md): the Vue app at /books, its Frappe data layer, models and tests

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
