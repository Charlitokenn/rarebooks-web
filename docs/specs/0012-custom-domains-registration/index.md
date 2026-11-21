# 0012. Custom domains on registration

**Date**: 2026-11-21
**Status**: Proposed

Amends: spec [0010](../0010-frappe-cloud-hosting/index.md) (AC-10 registration gains a subdomain, AC-11 the 5 minute job gains the domain steps, AC-13 the Frappe Cloud client gains the domain methods, AC-16 the digest) and spec [0008](../0008-billing-control-site/index.md) (AC-5, the `return_url` host rule). Every other rule in those specs still holds.

## Summary

When you register a hosted site, the control site now also gives it its own address under `rarebooks.cc` (for example `site1.rarebooks.cc`). It creates the DNS record at Cloudflare, adds the domain on Frappe Cloud, waits for the certificate, proves the new address reaches the right site with a signed ping, and only then makes it the main address and switches `site_url`. Until then the site keeps working on its `.frappe.cloud` address, and that address keeps working afterwards too. A failure shows on the form with a Retry domain button, and when a site is archived its DNS record and domain are removed so no one else can take the name.

## Requirements

**User stories**:
- As a Billing Manager, I want a new site to get its `rarebooks.cc` address as part of registering it, so I never touch DNS or the Frappe Cloud dashboard by hand.
- As a Billing Manager, I want sites that already exist (demo-site, demo-us) to get an address the same way, so every site ends up on `rarebooks.cc`.
- As a site owner, I want my old `.frappe.cloud` links and a checkout started on either address to keep working, so the move is invisible to me.
- As the operator, I want a removed site's name to be cleaned up and never handed to anyone else, so old links and emails can never open another customer's books.

