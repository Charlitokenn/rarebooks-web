# Verify: Product analytics with PostHog · spec 0027 · updated 2026-11-28
_Steps derived from spec 0027 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual

On a hosted test site with `books_control_url`, `books_posthog_key` and `books_posthog_salt` set, and the PostHog connector on project 372817:

- [x] Sign in as a Books User and open `/books` → `window.frappe.boot.books.analytics` holds `key, distinct_id, site_key, roles, country_code, language` and no salt or email → AC-1
- [ ] Same user, load twice → same `distinct_id`; same user on a second site → a different one; the id is not the SHA256 of the email → AC-2
- [x] Network tab: the `posthog-js` chunk loads only after the dashboard renders → AC-3
- [ ] In the console, `posthog.config` shows the AC-4 options exactly (`eu.i.posthog.com`, no autocapture, no recording, no surveys, no flags, `identified_only`, `localStorage`) → AC-4
- [x] Open a Customer, then a list, then change only a list filter → one `$pageview` each for the form and the list, with `route_template` `/edit/:schemaName/:name` and `/list/:schemaName/:pageTitle?`, none for the filter change → AC-5
- [x] Read those `$pageview` events through the connector → `$current_url` is `<origin>/books/edit/:schemaName/:name`, no `$title`, no referrer, and no property holds the customer's name → AC-6
- [x] Create, submit and cancel a Sales Invoice → exactly one `doc_created`, `doc_submitted`, `doc_cancelled`, each with only `schema_name=SalesInvoice`; saving Settings sends none → AC-7
- [ ] Complete a POS sale with two tenders → `pos_sale_completed` with `payment_method_count=2` plus `doc_submitted` → AC-7
- [ ] Import 3 rows with 1 bad one in the Import Wizard → `import_finished` with `row_count=3`, `failed_count=1` → AC-7
- [ ] Open a print view, then print → `print_opened` twice, `schema_name` only → AC-7
- [x] Throw a `TypeError` from the console, and cause a server error whose message names a customer → both reach PostHog as `$exception`, the server one with `exc_type` and status and no message; a missing mandatory field sends nothing → AC-9
- [x] As a Books Manager, turn off "Share usage analytics with RareBooks" in Settings, reload as another user → no PostHog chunk, no PostHog request → AC-10
- [x] Block `eu.i.posthog.com` in the browser, load and save a document → works as before, no toast, at most one `console.warn` → AC-11
- [x] Sign in as Administrator, and open a site without `books_control_url` → no PostHog chunk or request → AC-1
- [ ] On rarebooks.cc with `PUBLIC_POSTHOG_KEY` set, sign up → the Books Signup row has `posthog_distinct_id` equal to the cookie's id, and `site_ready` arrives under that id → AC-17
- [ ] Sign up with the `ph_*_posthog` cookie deleted → the sign up works, `site_requested` arrives as `signup:<name>` → AC-17
- [x] `/privacy` shows the "PostHog (EU cloud), inside RareBooks" line and keeps the marketing line → AC-18

## Commands

- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_analytics` → 8 pass → AC-1, AC-2, AC-10, AC-19
- [ ] `cd frontend && node --test tests/analytics.test.mjs` → 12 pass → AC-3 to AC-9, AC-11
- [ ] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_analytics` → 22 pass → AC-12 to AC-17, AC-19
- [ ] `cd rarebooks-site && node --test tests/onboarding/posthog-id.test.ts` → 3 pass → AC-17
- [ ] Every suite with no PostHog keys set → no new failures → AC-19

## Value sourcing (one step per source)

- [ ] `key`: change `books_posthog_key` in bench config, reload → the boot carries the new key → AC-1
- [ ] `distinct_id`: change `books_posthog_salt` on a test bench → every id changes (so never change it in production) → AC-2
- [ ] `site_key`: add a custom domain to a test site → `site_key` stays `frappe.local.site`, not the custom domain → AC-1
- [ ] `roles`: a user with Books Manager and Books User → `["Books Manager", "Books User"]`, sorted; System Manager only → no block → AC-1
- [ ] `country_code`: an Indian company → `in`; a country without a regional schema → `-` → AC-1
- [ ] `language`: a user set to Swahili → `sw` in the person properties → AC-1
- [x] hosted check: remove `books_control_url` → `None` → AC-1
- [x] opt out: `share_usage_analytics` 0 → `None` from the next page load → AC-10
- [x] `app_version`: every event carries `frappe_books.__version__` → AC-4
- [x] `route_name`, `route_template`, `schema_name`: a route with no name (`/`) sends no `route_name` and `route_template=/` → AC-5
- [ ] doc events `schema_name`: a child table row saved alone sends nothing → AC-7
- [x] `doc_created` "is new": double click Save on a new doc → one event → AC-7
- [ ] `payment_method_count`: a sale on credit with no tender → `0` → AC-7
- [ ] `row_count`, `failed_count`: an import where every row fails → `failed_count` equals `row_count` → AC-7
- [ ] server error `exc_type`, status: a 403 `PermissionError` → `Error (PermissionError, 403)` or the mapped type, no message → AC-9
- [x] control `site_key` and `$groups.site`: equal to the Books Hosted Site `site` → AC-16
- [x] control `distinct_id`: a site whose signup has no stored id → `site:<site>` → AC-16
- [ ] `provider`, `plan`, `billing_period`: a PayPal monthly checkout → `PayPal`, its plan name, `Monthly` → AC-14
- [ ] `amount`, `currency`: TZS `120000.4` → `"120000"`; USD `9.995` → `"10.00"` → AC-14
- [ ] `is_renewal`: first payment false, second true → AC-14
- [ ] `auto_renew_ended`, `paypal_status`: cancel the PayPal subscription → one event with `cancelled` → AC-14
- [ ] `reason_kind`: each of `timeout`, `owner_step`, `domain`, never the failure text → AC-14
- [ ] `uuid`: replay the same webhook → the same uuid, one event in PostHog → AC-13
- [x] `$group_set`: after a payment, `phase=paid` and the new `paid_until` → AC-16
- [ ] daily "yesterday", "3 days ago": sites in `Africa/Dar_es_Salaam` and `America/Los_Angeles` around midnight UTC each get their own day → AC-15
- [ ] funnel `posthog_distinct_id`: a cookie from another PostHog project → no field sent → AC-17
- [ ] control send key: remove `posthog_project_key` → nothing queued → AC-19

## Acceptance-criteria coverage

- AC-1 manual 1, 14, value sourcing 1, 3 to 8 · AC-2 manual 2, value sourcing 2 · AC-3 manual 3 · AC-4 manual 4, value sourcing 9 · AC-5 manual 5, value sourcing 10 · AC-6 manual 6 · AC-7 manual 7 to 10, value sourcing 11 to 14 · AC-8 node tests · AC-9 manual 11, value sourcing 15 · AC-10 manual 12 · AC-11 manual 13 · AC-12 control tests · AC-13 value sourcing 23 · AC-14 value sourcing 18 to 22 · AC-15 value sourcing 25 · AC-16 value sourcing 16, 17, 24 · AC-17 manual 15, 16, value sourcing 26 · AC-18 manual 17 · AC-19 commands 5, value sourcing 27
