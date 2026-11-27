# frappe_books/subscription (trial clock and read only lock)

## Overview

The 30 day trial clock, the subscription state, and the read only lock for hosted sites (spec [0005](../../docs/specs/0005-trial-read-only-lock/index.md)). A site counts as hosted only when `books_control_url` is in its `site_config.json`. Without it the clock is off and nothing is ever locked.

## Key files

| File | Owns |
|---|---|
| `__init__.py` | The public names that hooks and `bench execute` call (`frappe_books.subscription.<name>`) |
| `clock.py` | `current_clock()` and `SubscriptionClock`: the phase from the stored facts, today and the site's time zone. Day constants (`TRIAL_LAST_DAY`, `LOCK_DAY`, `REMOVAL_DAY`, `GRACE_DAYS`) |
| `lock.py` | `lock_request`, `lock_job`, the `refuse_when_locked` doc event, `SiteLockedError`, and `ALLOWED_METHODS` (what a locked site still runs) |
| `state.py` | The only writers of the Books Subscription single: `start_trial`, `apply_state`, and the synced push or pull |
| `control.py` | The signed contract with the control site: HMAC signing, the `issued_at` window, outgoing calls |
| `api.py` | Whitelisted `get_subscription`, `start_checkout` and `receive_state` (guest, rate limited, signed) |
| `removal.py` | The site's side of trial end removal (spec [0007 trial end export removal](../../docs/specs/0007-trial-end-export-removal/index.md)): `removal_status`, `build_export`, `export_job` (builds the zip and PUTs it to the presigned R2 link the control site sends), and the two hold fields. Not whitelisted; the control site reaches them through `remote.py` |
| `remote.py` | The control site's signed calls into this site (spec [0010](../../docs/specs/0010-frappe-cloud-hosting/index.md) AC-2, AC-5): guest POST `removal_report`, `start_export`, `mark_export_sent`, `clear_removal` and `control_ping`. Every answer, a 401 included, is signed and echoes the request's `issued_at` |
| `onboarding.py` | The control site's signed calls that hand a warm pool site to its owner (spec [0014](../../docs/specs/0014-self-serve-onboarding/index.md) AC-22 to AC-24): guest POST `claim_site` (makes the owner, sets the time zone, restarts the trial through `state.restart_trial_at_claim`), `owner_link` (a fresh password set link until the owner has one, else `/login`) and `claim_report` (whether the owner has logged in, read before any discard) |
| `bulk_import.py` | The control site's signed calls that bulk import rows into this site (spec [0025](../../docs/specs/0025-bulk-import-control-site/index.md)): guest POST `import_columns`, `preview_import`, `start_import` and `import_report`, plus the `delete_finished_import_file` Data Import hook. The site builds the CSV and runs Frappe's Data Import, so its own controller rules decide what saves. `NEVER_SUBMITTED` keeps Books Expense a draft (spec 0004 AC-12) |
| `import_templates.json` | The Import Wizard's template columns per type, which `bulk_import.py` reads. Written by `frontend/tests/import-templates.test.mjs`, never by hand |
| `../tests/subscription.py` | Test helpers: `store_facts`, `lock_site`, `set_hosted_phase`, `ControlStub`, `SubscriptionTestMixin` |

## Commands

```bash
bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_lock
bench --site <site> execute frappe_books.tests.subscription.set_hosted_phase --kwargs '{"phase": "locked"}'
bench --site <site> execute frappe_books.subscription.apply_state --kwargs "{'state': {'paid_until': '2027-01-31'}}"
```

## Conventions