**Acceptance criteria**:
- **AC-1**: A subdomain label is accepted only when it is 3 to 40 characters of lowercase `a` to `z`, `0` to `9` and hyphens, does not start or end with a hyphen, does not start with `xn--`, and is not on the reserved list (`www`, `api`, `app`, `control`, `billing`, `pay`, `mail`, `smtp`, `admin`, `support`, `help`, `status`, `docs`, `demo`, `test`, `staging`). Input is trimmed and lowercased first. Anything else is refused with a translated message naming the rule, and nothing is written.
- **AC-2**: A label is refused as taken, with a message saying why and nothing written, when any Books Hosted Site (Removed ones included) holds it as `subdomain`, when Cloudflare has a DNS record of any type for `<label>.<books_site_domain>` in the zone, or when Frappe Cloud says the domain is already in use (`domain_exists`). If Cloudflare or Frappe Cloud can't be asked, the action is refused with "try again" and nothing is written. The `subdomain` column is unique in the database too, so two concurrent requests can't both win: a duplicate key error on insert or save becomes the same "taken" refusal. A blank `subdomain` is always stored as NULL (the controller's `validate()` turns `""` into None), since MariaDB's unique index allows many NULLs but only one empty string.
- **AC-3**: Register site (spec 0010 AC-10) gains a required Subdomain field, prefilled in the dialog from the Frappe Cloud site name's first label (`site1.frappe.cloud` gives `site1`) and editable. `register_site` takes `subdomain`, runs AC-1 and AC-2 with the existing checks before anything is written, and stores it on the new row with `domain_status` blank. Registration still finishes on the `.frappe.cloud` address exactly as spec 0010 AC-10 and AC-11 describe; `site_url` is the URL typed in the dialog.
- **AC-4**: A Billing Manager can press Add domain on a Books Hosted Site that has no `subdomain`, is not Removed and has no Dropping case. It asks for a label (prefilled as in AC-3), runs AC-1 and AC-2, and stores it with `domain_status` blank. This is how demo-site, demo-us and every site registered before this spec get an address.
- **AC-5**: The 5 minute job (`books-config-ping`, spec 0010 AC-11) also moves each site that has a `subdomain`, `domain_status` not set or Working (`domain_step` not Cleanup), `status` Active, `config_status` Active, no `pending_secret` and no Dropping case, by doing at most one step per site per run, in this order: DNS, Frappe Cloud, Certificate, Ping, Primary. Each step first checks whether its work is already done and, if so, moves on, so repeating a step is safe. A site with `domain_status` blank starts at DNS and becomes Working with `domain_step_started_on` set. Each new step sets `domain_step` and restarts `domain_step_started_on`. One site's failure is logged and rolled back without stopping the others (the existing `_isolated` rule). Every step follows one lock rule: read the row `for_update`, check again that it is still eligible and still on that step, commit; make the outside call with no lock held; then read it `for_update` again, check the same things, and write. A site with `domain_status` Working that the job skips because it isn't eligible (config not Active, a rotation pending, a Dropping case) has `domain_step_started_on` restarted, so the 2 hour clock of AC-10 only counts time the site could actually move. At every step except Primary, a `FrappeCloudError`, an `OutcomeUnknown` or a Cloudflare 429 or 5xx means stay on the step and try again next run, logged once per site and step start, not every run.
- **AC-6**: DNS step: the control site looks up records named `<subdomain>.<books_site_domain>` in the Cloudflare zone. A DNS only CNAME whose target is the row's `site` (compared ignoring case and a trailing dot) is taken as done and its id stored in `dns_record_id`; this also covers a create whose answer was lost before the id was stored. A proxied CNAME to `site` makes the site Failed at once with an ops email saying to switch it to DNS only. Any other record of that name makes the site Failed at once, with an ops email saying to remove that record before pressing Retry domain, and is never overwritten. With no record, it creates a CNAME to `site`, DNS only (`proxied` false), TTL automatic, comment `rarebooks <site>`, and stores the returned id. A Cloudflare answer counts only when it is HTTP 200 with `success` true; ids come from `result`. A create refused because the record already exists reads the records again in the same run. A 401 or 403 from Cloudflare makes the site Failed at once (the token is wrong), not after 2 hours.
- **AC-7**: Frappe Cloud step: if Frappe Cloud already lists the domain on the site, the step is done. Otherwise it calls `check_dns`, and only when that passes calls `add_domain`; a failed `check_dns` waits for the next run (DNS can take minutes to be seen). Certificate step: done when Frappe Cloud shows the domain `Active`. `Pending` or `In Progress` waits. `Broken` calls `retry_add_domain`, at most once every 30 minutes per site (a `frappe.cache` key), so a failing certificate isn't requested again every 5 minutes. A clear answer from `add_domain` that the domain is already in use elsewhere on Frappe Cloud makes the site Failed at once, with an ops email.
- **AC-8**: Ping step: the control site sends a signed `control_ping` to `https://<subdomain>.<books_site_domain>`, not to `site_url`, through `call_site` with a new `url` override (never `_pinged`, which skips the rotation fallback), so the same signing and `destinations.post` rules as every site call apply (spec 0010 AC-2). Only a verified answer that echoes the row's `site` passes. Primary step: under the row lock, it calls `set_host_name` for the domain. On success, in the same transaction, it sets `site_url` to `https://<subdomain>.<books_site_domain>` and `domain_status` Active, then commits. Before calling it, the step checks whether Frappe Cloud already shows the domain as primary (the answer shape is fixed by build task 1), and if so only switches. An unknown outcome (sent, no answer) keeps the step, and the next run checks and calls `set_host_name` again (it is safe to repeat). If task 1 finds `set_host_name` asynchronous, the step waits until Frappe Cloud shows the domain primary before switching `site_url`. No redirect is set: the `.frappe.cloud` address keeps serving the site.
- **AC-9**: `create_checkout` (spec 0008 AC-5) accepts a `return_url` that is `https://` and whose host is one of: the host of the row's `site_url`, the row's `site` (its `.frappe.cloud` name), or `<subdomain>.<books_site_domain>` when `subdomain` is set. All three come from the registry, so this is still no open redirect. Any other host still gets 400. A checkout started on either address, before, during or after the switch, works.
- **AC-10**: A site whose current step has run for 2 hours since `domain_step_started_on` without finishing becomes `domain_status` Failed, with `domain_step` kept, and `books_ops_email` gets one email (through `alerts.send_ops`, once per site and step start) naming the site, the step and "press Retry domain". A Failed site gets no more steps. Retry domain (Billing Manager, on a Failed site that is not Removed) sets `domain_status` Working and restarts `domain_step_started_on`, keeping `domain_step`, so the work goes on from the failed step. Through all of this the site keeps working on its current `site_url`, and billing, pushes and removal are not affected.
- **AC-11**: Cleanup starts when the site's archive is requested: in the same transaction that sets `archive_requested_on` (spec 0011), or in `mark_removed` (spec 0010 AC-7) if it wasn't started then, a site with a `subdomain`, no `domain_cleaned_on` and `domain_step` not already Cleanup gets `domain_step` Cleanup, `domain_status` Working and `domain_step_started_on` now. Neither place makes an outside call; a repeat of either changes nothing. A cleanup sweep, run at the start of every hourly round before the `mode` check (so it runs with mode off too), works through every row with `domain_step` Cleanup and `domain_status` Working, under AC-5's lock rule and the `_isolated` rule. It deletes the Cloudflare record (`dns_record_id`, or the CNAME to `site` found by name), and removes the domain on Frappe Cloud if it is still listed; it skips the bench group check (an archived site may show no group). Each part counts as done when: the CNAME of ours is gone (a record that isn't ours is left alone and counts as gone); Frappe Cloud no longer lists the domain, or answers that the site is archived or the domain isn't found; or the DNS step never ran (no `dns_record_id` and no CNAME of ours by that name). When both parts are done it sets `domain_cleaned_on` and clears `domain_status`, keeping `subdomain` so the label is never reused (AC-2). Any error waits for the next hourly sweep. After 24 hours without success, `books_ops_email` gets one email. Retry domain is not offered on a site in Cleanup or Removed.
- **AC-12**: Only a Billing Manager can register a site, Add domain or Retry domain; each action checks it on the server with `frappe.only_for`, and others get 403. `subdomain`, `domain_status`, `domain_step`, `domain_step_started_on`, `dns_record_id` and `domain_cleaned_on` are read only in desk for every role and written only by `registry.py` (and `mark_removed` for AC-11). The subdomain can't be changed once set. The Cloudflare token, the Frappe Cloud key and their request headers are never logged or put in an error text.
- **AC-13**: Only `providers/cloudflare.py` talks to Cloudflare, at `https://api.cloudflare.com/client/v4`, with a 30 second timeout and no redirect followed, reading `cloudflare_api_token`, `cloudflare_zone_id` and `books_site_domain` from the control site's `site_config.json`. It has three functions only: `find_records(name)`, `create_cname(name, target, comment)` and `delete_record(record_id)`. The Frappe Cloud client (spec 0010 AC-13) gains `domains`, `domain_exists`, `check_dns`, `add_domain`, `retry_add_domain`, `set_host_name` and `remove_domain`, with the same error rules (`FrappeCloudError`, `OutcomeUnknown`). If any of the three Cloudflare keys is missing, Register site and Add domain refuse with "Set the custom domain config first", and no domain step runs.
- **AC-14**: The daily digest (spec 0010 AC-16) lists every site whose `domain_status` is Working for more than 30 minutes, or Failed, with its step. The Books Hosted Site form shows a headline with the domain status and step when it isn't Active or blank, and shows Add domain or Retry domain per AC-4 and AC-10.

