# Verify: support chat · spec 0009 · updated 2026-11-19 (13 steps confirmed by /check verify on 2026-11-19)
_Steps derived from spec 0009 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] On a site with none of the `books_tawk_*` keys set, sign in as a Books User and open the app menu (desktop sidebar and phone nav sheet) → no "Chat with support" item, and the network panel shows no request to `embed.tawk.to` on any screen → AC-1
- [ ] Set only two of the three keys (each pair in turn) → still no entry and `frappe.boot.books.support_chat` is `null` → AC-1
- [ ] With all three keys set, sign in as a Books User, a Books Manager and a Books Cashier with real emails → each sees "Chat with support" in the Help group, on desktop and on a phone → AC-2
- [x] Sign in as Administrator, and as a Books User whose email is `Someone@Example.com` → no entry, and the boot `support_chat` is `null` → AC-2
- [x] Load several screens without picking the entry → no request to `embed.tawk.to` → AC-3
- [ ] Pick "Chat with support" → one `embed.tawk.to/{property}/{widget}` script loads, the chat window opens, and no floating bubble shows; minimize and close it → the bubble stays hidden; pick again → the window reopens with no second script request → AC-3
- [x] View the page source and the boot JSON → the Secure Mode API key appears nowhere; `visitor.hash` is 64 lowercase hex characters → AC-4
- [ ] With Secure Mode on in tawk.to, change `Tawk_API.visitor.email` in the console before the first pick → tawk.to does not show the chat under the edited email → AC-4
- [ ] Start a chat from `/books/list/SalesInvoice?status=Paid` → the tawk.to dashboard visitor shows `company`, `site`, `phase`, `roles`, `app-version`, and `screen` = `/books/list/SalesInvoice` (no query string) → AC-5
- [x] Lock the site (`set_hosted_phase` `locked`) → the app menu still has the entry, the red banner shows "Chat with support", and a chat opened from it carries `phase: locked` → AC-6
- [x] Open `/books/subscription` → the "Chat with support" button opens the chat → AC-7
- [ ] Block `embed.tawk.to` (ad blocker or a devtools request block) and pick the entry → an orange toast "Chat could not load. Write to {support email}." stays until closed; the rest of /books keeps working; picking again retries → AC-8
- [ ] Unset `books_support_email` and repeat → the toast reads "Chat could not load. Please try again later." → AC-8
- [ ] Throttle the line so tawk.to takes over 10 seconds → the toast shows at 10 seconds, and a load that finishes later does not open the window → AC-8
- [x] With a chat open, sign out from the app menu → `Tawk_API.logout` runs before the `/api/method/logout` request, and `books_support_chat_email` is gone from localStorage → AC-9
- [ ] Sign in as a different user on the same browser and open the chat → no trace of the previous user's conversation or identity → AC-9
- [x] Let a session expire without signing out, sign in as another user, open the chat → the previous visitor is logged out first and the new identity shows → AC-9
- [ ] At 390 px on the dashboard and the POS, before a pick, after minimizing, and while the script is still loading on a throttled line → no tawk.to element floats over any control → AC-10
- [ ] Switch the user's language and check the new strings ("Chat with support", "Questions about your subscription?", both toast messages) go through the translation template → AC-11

## Value sourcing
- [ ] Turn each `books_tawk_*` key on and off and check the on or off state follows; give a user a mixed case `@EXAMPLE.com` email with spaces around it → off
- [x] Change `books_tawk_property_id` and `books_tawk_widget_id` → the script URL uses the new values
- [x] `visitor.email` matches `User.email` exactly as stored (case kept)
- [ ] A user with no full name → `visitor.name` is the email
- [x] `visitor.hash` equals `hmac.new(api_key, email, sha256).hexdigest()` computed by hand for one user
- [ ] Rename the company in Books Accounting Settings, reload → `company` follows; before setup completes → `company` is left out
- [x] On the hosting bench → `site` is the site's host name
- [ ] Lock the site while /books is open (no reload) and pick the entry → `phase` is `locked` (live ref, not the cached boot); on a self hosted site → `unmanaged`
- [ ] A user with Books Cashier and Books Manager → `roles` is `Books Manager, Books Cashier`; a user with no Books role → no `roles` attribute, chat still works
- [x] `app-version` equals `frappe_books.__version__`
- [ ] `support_email` set and unset → shown in, or left out of, the failure toast
- [x] Pick from a route with a query string and hash → `screen` holds the path only
- [ ] A company name over 255 characters → the `company` attribute is cut to 255; `name` and `email` are never cut
- [ ] The failure toast is orange (warning) and stays until closed
- [ ] Sign out before ever opening the chat → no `Tawk_API.logout` call; sign out while the script is still loading and finishes within 2 seconds → logout is called

## Commands
- [ ] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_support_chat` → 11 tests pass → AC-1, AC-2, AC-4, AC-5
- [ ] `cd frontend && node --test tests/support-chat.test.mjs tests/app-menu.test.mjs` → all pass → AC-1, AC-2, AC-3, AC-5, AC-8, AC-9
- [ ] `cd frontend && BOOKS_FILTER_TEST_BENCH=<bench> BOOKS_FILTER_TEST_SITE=<site> yarn test:ui tests/ui/support-chat.spec.ts` → all pass → AC-1, AC-3, AC-6 to AC-10
- [ ] `cd frontend && yarn typecheck && yarn lint` and `uvx ruff@0.14.10 check frappe_books && uvx ruff@0.14.10 format --check frappe_books` → clean → all

## Acceptance-criteria coverage
- AC-1: UI steps 1 and 2, node and Playwright "off" tests · AC-2: UI steps 3 and 4, Python exclusion tests · AC-3: UI steps 5 and 6 · AC-4: UI steps 7 and 8, the Python hash vector · AC-5: UI step 9, value sourcing steps · AC-6: UI step 10 · AC-7: UI step 11 · AC-8: UI steps 12 to 14 · AC-9: UI steps 15 to 17 · AC-10: UI step 18 · AC-11: UI step 19
