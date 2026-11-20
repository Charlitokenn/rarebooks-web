# 0010. Hosting on Frappe Cloud: rationale

## Context

Specs 0007 and 0008 were written for a server you run yourself. They assume a host crontab that starts `bench books-removal-run` every hour, a secrets file at `<bench>/config/books-runner.json`, the MariaDB root login for dropping sites, a separate `control` Linux user with its own supervisor, Redis passwords and nginx block, and a bench command that writes `site_config.json` when a site is registered or its secret rotates.

You host on a Frappe Cloud dedicated server (Unified plan, Hetzner Falkenstein). Frappe Cloud runs each bench in containers it manages. You get bench SSH at most, not root; files written into the bench outside `sites/` are lost on the next deploy; site config is managed through the dashboard or its API; and sites are created and archived by Frappe Cloud, so dropping one behind its back would leave its records out of sync. None of the host pieces above can run there.

Two facts found during this design shape the options. Frappe stops running the scheduler on a site with no recent logins when it runs on Frappe Cloud (`dormant_days` in System Settings), and abandoned trials are exactly those sites, though jobs enqueued by someone else still run. And archiving through the Frappe Cloud API takes an offsite backup first by default, so a removed site still leaves a copy under Frappe Cloud's retention policy.

Milestones 1 to 4 of both specs are built, rollout is not. So nothing live has to move, but real code is replaced.

## Options considered

### Option 1: Each customer site runs its own removal round

Each site's hourly scheduled job reports to the control site, gets instructions, builds and uploads its export, and the control site archives through the Frappe Cloud API.

**Pros**:
- Simple signing: every call is the site calling out with its own secret, as today.
- No fan out job on the control site.

**Cons**:
- Frappe skips the scheduler on dormant sites on Frappe Cloud, so an abandoned trial, the main case, would never report and never be removed.
- Changing `dormant_days` on every customer site to work around it fights the platform and wastes resources on idle sites.

### Option 2: The control site drives everything (chosen)

An hourly job on the control site calls each site's signed endpoints, asks it to enqueue its export job, hands it a presigned upload URL, and archives through the Frappe Cloud API after every check.

**Pros**:
- Works on dormant sites, since enqueued jobs still run.
- Customer sites hold no storage or hosting credential.
- One place decides and acts, so the drop gates and the cap are checked where the action happens.

**Cons**:
- New signed endpoints on the customer site, and answers must be signed too.
- The control site's scheduler becomes the single clock; it needs `dormant_days` 0 and a heartbeat.
- One API key with team wide power lives on the control site.

### Option 3: Keep the runner on a self managed VPS

Move hosting off Frappe Cloud (or add a VPS just for the runner with database access).

**Pros**:
- The built runner and its tests are kept as is.

**Cons**:
- You chose Frappe Cloud; a VPS reached into Frappe Cloud's databases isn't possible, and moving hosts gives up managed backups, updates and scaling.
- Still needs root credentials on a box you patch yourself.

## Rationale

The forces are: no host access, dormant sites that skip their own scheduler, an irreversible step that must stay behind every safety gate, and a small operator team. Option 2 is the only one that removes abandoned trials reliably on Frappe Cloud, because the control site's own scheduler (kept non dormant) enqueues the work and enqueued jobs still run on dormant sites. It also shrinks the credential footprint: sites keep only their own secret, the R2 write power becomes a 6 hour presigned URL per attempt, and the archive power sits in one module behind guards (registry, bench group, not itself, fresh unpaid report).

The engineer's picks (presigned URLs, Frappe Cloud API archive and config, one settings doc, removing the runner) all follow from this. The cost accepted is a team wide API key and Frappe Cloud's own backups of archived sites, both stated in the spec instead of hidden.

Smaller calls made while writing: answers from sites are signed and echo `issued_at`, as the runner's were, since a forged "locked, unpaid" answer would lead to a removal (runner up: trust HTTPS alone). One job per site per round, deduplicated, keeps one slow site from delaying others (runner up: one sequential job). The daily cap is counted under a row lock on the settings doc because site jobs run in parallel. Exports are built in `sites/<site>/books-removal/` so Frappe Cloud's file backups don't copy them (runner up: `/tmp`, which may be small in the container). The 5 minute ping confirms a config write took effect, because `update_config` runs as a Frappe Cloud job and silently drops blocked keys.

## References

See the References section of [index.md](index.md).
