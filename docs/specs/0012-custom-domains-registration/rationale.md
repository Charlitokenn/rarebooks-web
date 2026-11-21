# 0012. Custom domains on registration: rationale

## Context

> ⚠️ Premise note: the scope row reads as "add a DNS record and make it primary". The real risk sits around that step. Customer sites sit behind Frappe Cloud proxies that other teams share. So any `rarebooks.cc` name that points at those proxies but isn't tied to one of your sites (a wildcard, a record left after archive, an archived site name taken again) could be added as a domain by another Frappe Cloud team, and your customers' old links would open their site. The design treats name ownership and cleanup as part of the feature, not a nice to have.

Registration today (spec 0010 AC-10 and AC-11) leaves every customer site on its Frappe Cloud name, for example `site1.frappe.cloud`. You want each site on its own `rarebooks.cc` subdomain, with no manual DNS or Frappe Cloud dashboard steps, because the Billing Manager registering sites shouldn't need DNS access, and a hand made step gets skipped or mistyped.

Several parts of the control site depend on `site_url`. Every signed call (`site_calls.call_site`) and every push goes to it, with no redirect followed. `create_checkout` (spec 0008 AC-5) refuses a `return_url` whose host isn't `site_url`'s host. And the customer site builds its `return_url` from `get_url()`, which uses the host the user is actually browsing on. So the moment `site_url` changes, and the moment Frappe Cloud makes the new name primary, both matter: switch too early and calls go to an address that doesn't answer yet; switch without accepting the old host and checkouts started on an old bookmark fail.

Getting a working address takes several outside steps that can each take minutes or fail: a DNS record has to exist and be seen, Frappe Cloud has to accept the domain and get a Let's Encrypt certificate, and only then does HTTPS work. The control site already has a 5 minute job that moves registrations forward and proves them with a signed `control_ping` (spec 0010 AC-11), plus ops alerts and a daily digest.

Two sites already exist (demo-site and demo-us) and should move too, so the design needs a path for sites registered before this feature, not only new ones.

## Options considered

### Option 1: Cloudflare DNS, per site CNAME, resumable steps in the 5 minute job (chosen)

Move or keep the `rarebooks.cc` zone on Cloudflare. The control site creates one DNS only CNAME per site, pointing at the site's `.frappe.cloud` name, through an API token limited to DNS Edit on that zone. The 5 minute job then adds the domain on Frappe Cloud, waits for the certificate, pings the new address, and sets it primary while switching `site_url` in one transaction.

**Pros**:
- One small, well documented records API, and a token whose reach is one zone's DNS only.
- Each name points at exactly one site, which is what Frappe Cloud's DNS check expects, and nothing is left claimable.
- Reuses the 5 minute job, its dedup, its per site isolation and the signed ping as the proof of success.

**Cons**:
- A second outside provider and secret to run.
- The zone has to live on Cloudflare (a one time move if it is elsewhere).

### Option 2: Wildcard DNS, Frappe Cloud domains only

One `*.rarebooks.cc` record points at Frappe Cloud; the control site only calls the Frappe Cloud domain API. No DNS API or token at all.

**Pros**:
- No DNS provider integration and no DNS secret.
- Nothing to clean up in DNS at archive.

**Cons**:
- Every unused name resolves to Frappe Cloud's shared proxies, so any Frappe Cloud team could add an unused or removed `rarebooks.cc` name to their own site.
- Frappe Cloud's DNS check may not accept a wildcard for each site, which would make the plan fail at the first step.

### Option 3: Registrar's DNS API

Keep the zone at its registrar and use its API (Namecheap, Porkbun and similar).

**Pros**:
- No zone move.

**Cons**:
- Registrar API keys usually reach the whole account (every domain, sometimes transfers), not one zone's records.
- APIs differ a lot in quality; some need IP allowlisting, which a Frappe Cloud server can't promise.

### Option 4: Manual DNS with a checklist

The Billing Manager adds the record by hand; the control site does the rest.

**Pros**:
- No DNS code at all.

**Cons**:
- Goes against the scope's "no manual DNS steps" and puts DNS access in the Billing Manager's hands.
- Cleanup after archive depends on someone remembering, which is exactly where the takeover risk lives.

## Rationale

Option 1 is the only one that meets "no manual steps" while keeping every name tied to one site. That's the force that matters most here, because the failure mode (a customer's old link opening another team's site) is silent and hard to undo. Option 2 is attractive for having no secret, but it trades a contained secret for an open door on Frappe Cloud's shared proxies. Option 3 meets the goal with a much wider key. Cloudflare's scoped tokens keep the new secret's blast radius to one zone's DNS, which is smaller than the Frappe Cloud key the control site already holds.

The steps run in the existing 5 minute job, one step per site per run, each checking its own result first. That's the same shape as the config ping: certificates take minutes, the job is already deduplicated and isolates each site, and a step that can be repeated means a crash or timeout costs one run, not a stuck site. The domain work starts only after config is Active, so a DNS or certificate problem can never delay billing, pushes or removal. Those all keep using the `.frappe.cloud` `site_url` until the switch.

The switch is ordered so it can't point at a broken address: a signed ping must answer at the new name before `set_host_name` is called, and `site_url` changes in the same transaction as the Primary success. No redirect is set, so the old name keeps working for old links and as a fallback. Because users may browse on either name, `create_checkout` accepts both the `site_url` host and the row's own `site` host. That host comes from the registry, so it isn't an open redirect.

Labels are never reused and records are deleted promptly after archive, for the same reason: no name should ever lead to a different customer than the one it was given to. The 2 hour timeout (rather than config's 1 hour) leaves room for slow certificate issuing without false alarms, and Retry domain resumes at the failed step, so a certificate that is already fine isn't thrown away.

Smaller calls made while writing:
- **Clash check also asks Frappe Cloud `domain_exists`**, so a name already attached somewhere on Frappe Cloud is refused before any DNS write. Runner up: rely on `add_domain` failing later, which would leave a record behind.
- **Cloudflare or Frappe Cloud unreachable at registration refuses the action.** The subdomain is required and must be checked before anything is written. Runner up: register anyway and check later, which allows a clash to be stored.
- **`Broken` certificates are retried at most every 30 minutes** through a cache key, so Let's Encrypt's failure limits aren't hit. Runner up: a new field, which isn't worth a column.
- **An unknown `set_host_name` outcome calls it again next run**, because setting the same primary twice is harmless, unlike archive (spec 0011).
- **Cleanup runs in the hourly removal round**, which already handles the Archived poll and `mark_removed`. Runner up: the 5 minute job, which only looks at Active sites.
- **A foreign record of the same name fails at once and is never overwritten**: it was made by hand for a reason, and overwriting DNS is the one action here that could break something outside RareBooks.
