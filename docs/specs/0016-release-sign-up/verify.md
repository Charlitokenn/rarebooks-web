# Verify: Release a sign up · spec 0016 · updated 2026-11-25 (first /check verify run: local bench and Worker harness)
_Steps derived from spec 0016 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [x] Control desk, signed in as a Billing Manager, open a Ready Books Signup → Release sign up shows; on a Failed one it shows beside Retry; on Queued, Claiming, Preparing or Released it does not → AC-1
- [x] Same form as a System Manager or Removal Manager with no Billing Manager role → no Release sign up button → AC-1
- [x] Open the dialog → it shows the row's email and `hosted_site` (or "none"), the three notes (old site untouched, reach it at its own `/login`, next sign up uses the Clerk email then) and a required Reason → AC-1
- [x] Release one email, then open another row with the same email key → the dialog warns "This email was released 1 times before.", and release still works → AC-1
- [x] Confirm with "  A second business  " → the form reloads Released (grey indicator), the Release section shows Released From, By (you), On (UTC) and the trimmed reason; the version history lists the moved keys → AC-1, AC-3
- [ ] Staging: release a Ready test sign up, then on `rarebooks.cc` with the same Clerk account open `/dashboard` → the start form shows (no stale request), and a sign up with a new subdomain becomes Queued → AC-5, AC-8, AC-9
- [ ] Staging: the old site still loads at its address and its owner can sign in at its `/login` → AC-6

## Commands
- [x] `bench --site <site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_onboarding` → OK (TestRelease, TestReleaseRefusals, TestReleasedIsFinal) → AC-2 to AC-7
- [x] `bench --site <site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_pool` → OK (the Failed release waits for its Discard and cleanup) → AC-2, AC-3
- [x] In `rarebooks-site`, `npm test` → `earlier.test.ts` passes (404 is stale; 200 for the same request is live; 200 for another request, no answer, 401, 429 and 5xx keep the row) → AC-8, AC-9
- [x] `select email_key, clerk_user_id, subdomain from tabBooks Signup where status = 'Released'` → every value NULL, never `''` → AC-3
- [x] Call `release_signup` twice on one row → both answer `{"status": "Released"}`; `released_on` and `modified` unchanged by the second → AC-4
- [x] Call `release_signup` on a Queued row, with a blank or 281 character reason, or on `SU-99999` → refused, nothing written → AC-2
- [x] Release a Failed row whose Discard case is still open → "isn't discarded yet"; once Removed but the address not cleaned → "isn't cleaned up"; once cleaned → Released → AC-2
- [x] After a release, run `onboarding.sweep()`, `retry_signup`, `mark_ready(<old site>)`, `fail_signup_of_site(<old site>, ...)` → the row and its `modified` are unchanged, no ops email, no Discard case → AC-7
- [x] Signed `signup_status` and `owner_link` for the released Clerk user → signed 404 → AC-7
- [x] With D1 holding a row for a user, make the control site answer a signed 404 on `/api/onboarding/status` → the row is deleted and the route answers 404 → AC-8
- [x] Same with the control site down, answering 401 or 5xx → the row stays and `/api/onboarding/signup` answers 503 "We couldn't check your earlier sign up. Try again." with no IP limit count → AC-9
- [x] Insert a newer D1 row for the same user, then let a 404 for the old `request_id` arrive → the newer row stays (delete matches `clerk_user_id` and `request_id`) → AC-8, AC-10
- [ ] Send a Ready notice for the released request after the person signed up again → only the old `request_id` row (or a `request:<id>` row) is touched, never the newer one → AC-10

## Value sourcing
- [ ] Dialog email and site come from the row's `email` and `hosted_site`: try a row with no `hosted_site` → "none" → Value sourcing
- [x] `released_email_key`, `released_clerk_user_id`, `released_subdomain` equal the keys the row held under the lock (try a Gmail address with dots and `+`: the key, not the email, is stored) → Value sourcing
- [x] `released_from` equals the status at release: release one Ready and one Failed row → Ready and Failed → Value sourcing
- [ ] `released_by` is the session user: release as two different Billing Managers → each name stored → Value sourcing
- [x] `released_on` is UTC: on a site whose system time zone is not UTC, the stored time matches UTC now → Value sourcing
- [x] `release_reason` is the input trimmed: leading and trailing spaces gone, inner text kept → Value sourcing
- [x] Failed cleanup check uses `_cleanup_pending(hosted_site)`; a Failed row with no `hosted_site` releases at once → Value sourcing
- [ ] Repeat warning counts Released rows with the same `released_email_key`: 0 shows no warning, 2 shows "2 times" → Value sourcing
- [x] `awaits_signup` treats Ready and Released alike: a released Ready site gets its Trial case from the round; a Preparing one still gets none → Value sourcing
- [x] Worker staleness comes only from a signed, verified `signup_status` 404 for that `clerk_user_id` and `request_id`; an unsigned 404 keeps the row → Value sourcing
- [ ] Worker uses the Clerk session user id and the D1 `request_id`: a form field naming another user changes nothing → Value sourcing

## Acceptance-criteria coverage
- AC-1: UI steps 1 to 5 · AC-2: Commands 1, 2, 6, 7 · AC-3: UI 5, Commands 4 · AC-4: Commands 5 · AC-5: UI 6 · AC-6: UI 7, Value sourcing (`awaits_signup`) · AC-7: Commands 8, 9 · AC-8: UI 6, Commands 3, 10, 12 · AC-9: UI 6, Commands 3, 11 · AC-10: Commands 12, 13