## Decision

**Chosen option**: Option 1: Cloudflare DNS, per site CNAME records, a resumable step machine in the 5 minute job

The control site owns the whole path from label to main address: it validates the label, writes one DNS only CNAME per site in a Cloudflare zone through a token limited to DNS Edit on that zone, adds and verifies the domain through the Frappe Cloud API, proves the new address with a signed ping, and only then sets it primary and switches `site_url`, cleaning up both records after archive.

**Implementation skills**: `frappe-code-review` (`frappe/skills`, `.agents/skills/frappe-code-review/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `cloudflare` (session skill, for the DNS records API and token scopes)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch** (Books Hosted Site, new fields, all read only, in a new "Domain" section):

| Field | Type | Required | Notes |
|---|---|---|---|
| `subdomain` | Data, unique | set on new registrations | The label alone (`site1`). Kept after Removed, never reused |
| `domain_status` | Select: (blank), Working, Active, Failed | no | Blank means no step has started, or cleanup finished |
| `domain_step` | Select: DNS, Frappe Cloud, Certificate, Ping, Primary, Cleanup | no | The step in progress, or the one that failed |
| `domain_step_started_on` | Datetime (UTC) | no | Starts the 2 hour clock (AC-10) and the 24 hour cleanup clock (AC-11) |
| `dns_record_id` | Data | no | Cloudflare's record id, for cleanup |
| `domain_cleaned_on` | Datetime (UTC) | no | Set when the record and the Frappe Cloud domain are both gone |

No new DocType and no new link. The full domain is `{subdomain}.{books_site_domain}`, built when needed. The `.frappe.cloud` host is the row's `site`. Existing rows get the new fields empty; no backfill.

**State transitions** (`domain_status` / `domain_step`):

```
(blank) ──first run──▶ Working/DNS ─▶ Working/Frappe Cloud ─▶ Working/Certificate ─▶ Working/Ping ─▶ Working/Primary ─▶ Active
Working/<any step> ──2 hours in one step, or a foreign DNS record──▶ Failed/<step> ──Retry domain──▶ Working/<same step>
<any> ──archive requested (or mark_removed)──▶ Working/Cleanup ──both removed──▶ (blank), domain_cleaned_on set
Working/Cleanup ──24 hours──▶ alert once, cleanup keeps retrying hourly
```

Triggers: the 5 minute job (forward steps), the Billing Manager (Retry domain), the archive request or `mark_removed` (start cleanup), the cleanup sweep at the start of the hourly round (cleanup).

**API surface** (control site, desk calls; all `POST`, whitelisted, type annotated):

| Method | Inputs | Output | Auth | Errors |
|---|---|---|---|---|
| `rarebooks_control.registry.register_site` | `site`, `owner_email`, `site_url`, `subdomain` (new, required) | `{site, config_status}` | Billing Manager | 403; 417 with the AC-1, AC-2, AC-13 refusal or the spec 0010 refusals |
| `rarebooks_control.registry.add_domain` | `site`, `subdomain` | `{subdomain}` | Billing Manager | 403; 404 no site; 417 Removed, Dropping, already has a subdomain, AC-1, AC-2, AC-13 |
| `rarebooks_control.registry.retry_domain` | `site` | `{domain_status, domain_step}` | Billing Manager | 403; 404; 417 Removed or not Failed |
| `rarebooks_control.api.create_checkout` (changed rule only) | `return_url` | as spec 0008 | site HMAC | 400 host is neither `site_url`'s nor `site` |

Outgoing calls:

| Client | Call | Used by |
|---|---|---|
| Cloudflare | `GET /zones/{zone}/dns_records?name=<fqdn>` | AC-2, AC-6, AC-11 |
| Cloudflare | `POST /zones/{zone}/dns_records` `{type: CNAME, name, content: site, proxied: false, ttl: 1, comment}` | AC-6 |
| Cloudflare | `DELETE /zones/{zone}/dns_records/{id}` | AC-11 |
| Frappe Cloud | `press.api.site.domain_exists(domain)` | AC-2 |
| Frappe Cloud | `press.api.site.domains(name)` (domain, status) | AC-7, AC-11 |
| Frappe Cloud | `press.api.site.check_dns(name, domain)`, `add_domain(name, domain)`, `retry_add_domain(name, domain)` | AC-7 |
| Frappe Cloud | `press.api.site.set_host_name(name, domain)` | AC-8 |
| Frappe Cloud | `press.api.site.remove_domain(name, domain)` | AC-11 |
| Customer site | `control_ping` at `https://<fqdn>` | AC-8 |

The Frappe Cloud method names and their answer shapes are from the open source `press` app as of this writing; build task 1 confirms them against the live API before any code relies on them.

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| Register site dialog | Subdomain prefill | the typed Frappe Cloud name, up to its first dot |
| `register_site`, `add_domain` | label | the `subdomain` input, trimmed and lowercased |
| clash check, DNS step | full domain | `subdomain` + `.` + `books_site_domain` (site config) |
| clash check | registry use | `subdomain` unique column, Removed rows included |
| clash check | DNS use | Cloudflare `find_records(fqdn)` |
| clash check | Frappe Cloud use | `domain_exists(fqdn)` |
| DNS step | CNAME target | the row's `site` |
| DNS step | zone, token | `cloudflare_zone_id`, `cloudflare_api_token` (site config) |
| DNS step | record id | Cloudflare's create answer, or the found record |
| Certificate step | certificate state | `domains(site)` status for the fqdn |
| Certificate step | last retry time | `frappe.cache` key `domain-retry:<site>`, 30 minute expiry |
| Ping step | URL | `https://` + fqdn |
| Ping step | secret | `control_secret` (or `pending_secret` on a 401 during a rotation, the existing `call_site` rule) |
| Primary step | new `site_url` | `https://` + fqdn |
| 2 hour rule | clock | `domain_step_started_on` |
| alert | recipient | `books_ops_email` via `alerts.send_ops` |
| alert | once only | `removal_mail._first_alert("domain:<site>:<step>:<domain_step_started_on>")` |
| `create_checkout` | allowed hosts | host of `site_url`, `site`, and `subdomain` + `.` + `books_site_domain` when `subdomain` is set |
| cleanup | start | `archive_requested_on` being set (spec 0011), else `mark_removed` |
| cleanup | record to delete | `dns_record_id`, else the CNAME to `site` found by name |
| cleanup | done | Cloudflare and `domains(site)` per AC-11's done rules |
| digest | stuck sites | `domain_status`, `domain_step`, `domain_step_started_on` |

**Key invariants**:
- `site_url` changes only in the Primary step, in the same transaction as `domain_status` Active, and only after a verified ping at the new address in an earlier step.
- A label, once stored on any row, is never stored on another (unique column) and never removed from its row.
- The control site never overwrites or deletes a DNS record that isn't the CNAME to that row's `site`.
- No domain step runs for a site that is Removed or has a Dropping case, except cleanup.
- No outside call (Cloudflare, Frappe Cloud, the customer site) is made while the Books Hosted Site row is locked.
- Domain steps never change billing, push or config fields; a domain failure never blocks billing, pushes or removal.

**Security model**:
- Billing Manager only, checked on the server (AC-12). System Manager and Removal Manager read the new fields.
- The Cloudflare token is an API token (not the global key) with one permission, Zone DNS Edit, on the `rarebooks.cc` zone only. It lives in the control site's `site_config.json` like the Frappe Cloud key, and is never logged.
- Takeover risk: customer sites sit behind Frappe Cloud proxies shared with other teams. A name that points at them but belongs to no site of yours could be claimed by another team. So records are per site (no wildcard), point at the site's own `.frappe.cloud` name, are added on Frappe Cloud straight after DNS, and are deleted promptly after archive (AC-11).
- The ping at the new address uses the existing signed call path, so a hijacked or misrouted name fails verification and `site_url` never moves to it.
- No new personal data. The label may resemble a business name; it is public by nature (DNS).

**Configuration required** (control site `site_config.json`):
- `books_site_domain`: the parent zone name, `rarebooks.cc`
- `cloudflare_zone_id`: the zone's id
- `cloudflare_api_token`: Zone DNS Edit on that zone only. Secret, never logged.

**Critical test scenarios**:
- Label rules: `ab`, `-ab`, `ab-`, `xn--ab`, `www`, `Ab Cd`, 41 characters are refused; ` Site1 ` is stored as `site1`. Verifies **AC-1**.
- Clash: a Removed row holding the label, an existing A record by that name, `domain_exists` true, and Cloudflare timing out each refuse with nothing written; two concurrent registrations with the same label leave one row and the other gets the taken message; two rows with no subdomain save fine. Verifies **AC-2**.
- Registration: a good one stores `subdomain`, stays on `.frappe.cloud`, goes config Active as before, then walks DNS to Active over five runs against stubs, ending with `site_url` on the new address. Verifies **AC-3**, **AC-5**, **AC-8**.
- Add domain on an existing Active site walks the same path; refused on a Removed site, a Dropping site and a site that already has a subdomain. Verifies **AC-4**.
- No step runs while `config_status` is Pending or Failed, a rotation is pending, or a case is Dropping, and the clock restarts while skipped (a site skipped for 3 hours doesn't fail on resume). Verifies **AC-5**, **AC-10**.
- DNS: an existing CNAME to `site` is adopted; a CNAME to another target makes it Failed with one email and is not touched; a create stores the id with `proxied` false; a lost create answer is adopted next run; a proxied CNAME to `site` fails; a Cloudflare 403 fails at once. Verifies **AC-6**.
- Frappe Cloud: `check_dns` false waits; `Broken` calls `retry_add_domain` once in 30 minutes, not every run. Verifies **AC-7**.
- Ping fails (unsigned answer, wrong `site` echo): no Primary, `site_url` unchanged. `set_host_name` times out: step kept, called again next run, `site_url` switched once. Verifies **AC-8**.
- Checkout: `return_url` on the `.frappe.cloud` host and on the new host both pass before and after the switch; another host gets 400. Verifies **AC-9**.
- A step stuck 2 hours goes Failed with one email (not one per run); Retry domain resumes at that step and the clock restarts. Verifies **AC-10**.
- Archive: setting `archive_requested_on` starts cleanup and a repeat of `mark_removed` doesn't restart its clock; the sweep runs with mode off; a Cloudflare error retries hourly; a foreign record and an "archived" answer from Frappe Cloud count as gone; after success `domain_status` is blank and `subdomain` kept; a 24 hour failure sends one email. Verifies **AC-11**.
- Permissions: a System Manager calling `register_site`, `add_domain` or `retry_domain` gets 403; desk shows the fields read only. Log output in every test holds no token. Verifies **AC-12**.
- Missing `cloudflare_api_token` refuses Register site and Add domain and runs no step; `providers/cloudflare.py` sets `allow_redirects=False`. Verifies **AC-13**.
- The digest lists a Failed site and one Working for 40 minutes, not one Working for 10. Verifies **AC-14**.

## Build plan

Tracer Bullet: Milestone 1 takes one existing site (the Add domain path) from no domain to `site_url` on `rarebooks.cc`, end to end against stub Cloudflare and Frappe Cloud clients, before registration, failures or cleanup are added.

**Milestone 1: The thread, one existing site to its new address**
1. [ ] Confirm the Frappe Cloud domain methods (`domain_exists`, `domains`, `check_dns`, `add_domain`, `retry_add_domain`, `set_host_name`, `remove_domain`) against the live API on a throwaway site: their answer shapes, the domain status strings, how the primary domain is shown, whether `set_host_name` is asynchronous, what `host_name` changes on the site (`get_url()` in and outside a request), and what `domains` and `remove_domain` answer for an archived site. Note any difference in this spec before coding; if `host_name` matters to nothing, drop the Primary step's `set_host_name` call. Satisfies **AC-13**.
2. [ ] Books Hosted Site: the six fields in a Domain section (read only, `subdomain` unique), exported from desk; tests' `make_site` and the field lists updated. Satisfies **AC-12**.
3. [ ] `providers/cloudflare.py` (three functions, config keys, no redirects, nothing logged) and the new Frappe Cloud client functions, with tests that patch them. Satisfies **AC-13**.
4. [ ] `registry.add_domain` with the AC-1 and AC-2 checks, and the Add domain button on the form. Satisfies **AC-1**, **AC-2**, **AC-4**.
5. [ ] The step machine in the 5 minute job (`run_domain_steps` called from `run_pings`): DNS, Frappe Cloud, Certificate, Ping (`call_site` gains a `url` override), Primary with the locked `site_url` switch, all under AC-5's lock rule. Satisfies **AC-5**, **AC-6**, **AC-7**, **AC-8**.
6. [ ] `api._is_return_url` accepts the `site` host and the subdomain host too. Satisfies **AC-9**.

**Milestone 2: Registration with a subdomain**
7. [ ] `register_site` takes the required `subdomain` and runs AC-1 and AC-2 before any write; the Register site dialog gets the prefilled field. Satisfies **AC-3**, **AC-1**, **AC-2**.

**Milestone 3: Failures, retry and visibility**
8. [ ] The 2 hour rule, the foreign record rule, one ops email per step start, `retry_domain` and the Retry domain button, the 30 minute certificate retry key. Satisfies **AC-6**, **AC-7**, **AC-10**, **AC-12**.
9. [ ] The form headline and the digest lines. Satisfies **AC-14**.

**Milestone 4: Cleanup at archive**
10. [ ] Cleanup start where `archive_requested_on` is set and in `mark_removed`; the cleanup sweep at the start of `run_round` before the mode check; the done rules; the 24 hour alert. Satisfies **AC-11**.

**Milestone 5: Rollout**
11. [ ] Put `rarebooks.cc` on Cloudflare DNS if it isn't there, check for a CAA record that would block Let's Encrypt, create the zone scoped token, and set the three config keys on the control site. Satisfies **AC-13**.
12. [ ] Add domain on demo-site and demo-us, watch both reach Active, check a checkout from each address, then register one new staging site with a subdomain and archive a throwaway one to see its record and domain removed. Satisfies **AC-3**, **AC-4**, **AC-8**, **AC-9**, **AC-11**.

## Consequences

**Positive**:
- Registration stays one action with no DNS or Frappe Cloud dashboard work, and every site gets a branded address.
- The switch is proven before it happens, so a broken DNS or certificate never moves `site_url` to an address that doesn't work.
- Old `.frappe.cloud` links, bookmarks and in flight checkouts keep working.
- Names are never reused and records don't dangle, which closes the takeover and wrong tenant risks.

**Negative / tradeoffs**:
- A second outside provider (Cloudflare) and a second powerful token to guard, though limited to one zone's DNS.
- Every site has two working addresses for good, so the same books are reachable under two names (no SEO concern for a signed in app, but two places a user might bookmark).
- The Frappe Cloud client grows from three methods to ten, which widens what a bug could do with the team wide key; `remove_domain` and `set_host_name` are guarded by the same "registered site in `books_bench_group`" checks as the rest.
- The Frappe Cloud domain methods are not a documented public API, so they can change without notice. Task 1 checks them, and a change shows up as Failed steps, not a broken site.
- Labels are never reused, so good names are used up for good.

**Neutral**:
- No change to the customer site code in this repo is expected: nothing there checks the request host, `get_url()` follows the request host (and `host_name` outside a request, task 1 confirms), and the removal report carries the site URL it was called on. After the switch that is the new address, so `case.site_url` and the removal warning emails use it too.
- A subdomain can't be renamed in this slice (see Follow-up).

## Follow-up

- [ ] Add to the scope's Deferred list: renaming a site's subdomain (Change domain), with the old label retired; watching an Active domain for later drift (a certificate gone Broken, a record changed by hand).
- [ ] Add the `providers/cloudflare.py` rule (only module that talks to Cloudflare, its three config keys, never logged) to `rarebooks_control/AGENTS.md` through `/sync`, next to the ClickPesa and Frappe Cloud rules.
