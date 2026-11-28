# Verify: push notifications · spec 0026 · updated 2026-11-28
_Steps derived from spec 0026 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

Set up first: a Firebase test project, its three keys in the test site's config (`books_fcm_service_account`, `books_fcm_web_config`, `books_fcm_vapid_key`), a Books Manager with a real email, a second Manager, a Books Cashier, and a phone (Android Chrome, plus an iPhone with /books on the Home Screen, iOS 16.4 or later).

## UI / manual
- [ ] Remove one of the three keys, reload /books as a Manager → `frappe.boot.books.push` is `null`, no notifications entry in the app menu, submitting a payment makes no request to Google → AC-1
- [ ] Put all three keys back, sign in as `Administrator` and as a user at `@example.com` → no entry → AC-2
- [ ] As the Manager on desktop Chrome, open the app menu → "Turn on notifications" sits beside "Chat with support"; no browser prompt shows before the click → AC-2
- [x] Pick it, allow → toast "Notifications are on for this device."; the entry now reads "Turn off notifications"; one Books Push Device row with this user, a label like "Chrome on Windows", and `last_seen` now → AC-2, AC-3
- [x] On a fresh browser profile pick it and block the prompt → orange toast that stays: "Notifications are blocked. Allow them for this site in your browser settings." → AC-2
- [x] On an iPhone in Safari (not from the Home Screen) pick the entry → toast "Add RareBooks to your Home Screen first, then turn on notifications from there." → AC-2
- [ ] Same phone, /books opened from the Home Screen → turning on works and a push arrives → AC-2
- [ ] Reload /books twice within an hour → `last_seen` does not change; set it back two hours in the database and reload → it moves to now → AC-3
- [ ] Sign in as the second Manager on the same browser and turn on → the same row now belongs to the second Manager (one row, not two) → AC-3
- [x] Register 11 devices for one user (bench console) → only 10 rows remain, the oldest `last_seen` gone → AC-3
- [x] As a Books User, list Books Push Device through `/api/resource` → only their own rows; deleting another user's row is refused → AC-3
- [x] "Turn off notifications" → toast "Notifications are off for this device.", the row is gone, the browser has no push subscription (DevTools, Application, Service workers, Push) → AC-4
- [x] Turn on again, then Log out → `unregister_device` runs before `logout`; the row is gone → AC-4
- [ ] As the Cashier submit a Receive payment (not POS) → both Managers' devices get "Payment received", body "{party} paid {amount}" in the company currency; tapping opens that payment → AC-5
- [ ] As Manager A submit a Receive payment → Manager B gets it, Manager A does not → AC-5
- [x] Ring a POS sale paid by cash and card → one push with the total of both tendered rows; tapping opens the invoice → AC-5
- [ ] Pay a submitted POS invoice later from the POS (`pay_pos_invoice`) → one push for that call's total → AC-5
- [ ] Cancel a payment, amend and submit it, and submit a Pay payment → no push for any of them → AC-5
- [x] On a tracked item set Reorder level 10 with 12 in stock (the field shows only with Track Inventory on) → no push; ship 3 → "Low stock: {item}", body "9 {unit} left (reorder level 10)"; ship 1 more → no second push → AC-6
- [x] Receive 7 (total 15), then ship 7 (total 8) → a second low stock push → AC-6
- [x] Set the level above current stock and save the item → a push on that save; set it to 0 → the flag clears and nothing is sent → AC-6
- [x] Two cashiers ship the same item at the same moment across the level → one push → AC-6
- [ ] Move stock between locations only → no push (total unchanged) → AC-6
- [x] Put a hosted site in `trial`, run `notify_subscription_phase`, then move it to `prompt` and run again → one "Your books turn read only soon" naming the lock date (`lock_starts_on`, day 26, never a past date) in the site's date format; with a PayPal subscription set to start after the trial (`subscription_starts_on`), no push and the phase is still stored → AC-7
- [x] A first run that only sees `prompt` late (day 25) → the push still names the lock day (`lock_starts_on`), never the past trial end → AC-7
- [x] A PayPal subscription set to start after the trial (`set_hosted_phase('waiting')`, then `'overdue'`) → no `prompt` push on day 22 or day 23, phase stored as `prompt`; moving to `locked` still pushes → AC-7
- [x] Repeat for `renew_soon` ("Renewal due"), `grace` ("Payment overdue") and `locked` ("RareBooks is now read only") → one push each, tapping opens /books/subscription → AC-7
- [x] Move `locked` to `lapsed` → no new push → AC-7
- [ ] Self hosted (`unmanaged`) or exempt site → no subscription push ever; a first run stores the phase only → AC-7
- [x] Settings → Notifications tab shows for a Manager with three switches on; it is absent for a Books User and when push is off; switch Payment received off → payments push nothing; switch it back on → nothing missed is resent → AC-8
- [x] Set Manager B's language to French (with French translations present) → B's push text is French, A's is the site language → AC-9
- [ ] Revoke the service account key in Google, submit a payment → the payment stays submitted, one Error Log entry with only HTTP status and error code (no token, no key) → AC-10, AC-12
- [x] Uninstall the browser that holds a registered token, submit a payment → its row is deleted after the send (FCM `UNREGISTERED`) → AC-10
- [x] Use a service account from another Firebase project → `SENDER_ID_MISMATCH` logged, rows kept → AC-10
- [ ] With /books open and visible, a push arrives → one system notification, no in app duplicate → AC-11
- [ ] Tap a push with /books open in another tab → that tab focuses and moves to the link; with no /books tab open → a new window opens at the link → AC-11
- [x] View the page source, the boot and the Error Log → the service account JSON (its `private_key`) appears nowhere → AC-12
- [x] On a locked site pick "Turn on notifications" → the usual lock notice, no row, no browser subscription; "Turn off" and sign out still remove the browser subscription → AC-13
- [x] Set a row's `last_seen` to 91 days ago and run `delete_stale_devices` → gone; 89 days → kept → AC-14

