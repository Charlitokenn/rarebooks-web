# Review, v16-dashboard-features (lock hardening, spec 0007), 2026-11-18

**Reviewed by**: Sonnet 5.5 (author on Opus 5.5)
**Scope**: 16 files (commits 0725baf, 3266f53, 75366c1), branch vs origin/version-16 (merge base 7ae28fa). The interleaved trial end export removal (fb42b49) is out of scope except where it touches the same code.
**Verdict**: Approve with nits

## Summary

The change closes the prior review's findings as spec 0007 describes: a row locked read for pushes, pulls and checkout, a 400 or 500 split on `InvalidPushError`, an https rule for checkout links shared with `control_url`, a never raising `site_zone`, a status only `get_subscription`, and a client that waits for one shared fresh status before wording a lock notice. The code matches the spec closely, including the AC-4 revision that dropped the unloggable hourly row. I found no blockers or majors. `ruff@0.14.10 check` and `format --check` are clean, and the 780 frontend node tests pass. The Python integration tests could not be run here, as no bench site exists, so those were judged by reading only.

## Minor

### 🟡 A non control site failure in a pull leaves the pull window claimed, `frappe_books/subscription/api.py:180`
**Problem**: `_pull_and_report` claims `LAST_PULL_KEY` as `pending` and only overwrites it after `pull_state()` returns or raises `ControlSiteUnreachable`. Any other exception propagates (now by design, AC-2), so the key stays `pending` for the full 10 seconds.
**Why it matters**: The new row lock adds failures of exactly this kind (lock wait timeout, deadlock) inside `apply_synced_state`. For those 10 seconds every other `get_subscription(refresh=True)` gets the Retry message and no pull is attempted. It self heals and only delays recovery. `test_any_other_pull_failure_is_not_logged_as_a_bad_value` does not assert the key state.
**Suggested fix**: Delete the claimed key, or set it to the error, in a `finally`/`except BaseException` branch before re-raising. Add an assertion to that test.

### 🟡 Spec claim "every writer takes the locking read first" is not true, `frappe_books/subscription/state.py:21` and `:30`
**Problem**: `start_trial` and `apply_state` still use plain `frappe.get_single`. The spec's justification for rewriting the single's rows safely (index.md, server internals) says all writers lock.
**Why it matters**: Both are install, patch or bench execute paths, so a real collision is unlikely. The doc and code disagree, and a future caller of `apply_state` on a live site (it is the documented way to lift a lock) could hit a timestamp mismatch against a push.
**Suggested fix**: Have `apply_state` use `_locked_facts()`. Leave `start_trial` alone if it is install only, and correct the spec sentence either way.

### 🟡 Weak assertions in the concurrency tests, `frappe_books/tests/test_subscription_control.py:196` and `:261`
**Problem**: The serialization check in `test_two_pushes_at_once_both_answer_and_the_newer_wins` is wrapped in `if len(started) == 2`, so it is silently skipped when the older push is `ignored`. `test_a_checkout_during_a_push_waits_and_both_save` asserts only the end state, not that the checkout waited for the push's commit.
**Why it matters**: The end state does catch an unlocked read, which would lose a write or raise a timestamp mismatch, so the tests have value. A regression that kept both outcomes valid but dropped the ordering would still pass.
**Suggested fix**: In the checkout test, record the time `mark_checkout_started` returns and assert it is not before the push's finish time. For the push test, assert the ordering outside the conditional, or assert `len(started)` explicitly for the order sent.

### 🟡 The checkout log row is mislabeled when the link is missing, `frappe_books/subscription/api.py:101`
**Problem**: Any non empty signed answer without a valid link writes "create_checkout sent a link that isn't https", including an answer that has no `checkout_url` at all or a non string one. A valid signed empty `{}` writes no row.
**Why it matters**: The operator gets a misleading cause, and an empty answer is indistinguishable from an outage.
**Suggested fix**: Use a neutral title ("sent no usable checkout link"), or log only when a string link was present and failed the https rule. Treat the empty `{}` the same way.

## Nits

- ⚪ `frontend/src/web/api.ts:131`, `InReadOnlyMode` always costs an extra status GET per refused write, even when the stored status already says locked. This follows the spec, but a stored `locked: true` with a lock phase text could skip it. It is not worth changing unless refusals turn out to arrive in bursts that are not coalesced.
- ⚪ `frappe_books/subscription/clock.py:167`, `site_zone` swallows the bad zone with no signal at all, as the spec chose. A one line comment pointing at the spec exists. Consider a `frappe.logger()` debug line (file log, no DB stamp) so the operator has some trace.
- ⚪ `frappe_books/subscription/control.py:115`, `control_url` previously accepted any scheme in developer mode and now accepts only `http://` or `https://`. This is a harmless tightening, but it is not listed in the spec's API changes.
- ⚪ `docs/specs/0007-lock-hardening/verify.md:12`, the "Two refused saves at once" manual step is still unchecked, while the scope marks the feature as built and tested. Check it or note why it is deferred. The node test already covers the single shared call.

## Strengths

- The row lock is taken only after the control site call returns, and `_locked_facts` documents why a locking read is needed under repeatable read. `InvalidPushError` is correctly narrowed, so a deadlock becomes a 500 the control site retries, not a dropped "bad value".
- The client loop guard is clean: `skipLockStatus` on the status call itself, plus one shared in flight promise cleared in `finally`. Tests cover the guard, coalescing, fallback on failure, and kept plans.
- Test setup is isolated from site leftovers (`managed_site(False)`, `store_facts(auto_renews=0)`), and `clear_trial_start` has a documented undo.

## Test coverage

Covered: concurrent pushes in both orders (AC-1), the 400 or 500 push split and the pull split (AC-2), checkout during a push and the https rule with http, `javascript:` and no scheme, plus the developer mode case (AC-3), UTC fallback for three bad zone names, lock day counting and no Error Log rows (AC-4), maintenance text, awaited status, fallback, coalescing, loop guard and kept plans (AC-5 to AC-7), and the order sensitive test isolation (AC-8). Gaps: no assertion on the pull window key after a non control failure (see the first Minor), and the checkout wait is not asserted directly (see the third Minor). The Python integration suite was not run in this environment.
