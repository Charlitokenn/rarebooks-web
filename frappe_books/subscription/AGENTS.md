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
- Dates and phases use the site's System Settings time zone. `trial_started_on` is stored in UTC.
- Calls to and from the control site are signed with `books_control_secret` in the `X-Books-Signature` header. Never log the secret.

## Gotchas

- Web workers cache `site_config.json` for up to 60 seconds, so a new `books_control_url` takes a minute to show over HTTP.
- Subscription tests patch `clock.is_managed` (`managed_site()`) instead of writing `site_config.json`, and restore the facts with `SubscriptionTestMixin`.
- A hosted, unpaid, non exempt site with no `trial_started_on` reads as `locked` (fail closed), with `lock_reason: no_trial_start` and no trial dates in the status. Repair it with `bench --site <site> execute frappe_books.subscription.start_trial`.
- A pull from the control site runs at most once per `PULL_INTERVAL_SECONDS` (10) per site. The caller claims the window first with Redis SET NX on `LAST_PULL_KEY` (`_claim_pull_window`); calls inside it get the stored result, or the Retry message while the pull is still pending, and never call billing. An applied push deletes the key. Only subscribers can ask for a pull, and its `issued_at` must be within the 5 minute window, like a push. Tests clear the key through `control_site()` (`PULL_CACHE_KEYS`).
- Frappe writes `User.last_known_versions` on a user's first boot, so `save_known_versions` saves it at login (`on_session_creation`), before the lock applies.

_Drafted by /sync from the introducing change, worth a quick human pass._