## Value sourcing
- [x] `web_config` and `vapid_key` in the boot match the site config values → boot row
- [ ] Menu "on" needs both granted permission and `books_push_token:<user>` in localStorage: clear the key with permission granted → the entry reads "Turn on" → menu row
- [ ] An iPad (Mac user agent with touch) outside the Home Screen gets the Home Screen toast → iOS row
- [ ] The token sent to `register_device` is the one `getToken` returns with the `/books/sw.js` registration (no request for `firebase-messaging-sw.js` in the network panel) → token row
- [ ] Device label on Safari iOS, Chrome Android, Edge Windows, Firefox Linux reads "{browser} on {OS}" → label row
- [ ] `token_hash` is the SHA256 of the token; `user` is the session user, never a value from the request → register row
- [x] Payment push amount uses the company currency format (try a non default currency site, for example KES) → payment currency row
- [ ] POS push amount is the sum of the counter payments, not the invoice grand total, when change is given (tender 200 on a 180 sale → 180) → POS row
- [ ] Low stock total sums every location and date, and a negative total still alerts → total stock row
- [ ] Subscription dates follow the site time zone and the Books date format (change both and check the text) → subscription dates row
- [ ] Recipients: a disabled Manager gets nothing; a System Manager without a Books role still gets pushes → recipients row
- [x] Language falls back to System Settings `language` when the user has none → language row
- [ ] Tags: two payment pushes for the same payment replace each other on the device; `locked` and `lapsed` share `subscription:read-only` → tag row
- [x] The access token is minted once per site per hour (watch for a single OAuth request across several sends) → access token row

## Commands
- [x] `bench --site <site> run-tests --app frappe_books --module frappe_books.tests.test_push_notifications` → 36 tests pass → AC-1, AC-3 to AC-10, AC-12 to AC-14
- [x] `cd frontend && node --test tests/push-notifications.test.mjs` → 9 tests pass → AC-2, AC-3, AC-4, AC-13
- [x] `cd frontend && yarn build && yarn test:ui tests/ui/push-notifications.spec.ts` (with `BOOKS_FILTER_TEST_BENCH` and `BOOKS_FILTER_TEST_SITE`) → 9 tests pass → AC-1, AC-2, AC-4, AC-8, AC-11, AC-12, AC-13

## Acceptance-criteria coverage
- AC-1: Python off tests, Playwright "no entry", UI step 1
- AC-2: node and Playwright turn on, blocked and iPhone tests, UI steps 2 to 7
- AC-3: Python register tests, node start up test, UI steps 4, 8 to 11
- AC-4: node and Playwright turn off and sign out tests, UI steps 12 and 13
- AC-5: Python payment and POS tests, UI steps 14 to 18
- AC-6: Python low stock tests, UI steps 19 to 23 (true concurrency only by hand)
- AC-7: Python subscription tests, UI steps 24 to 27
- AC-8: Python settings tests, Playwright Notifications tab, UI step 28
- AC-9: Python language test, UI step 29
- AC-10: Python send job and FCM tests, UI steps 30 to 32
- AC-11: Playwright worker test (show and link filter), UI steps 33 and 34 (the click by hand only)
- AC-12: Python boot and log tests, Playwright page check, UI step 35
- AC-13: Python and node locked tests, Playwright lock notice, UI step 36
- AC-14: Python stale test, UI step 37
