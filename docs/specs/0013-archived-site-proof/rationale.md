# 0013. Hosting on Frappe Cloud: proving a site is archived: rationale

## Context

The removal flow (specs 0007, 0010, 0011) ends with an archive on Frappe Cloud, the only irreversible step in the product. Three places then decide whether Frappe Cloud has finished: the read right before an archive call at the start of a drop (0010 AC-6), the hourly poll of a `Dropping` case (0010 AC-7, 0011 AC-2), and the daily reconcile of a `Failed` drop (0011 AC-11). All three read `press.api.site.get` and wait for status `Archived`. Spec 0012's domain cleanup (AC-11) starts when the archive is marked as requested, and counts the Frappe Cloud part done when Frappe Cloud shows the site archived, says it can't find it, or no longer lists the domain.

On 2026-11-21 a throwaway site, `rbdomaincheck.frappe.cloud`, went through a real archive with the control site's own client code. Right after the call, `get` answered status `Pending` and `domains` still listed both domains. About 30 seconds later, and every time after that: `get` answered HTTP 403, `domains` answered HTTP 403, `remove_domain` answered HTTP 403, and `domain_exists` answered `null` for both the custom domain and the site's own `.frappe.cloud` name. The site list (`press.api.site.all`) doesn't show archived sites with any filter. For comparison, `domain_exists("demo-site.frappe.cloud")` on a live site answers its own name. The same check confirmed the domain methods spec 0012 relies on, and the certificate on the custom domain was valid in a browser.

So with your team's key, `Archived` is never seen. As built, a real drop would count a `step_failed` on each hourly poll (a 403 is an API error), become `Failed` with an ops email after three hours, and then never be reconciled, because the daily reconcile also waits for `Archived`. Spec 0012's cleanup would retry every hour and send its 24 hour alert.

HTTP 403 means more than one thing: "this site is no longer visible to your team", "your key is wrong or revoked", and possibly "this name no longer belongs to the site", if Frappe Cloud renames a live site. The rule must fail closed: marking a live site `Removed` stops its billing, pushes and removal on the control site while the customer keeps using it. A second risk sits in spec 0012's cleanup: an archive call whose outcome is unknown counts as requested (0011 AC-1), so the cleanup can start, and delete the DNS record behind a site's primary address, while Frappe Cloud may never have received the archive. This spec doesn't change Frappe Cloud or the customer site; it only changes how the control site reads Frappe Cloud's answers.

## Options considered

### Option 1: Keep waiting for `Archived`

Keep 0011's rule and ask Frappe Cloud support whether archived sites can be shown to the team.

**Pros**:
- No code change; the most explicit signal there could be.

**Cons**:
- Frappe Cloud doesn't send it today, so every real drop ends `Failed` with an alert and stays that way, and every removal needs you by hand.
- Depends on a vendor change with no date.

### Option 2: HTTP 403 plus the site's own name released, for drops we started (chosen)

Treat a 403 from `get` as proof only for a case whose drop the control site started, and only when `domain_exists` for the site's own `.frappe.cloud` name answers `null` in the same job. Keep `Archived` as a second proof.

**Pros**:
- Two facts, plus our own record that we started the drop. A wrong or revoked key can't fake the released name, and a renamed live site can't reach proof (b) unless we had started dropping it.
- Works for every site, custom domain or not, because Frappe Cloud stores each site's own name as a domain and releases it at archive.
- Already seen on the live API, within about 30 seconds of the archive.

**Cons**:
- Rests on behaviours Frappe Cloud doesn't document: archived sites turning 403 for the team, and their names being released.
- A site archived by hand before any drop started doesn't close itself.
- One extra API call on each poll that gets a 403.

### Option 3: HTTP 403 plus a key check

Treat a 403 as proof when a call for another site (the control site itself) succeeds in the same job, which shows the key works.

**Pros**:
- Doesn't depend on how Frappe Cloud releases names.

**Cons**:
- A 403 can also mean the site moved to another team or was renamed; a working key elsewhere doesn't rule those out.
- No positive sign that the archive happened, only that the key works.

### Option 4: The released name alone

Count `domain_exists(site)` answering `null` as proof, whatever `get` answers.

**Pros**:
- One call, the simplest rule.

**Cons**:
- A single fact. If Frappe Cloud ever releases or renames a live site's name for another reason (a rename, a migration), a live site would count as removed.

## Rationale

The rule has to fail closed, because marking a live site `Removed` stops its billing, pushes and removal on the control site while the customer keeps using it. A 403 alone can't carry that weight: it also means a revoked key, and maybe a renamed site. The released name is a separate fact that a broken key can't produce, since an unauthorized `domain_exists` call fails instead of answering `null` (AC-9 checks that before the first live drop). Limiting proof (b) to cases with `drop_started_on` set closes the rename gap: a renamed site can release its old name, but the control site only accepts that as an archive when it had itself started dropping that exact site. Option 3 was the runner up: it shows the key works, but not that the archive happened. Option 4 drops the second fact for one saved call, which is a poor trade on the one irreversible step.

Keeping `Archived` as a second proof costs nothing. It keeps every existing test and the 0011 table valid, and it covers Frappe Cloud showing archived sites to teams again later. A 403 without the released name still counts a `step_failed`, as any API error does today. The window between the 403 and the released name is under a minute against hourly polls, so a real archive clears it on the next poll. A revoked key still reaches `Failed` with an ops email after three hours, which is the alert you want for that case, and the daily reconcile finishes a case that failed during the window. Marking a `Dropping` case `Removed` when the proof holds without `archive_requested_on` (a mark save that failed) extends 0011's existing rule; the price of the `drop_started_on` limit is that a site someone archived by hand before any drop started waits for you instead of closing itself.

Moving the cleanup start to `mark_removed` fixes a real hazard: 0011 counts an archive with an unknown outcome as requested, so the old start could delete the DNS record behind a still running site's primary address if Frappe Cloud never got the call. Waiting for the proof costs at most one hourly run of name exposure, which is small next to breaking a live customer's address. For the Frappe Cloud part of the cleanup, `domain_exists` answers the real question directly ("is this name still held by our site?"), so one rule covers an archived site and a live one whose domain was removed by hand.