- A locked request or job runs in a read only database transaction (`frappe.db.begin(read_only=True)`), the same mechanism as Frappe's maintenance mode. An insert or rename is refused with `SiteLockedError` (403); any other write fails with `InReadOnlyMode` (503).
- A new method that must still work on a locked site goes in `ALLOWED_METHODS` in `lock.py`, and in the allowlist test.
- Books Subscription changes only through `state.py`. Its controller refuses every other writer, Administrator included.
- Every writer in `state.py` reads the single through `_locked_facts()` (`get_doc(..., for_update=True)`, a row lock held until commit), so pushes, pulls, checkout, `start_trial` and `apply_state` never collide. Take it only after any control site call has returned, never across a network wait (spec [0007 lock hardening](../../docs/specs/0007-lock-hardening/index.md)).
- Only `InvalidPushError` (in `state.py`, raised by the value checks) answers 400 from `receive_state`. Catch nothing broader: any other failure must stay a 500 that rolls back, so the control site retries it.
- A link from the control site (`books_control_url`, a checkout link) passes `is_trusted_link` in `control.py`: `https://` always, `http://` only with `developer_mode`.
- `clock.site_zone()` must never raise, since the lock hooks call it before login: a time zone the server doesn't know gives UTC, with no log of its own.
- `get_subscription(with_plans=False)` returns the status alone and never calls the control site; /books uses it to word a lock notice.
- Dates and phases use the site's System Settings time zone. `trial_started_on` is stored in UTC.
- Calls to and from the control site are signed with `books_control_secret` in the `X-Books-Signature` header. Never log the secret.
- `import_templates.json` must match what the Import Wizard offers. After a change to an importable type or its fields, refresh it with `UPDATE_IMPORT_TEMPLATES=1 yarn test` in `frontend/` (the node test fails while they differ).
- `../tests/import_csv_cases.json` holds the grid text in, CSV out cases that both `test_subscription_bulk_import.py` and `frontend/tests/import-csv-cases.test.mjs` run, so the site's CSV builder and the wizard write numbers the same way (spec 0025 AC-17). Add a case there, not in one test alone.
- `../tests/signing_vectors.json` holds the golden signing vectors and must stay byte for byte identical to `rarebooks_control/tests/signing_vectors.json` in the `rarebooks_control` repo and `tests/onboarding/signing_vectors.json` in `rarebooks-site`. Change all three together.

## Gotchas

- Web workers cache `site_config.json` for up to 60 seconds, so a new `books_control_url` takes a minute to show over HTTP.
- Subscription tests patch `clock.is_managed` (`managed_site()`) instead of writing `site_config.json`, and restore the facts with `SubscriptionTestMixin`.
- A hosted, unpaid, non exempt site with no `trial_started_on` reads as `locked` (fail closed), with `lock_reason: no_trial_start` and no trial dates in the status. Repair it with `bench --site <site> execute frappe_books.subscription.start_trial`.
- A pull from the control site runs at most once per `PULL_INTERVAL_SECONDS` (10) per site. The caller claims the window first with Redis SET NX on `LAST_PULL_KEY` (`_claim_pull_window`); calls inside it get the stored result, or the Retry message while the pull is still pending, and never call billing. An applied push deletes the key. Only subscribers can ask for a pull, and its `issued_at` must be within the 5 minute window, like a push. Tests clear the key through `control_site()` (`PULL_CACHE_KEYS`).
- The control site drives removal over HTTPS (spec 0010); this app holds no R2 token and no bench wide secret. `export_job` runs on the long queue and `lock_job` lets it past the lock by name (`EXPORT_JOB` in `lock.py`), so it can build an export on a locked site. It writes only files under its own folder, never the database.
- A control site call whose answer status matters (a 503 to retry, a 409 to stop) goes through `control.post_signed`: the answer must be signed and echo the request's `issued_at`, or it raises `ControlSiteUnreachable`.
- Don't read `@@transaction_isolation` directly: MariaDB below 11.1 has only `tx_isolation`. Ask for both names, as `_session_isolation_level()` in `removal.py` does.
- `ALLOWED_METHODS` matches the short public path (`/api/method/frappe_books.subscription.get_subscription`). The module path `frappe_books.subscription.api.get_subscription` is not allowed, so a locked site answers it read only (503). Call these methods by the short path.
- A new pool site has empty System Settings `language` and `time_zone` until its setup wizard, so `System Settings.save()` refuses with a 417. Code that runs before the wizard (`claim_site`) writes one field with `frappe.db.set_single_value` and then calls `clear_system_settings_cache()` (spec 0014 AC-22).
- Frappe writes `User.last_known_versions` on a user's first boot, so `save_known_versions` saves it at login (`on_session_creation`), before the lock applies.

## Agent skills

- [aws-sdk-python-usage](../../.agents/skills/aws-sdk-python-usage/): `aws/agent-toolkit-for-aws`, boto3 and botocore patterns (clients, `ClientError`, S3 transfers), for the R2 side, which now lives on the control site (`rarebooks_control/export_storage.py`); this app only PUTs to a presigned link
- [cloudflare](../../.agents/skills/cloudflare/): `cloudflare/skills`, picking Cloudflare products and finding the right docs
- [cf-cli](../../.agents/skills/cf-cli/): `cloudflare/skills`, the `cf` CLI, including R2 bucket commands for setting up the export bucket
- MCP servers: Cloudflare API MCP (`https://mcp.cloudflare.com/mcp`, recommended), Cloudflare docs MCP (`https://docs.mcp.cloudflare.com/mcp`, recommended)

_Drafted by /sync from the introducing change, worth a quick human pass._
