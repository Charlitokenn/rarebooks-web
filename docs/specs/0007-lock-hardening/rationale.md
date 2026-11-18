# 0007. Lock hardening: decision record

## Context

The fresh model review of feature 6 (`docs/reviews/2026-11-18-v16-dashboard-features-trial-lock.md`) left six minor findings after its three majors were fixed. They share one theme: the lock behaves well on the happy path, but some timing accidents, bad settings and outside conditions give a wrong answer or a confusing message. In a paywall, a wrong answer either costs a customer access they paid for or costs the business a free subscription.

The forces at play:
- `apply_synced_state` reads the Books Subscription single without a lock. When two pushes overlap, the slower save fails Frappe's modified timestamp check, and `receive_state` turns every `frappe.ValidationError` (which that error is) into a 400 with a "bad value" log row. A control site may treat a 400 as final and stop retrying.
- `start_checkout` passes on a `checkout_url` that may be plain http, though spec 0005 says outgoing traffic is https only outside developer mode.
- `site_zone` builds a `ZoneInfo` from System Settings. An unknown name raises, and because the lock check runs in `before_request` before login, every request fails with a 500. Nothing in the UI can fix it.
- Frappe's own maintenance mode raises the same `InReadOnlyMode` the lock uses, and the client maps by type only, so maintenance shows "Subscribe to make changes again".
- The first refused write after the site turns read only builds its notice from the browser's old status, so it shows the generic text instead of the dated one spec 0005 AC-8 asks for.
- `/check verify` found two tests that pass or fail depending on what an earlier run left on the test site, and a verify.md setup line that can't run.

The feature is small, the team is small, and the stack is settled (Frappe 16, MariaDB, Redis, Vue). Anything that adds infrastructure or a stored field would cost more than the problems it solves.

## Options considered

### Serializing pushes

**Option A: database row lock (chosen).** Read the single with Frappe's locking read (`frappe.get_doc(..., for_update=True)`, a `SELECT ... FOR UPDATE` on its `tabSingles` rows) before changing it.
- Pros: it's in the same transaction as the save, so it releases on commit or rollback, it works across workers and hosts, and it needs nothing new.
- Cons: a push waits behind a slow pull that holds the lock; it relies on MariaDB row locks on `tabSingles` (fine on this stack, MariaDB only).

**Option B: Redis lock.** `frappe.cache` lock around the apply.
- Pros: it's independent of the database transaction and quick to add.
- Cons: a crash leaves the lock until its timeout; the lock and the transaction can disagree (the lock released before commit, or the reverse); it adds a moving part to a money path.

**Option C: retry on the timestamp clash.**
- Pros: the smallest code change.
- Cons: a third concurrent push can still lose, and retry loops hide real errors.

### A non https checkout link

**Option A: treat it as unreachable (chosen).** It gives the Retry message plus an Error Log row.
- Pros: one rule shared with `control_url`; the customer sees a familiar message; only a broken control site triggers it.
- Cons: support has to read the Error Log to know it wasn't a network failure.

**Option B: its own message.** "Billing sent an unsafe payment link."
- Pros: clearer to support.
- Cons: a new user facing string for an operator problem the customer can't act on.

### An unknown time zone

**Option A: UTC, log once an hour (chosen).**
- Pros: the site stays up and someone notices.
- Cons: lock days follow UTC until it's fixed.

**Option B: UTC, no log.**
- Pros: no noise.
- Cons: a wrong lock day could go unnoticed for weeks.

**Option C: UTC, log every request.**
- Pros: impossible to miss.
- Cons: it floods the Error Log on a busy site.

### The first notice and maintenance

**Option A: await a status only call (chosen).** `get_subscription(with_plans=False)` before building the notice.
- Pros: the first notice is right; one call also tells lock and maintenance apart; it never waits on billing.
- Cons: one extra request on that first refusal, and a new flag on `get_subscription`.

