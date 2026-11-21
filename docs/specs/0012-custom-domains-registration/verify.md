# Verify: custom domains on registration · spec 0012 · updated 2026-11-21
_Steps derived from spec 0012 acceptance criteria and its Value sourcing table. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual (control site desk, staging, with the three Cloudflare keys set)
- [ ] Books Hosted Site list → Register site → type `site1.frappe.cloud` → Subdomain prefills `site1`; edit it, then change the site name → your edit is kept → AC-3
- [ ] Register with Subdomain ` Site1 ` → row stores `site1`, `domain_status` blank, `site_url` is the URL typed → AC-1, AC-3
- [ ] Register with `ab`, `-ab`, `xn--ab`, `www`, `Ab Cd` → each refused with the rule named, no row written → AC-1
- [ ] Register with a label held by a Removed row, a label with an A record in the zone, a label Frappe Cloud already uses → each refused as taken, no row → AC-2
- [ ] Open demo-site (no subdomain) as Billing Manager → Add domain shows, prefilled `demo-site` → save → subdomain stored → AC-4
- [ ] Add domain is refused on a Removed site, on a site with a Dropping case, and on a site that already has a subdomain → AC-4
- [ ] Over five 5 minute runs the site goes DNS → Frappe Cloud → Certificate → Ping → Primary → Active; Cloudflare shows a DNS only CNAME to the `.frappe.cloud` name with comment `rarebooks <site>` → AC-5, AC-6, AC-7
- [ ] `site_url` changes to `https://<subdomain>.rarebooks.cc` only in the run that sets Active; `https://<site>.frappe.cloud` still serves the site afterwards → AC-8
- [ ] The form shows the domain headline while Working or Failed, and none once Active → AC-14
- [ ] Start a checkout from the `.frappe.cloud` address and one from the new address, before and after the switch → both return; a `return_url` on another host gets 400 → AC-9
- [ ] Put an A record on a new label's name before its DNS step → site goes Failed at DNS, one ops email, the record is untouched; remove it, press Retry domain → it goes on from DNS → AC-6, AC-10
- [ ] Archive a throwaway site → at the archive request `domain_step` is Cleanup; after the next hourly round (mode off too) the CNAME and the Frappe Cloud domain are gone, `domain_cleaned_on` set, `subdomain` kept → AC-11
- [ ] As System Manager, call `register_site`, `add_domain`, `retry_domain` → 403; the Domain fields are read only in desk → AC-12

## Value sourcing (one step per source)
- [ ] Prefill: type `shop.frappe.cloud` → `shop` (the name up to its first dot) → AC-3
- [ ] Full domain: change `books_site_domain` on a test site to `example.test` → the clash check and the DNS step use `<label>.example.test` → AC-2, AC-6
- [ ] CNAME target is the row's `site`, compared ignoring case and a trailing dot (`SITE1.FRAPPE.CLOUD.` is adopted) → AC-6
- [ ] Record id: a create whose answer is lost is adopted by id on the next run → AC-6
- [ ] Certificate state comes from `domains(site)`; a Broken certificate calls `retry_add_domain` at most once per 30 minutes (`domain-retry:<site>`) → AC-7
- [ ] Ping URL is `https://<fqdn>`, not `site_url`; a name that points at another site fails the signed ping and `site_url` stays → AC-8
- [ ] 2 hour clock is `domain_step_started_on`, restarted while the site is skipped (config Pending, rotation, Dropping) → AC-5, AC-10
- [ ] One ops email per site and step start, to `books_ops_email` → AC-10
- [ ] Return URL hosts: `site_url`'s host, `site`, and `<subdomain>.<books_site_domain>` → AC-9
- [ ] Cleanup starts at `archive_requested_on`, else in `mark_removed`; a repeat doesn't restart its clock → AC-11
- [ ] Digest lists Failed sites and Working ones over 30 minutes, not one Working for 10 → AC-14

## Commands
- [ ] `bench --site <site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_domains` → 28 tests pass → AC-1 to AC-14
- [ ] `bench --site <site> run-tests --app rarebooks_control` → every test passes → regressions
- [ ] `uvx ruff@0.14.10 check rarebooks_control && uvx ruff@0.14.10 format --check rarebooks_control` → clean → AC-13 (house rules)
- [ ] `grep -rn "cloudflare_api_token" <bench>/logs` after a run → only config reads, never the value → AC-12

## Still owed before rollout (build task 1)
- [ ] On a throwaway Frappe Cloud site, confirm `domains`, `domain_exists`, `check_dns`, `add_domain`, `retry_add_domain`, `set_host_name` and `remove_domain` answer as the `press` source shows (checked from source only on 2026-11-21) → AC-13

## Acceptance-criteria coverage
- AC-1 … register refusals, prefill trim, `TestLabel` · AC-2 … taken checks, `books_site_domain` · AC-3 … register and prefill · AC-4 … Add domain · AC-5 … five runs, skipped clock · AC-6 … CNAME, foreign record, lost create · AC-7 … certificate retry · AC-8 … `site_url` switch, ping URL · AC-9 … checkout from both hosts · AC-10 … Failed, Retry domain · AC-11 … archive cleanup · AC-12 … 403, read only, log grep · AC-13 … missing keys, task 1 · AC-14 … headline, digest
