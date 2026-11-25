# 0016. Release a sign up: rationale

## Context

Spec 0014 holds one Books Signup per `email_key`, per `clerk_user_id` and per subdomain, ever, with database unique indexes. That rule keeps one person from collecting free trials. It has no exit: when a person with a site needs another one (a new business, a fresh start after a bad first try, a support request), the only way today is for Administrator to delete the Books Signup by hand, then for someone to delete the Worker's D1 `signups` row with wrangler. Missing the second step leaves the person stuck: the start form shows, but `POST /api/onboarding/signup` finds the D1 row and answers the old `request_id` without asking the control site.

The forces: the release must be an operator decision, never a visitor's, or the trial limit means nothing. It must leave a record, because a later look at billing will find one email on two sites. The old site is live, with its own trial clock, pushes and removal cases (spec 0007, spec 0010), and those must keep working whatever happens to the request that created it. The removal round already reads the request's status for Claimed sites (`removal.awaits_signup`, spec 0014 AC-20), so a new status can silently change billing if it is missed.

The marketing site keeps its own copy of each request in D1 and trusts it. Anything that changes a request on the control site has to reach that copy, or be safe when it doesn't.

## Options considered

### What happens to the old site

**Leave it untouched (chosen).** The release frees the keys only; the site keeps running, billing and its removal cases as before, and you remove it separately if you want. Pros: covers both "a second business" and "start over"; no new path into removal code. Cons: the person can hold two sites, one possibly still on a trial.

**Require it removed first.** Refused until the old site has a Removed case, like Retry. Pros: one live site per email, always. Cons: a person who wants a second business can't keep the first; you'd have to remove a paying site to help them.

**Choose per release.** The dialog asks keep or remove; remove opens a case and the release waits for it. Pros: flexible. Cons: a release becomes a two step job tied to removal timing, with a second state to track.

### What happens to the row

**Keep it, status Released, keys moved to `released_*` (chosen).** Pros: the audit trail lives on the row, searchable by the old email; the old site still points to the request that made it; the unique indexes free the keys because NULL never clashes. Cons: three `reqd` fields become conditional, and readers of "the request for this site" must allow for Released.

**Delete it.** Pros: no schema change. Cons: the record survives only as a Deleted Document; the old site loses its request, and `awaits_signup` would then read "no Ready request" and stop opening its Trial case.

### How the Worker's D1 row goes

**The Worker trusts the control site (chosen).** On a signed 404 for a user's D1 row, the Worker deletes the row (status poll and start form). Pros: no new signed message, retry or alert; heals any hand made delete too. Cons: one more control site call on the start form for users who have a D1 row.

**A signed Released notice.** The control site sends `Released` through the existing notify endpoint and its 24 hour retry. Pros: explicit and immediate. Cons: a lost or late notice leaves the person stuck; the notice and the release can race a Ready notice already in flight.

**Both.** Pros: immediate, with a safety net. Cons: the most code for a rare operator action.

## Rationale

You chose to leave the old site untouched because the release is about the person's next sign up, not about their current site: removal already has its own rules, guards and approvals (spec 0007, spec 0010), and tying a release to them would make a support task wait on a removal round. The cost is that a release can give a second free trial; requiring a Billing Manager and a written reason, with the row kept for ever, makes that a visible decision rather than a loophole. Only Ready and Failed are releasable, because a request still being claimed, named or given its domain has steps that would keep writing to it; a Failed one must first finish its Discard, for the same reason Retry waits (spec 0014 AC-18), so a released request never leaves a half made site behind.

Keeping the row matters more than it looks: `removal.awaits_signup` decides whether a Claimed site gets its Trial case by finding its request Ready. Deleting the row, or adding Released without updating that check, would quietly stop trial enforcement on the old site. Counting Released as Ready there keeps billing exactly as it was. Moving the keys into `released_*` fields, rather than adding a "released" flag to the unique indexes, keeps the indexes simple and the database still enforces the one per person rule among live requests.

For the Worker, healing from the control site's answer beats a new notice because the D1 row is a cache: the control site is already the truth for every status, and AC-4 of spec 0014 already rebuilds a missing row from it. Deleting on a signed, verified 404 is the same trust, in the other direction, and it needs no new secret, retry or alert. The one extra call only happens for a user who has a D1 row and opens the start form, which today only a released or broken user does.
