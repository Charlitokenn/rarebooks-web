# Verify: self serve onboarding · spec 0014 · updated 2026-11-22
_Steps derived from spec 0014 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. This first set covers the thread (milestone 1) and the pool skip rules (build task 6)._

## UI / manual
- [ ] Signed out, open `/dashboard/start` → you land on Clerk sign in → AC-1
- [ ] Sign up with an email you haven't verified yet, open `/dashboard/start` → "Verify your email address first", no form → AC-1
- [ ] Verified, type `acme` slowly → one check about 400 ms after you stop, then "Available"; type `www` → the reserved reason → AC-2
- [ ] Type more than 30 names inside a minute → the field shows "Slow down", and the form still submits → AC-2
- [ ] Submit with Turnstile not solved (or a forged token through curl) → 403, and no call reaches the control site (its Error Log and the Books Signup list stay empty) → AC-3
- [ ] Four sign up attempts from one IP inside an hour (fresh Clerk users) → the fourth answers 429 before any control site call → AC-3
- [ ] Submit `acme` and "Acme Traders" → you go to `/dashboard`, which shows "Getting your site", then "Setting up your address", then "Ready" with `acme.rarebooks.cc` and a "Set your password" button → AC-3, AC-4
- [ ] Watch the network tab on `/dashboard`: a status call every 5 seconds for 2 minutes, then every 15, and none after Ready → AC-4
- [ ] Before Ready, open `/dashboard/site/open` → 302 back to `/dashboard` → AC-5
- [ ] At Ready, press "Set your password" → 302 with `Referrer-Policy: no-referrer` and `Cache-Control: no-store` to the site's update password page; the Worker log shows only the status code → AC-5
- [ ] After you set the password, press it again → you land on `https://acme.rarebooks.cc/login` → AC-5, AC-23
- [ ] The "Your RareBooks site is ready" email arrives once, and its button goes to `/dashboard/site/open`, never to the password link → AC-6
- [ ] Sign in on the Books site → the setup wizard opens with "Acme Traders" filled in and your browser's time zone → AC-24
- [ ] Sign up again with the same Gmail address written with dots or a `+books` suffix (another Clerk account) → "This email already has a RareBooks site. Contact support" with the support email → AC-3, AC-9

## Commands
- [ ] `cd rarebooks-site && npm test` → 4 passing (signing vectors, issued_at window, email key cases) → AC-6, AC-8, AC-9
- [ ] `cmp rarebooks-site/tests/onboarding/signing_vectors.json rarebooks_control/rarebooks_control/tests/signing_vectors.json` → no output → AC-8
- [ ] `cmp rarebooks-site/tests/onboarding/email_key_cases.json rarebooks_control/rarebooks_control/tests/email_key_cases.json` → no output → AC-9
- [ ] `bench --site <control site> run-tests --app rarebooks_control --module rarebooks_control.tests.test_onboarding` → 22 OK → AC-8 to AC-14, AC-20, AC-21
- [ ] `bench --site <books site> run-tests --app frappe_books --module frappe_books.tests.test_subscription_onboarding` → 8 OK → AC-22, AC-23
- [ ] POST to `rarebooks_control.onboarding.signup_status` with a wrong signature → signed 401, and the hour's signature failure counter rises → AC-8
- [ ] POST `owner_link` with a right `request_id` and another `clerk_user_id` → signed 404 with no detail → AC-14
- [ ] Replay `claim_site` on a claimed site with another email → signed 409, no second user → AC-22
- [ ] Make the marketing notify URL answer 503: the notice is retried every 5 minutes, stops after 24 hours, and you get one email → AC-13
- [ ] Notify the Worker twice with the same Ready notice → one email; make Resend fail → signed 503 and no `ready_emailed_at` → AC-6
- [ ] A Ready pool site 40 days after its build: no removal case, no push, `get_state` refuses with `config_pending` → AC-20

## Value sourcing
- [ ] Owner email and names come from Clerk: send a different `email` in the browser's sign up body → the Books Signup still holds the Clerk email → AC-1
- [ ] Blank Clerk first name → the Books user's first name is the email's local part; blank last name stays blank → AC-1
- [ ] Time zone: sign up from a browser set to `America/Lima` → System Settings on the Books site is `America/Lima`; send `Mars/Base` → UTC → AC-1, AC-22
- [ ] IP limit key: KV holds `signup:<CF-Connecting-IP>:<UTC hour>` → AC-3
- [ ] Turnstile: a token answered `success: false` by Siteverify is refused → AC-3
- [ ] `email_key`: `Asha.Mrema@googlemail.com` and `ashamrema+x@gmail.com` give the same key on both sides → AC-9
- [ ] Available or reason: a label held only by a Books Signup is "taken: a sign up holds it" → AC-21
- [ ] Address: shown only at Ready, as `https://<subdomain>.<books_site_domain>` → AC-4
- [ ] Step label: Queued and Claiming show "Getting your site", Preparing "Setting up your address" → AC-4
- [ ] Which site: with two Ready pool sites, the one with the older `pool_built_on` is claimed → AC-11
- [ ] Daily cap: `max_claims_per_day` 0 leaves a new request Queued → AC-10
- [ ] Trial day 1: on a pool site built weeks ago, the trial reads day 1 on the claim date in the claim's zone (try a claim just after midnight in that zone, which is still yesterday in UTC) → AC-22, AC-24
- [ ] Company prefill: the global default `books_signup_company` holds the trimmed company name → AC-22
- [ ] Password link: each `/dashboard/site/open` makes a new key, and the older link stops working → AC-23
- [ ] Ready email link target is `PUBLIC_SITE_URL` + `/dashboard/site/open` → AC-6
- [ ] Notice target is Books Onboarding Settings `marketing_notify_url`; an `http://` URL is refused at save → AC-13

## Acceptance criteria coverage
- AC-1 to AC-6: UI steps, the value sourcing steps and `npm test`
- AC-7: not built yet (build task 9)
- AC-8 to AC-14, AC-21: `test_onboarding` and the command steps
- AC-15 to AC-19: not built yet (build tasks 7 and 8; only the one email per failed sign up of AC-17 is in)
- AC-20: `TestPoolSkip` and the command step
- AC-22 to AC-24: `test_subscription_onboarding`, and the setup wizard UI step