**Option B: await the full status call.**
- Pros: no new flag.
- Cons: for a manager with no cached plans the notice can wait up to 10 seconds on billing.

**Option C: keep fire and forget.**
- Pros: no wait.
- Cons: spec 0005 AC-8 stays unmet on the first notice, and maintenance can't be told apart.

For the maintenance words, our own translated text was chosen over passing on Frappe's server message, which is worded as an error and isn't translated with the rest of the lock texts.

### Push errors other than a bad value

**Let them be a 500 (chosen)** rather than keeping 400 for everything. A 500 means "try again" to any sane client, and a transient database error should be retried, not dropped.

### Putting a site into "no trial start" for tests

**A `clear_trial_start()` helper (chosen)** rather than raw SQL in verify.md. The field is mandatory, so the only way to empty it is to delete its `tabSingles` row; a helper does it once, correctly, and clears the cache.

## Rationale

Every finding is a defect in code that otherwise holds, so each is fixed in place, the "fix in place" path for an enhancement, with no migration and no new component. The row lock is the boring, correct tool for "two writers, one row" on MariaDB: the database already guarantees the order, and tying the lock to the transaction removes the two failure modes a Redis lock adds. Splitting 400 from 500 by exception type makes the control site contract honest: 400 means "your data is wrong, don't send it again", 500 means "my side failed, try again".

Reusing the existing "unreachable" path for a bad link and the existing UTC path for an empty zone keeps the number of user facing states the same, which matters more for a paywall's support load than a precise message for an operator mistake. The hourly log is the middle ground between silence and a flood.

On the client, the status only call is the one change that fixes both the stale first notice and the maintenance mix up, because the fresh status is exactly what tells them apart. Making it skip plans keeps the notice off the billing path, so the 10 second billing timeout can never delay a save's error.

Small calls made while writing:
- **Where the client waits**: in the two async callers (`call` through an async `toBooksError`, and `request`), so `getServerError` stays synchronous. Runner up: make `getServerError` async, which spreads the change further for no gain.
- **A failed status call**: fall back to the stored status and the generic text, rather than retrying, so a refused save never hangs.
- **Error Log titles and the cache key**: "Books billing: create_checkout sent a link that isn't https", "Books subscription: unknown time zone {0}, using UTC", and `books_subscription_bad_time_zone`, named to match the existing "Books billing:" rows.
- **`SiteLockedError` with an unlocked fresh status** (the lock lifted between the save and the status read): still the lock notice with the generic text, rather than a third message, since a retry then works.

Changes after the cross check (2026-11-18, applied on the engineer's go):
- **A locking read, not a raw lock plus a plain read.** Under MariaDB's repeatable read, a plain `get_single` after a separate `SELECT ... FOR UPDATE` can still see the row from before the wait, so the save would fail the same timestamp check. `frappe.get_doc(..., for_update=True)` locks and reads the latest committed rows in one step. `mark_checkout_started` takes it too, since it reads then saves just like a push.
- **`InvalidPushError` lives in `state.py`** and the value checks raise it, because `api.py` imports `state.py` and the checks used plain `frappe.ValidationError`. Both the push and the pull catch only that type.
- **The time zone fallback catches any exception** (`ZoneInfo("America")` raises a directory error, not `ZoneInfoNotFoundError`), logs with `defer_insert` because a locked request is read only, and claims its hourly key with SET NX so two workers can't both log.
- **The client always fetches a fresh status on `InReadOnlyMode`**, not only when it thinks the site is open, so maintenance after a payment never says "Subscribe". AC-5 is limited to Frappe's "reads allowed" maintenance, because in full maintenance Frappe stops every request before this app runs.
- **No loop, one fetch:** the status call skips the wait, and refusals that arrive together share one fetch. A status only fetch keeps the plans already stored.
- **Tests force the overlap** (a barrier and a delay inside the apply) so the concurrency test can't pass without the fix, and name how errors are injected and logs are counted.
