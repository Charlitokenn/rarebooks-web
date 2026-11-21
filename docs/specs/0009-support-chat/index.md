# 0009. Support chat with a signed tawk.to visitor

**Date**: 2026-11-19
**Status**: In Progress

Decision history (context, options and reasoning) lives in [rationale.md](rationale.md). Verify steps live in [verify.md](verify.md).

## Summary

Every signed in /books user gets a "Chat with support" entry that opens a tawk.to chat, including on a locked site. The server signs the user's name and email with the tawk.to API key (Secure Mode), so nobody can chat as someone else, and it sends the company, site and subscription phase too, so you never have to ask who is writing. Nothing loads from tawk.to until the user asks for help, and the keys live in the bench config, where only the operator can change them.

## Requirements

**User stories**:
- As a Books User, Manager or Cashier on a hosted site, I want to open a support chat from any screen so I can get help without leaving /books.
- As a user on a locked site, I want to reach support from the lock notice so I can sort out the subscription.
- As the support agent, I want each chat to show who is writing, their company, site, role and subscription phase so I can help without asking.
- As the operator, I want the tawk.to keys in one place only I control, so no customer can change where chats go.

**Acceptance criteria**:
- **AC-1**: The chat is on only when `books_tawk_property_id`, `books_tawk_widget_id` and `books_tawk_api_key` are all set in the site's config (normally `common_site_config.json`). Otherwise the boot carries `support_chat: null`, no entry shows, and no tawk.to request is ever made.
- **AC-2**: Every signed in /books user with a real email (Books User, Manager and Cashier alike) sees "Chat with support" in the Help group of the app menu, so it shows in the desktop sidebar menu and the phone navigation menu. Administrator, Guest, and a user whose email is empty or ends in `@example.com` get `support_chat: null` and no entry.
- **AC-3**: No request goes to tawk.to before the user picks a chat entry. The first pick loads the tawk.to script and opens the chat window. The floating tawk.to bubble never shows: it is hidden on load, and hidden again whenever the chat is minimized or closed. A later pick opens the window again without loading the script twice.
- **AC-4**: The tawk.to visitor's name and email come from the server for the signed in user, with `hash` = lowercase hex HMAC SHA256 of that exact email string, keyed with `books_tawk_api_key` (tawk.to Secure Mode). The API key never appears in any response, boot or log. With Secure Mode on in the tawk.to dashboard, a visitor whose email is edited in the browser is not shown under that email.
- **AC-5**: Each chat carries these tawk.to attributes, visible on the visitor in the tawk.to dashboard: `company` (Books Accounting Settings `company_name`), `site` (the site name), `phase` (the subscription phase at the moment the chat was opened), `roles` (the user's Books roles), `app-version` (the frappe_books version), and `screen` (the /books route path at the moment the chat was opened, with no query string or hash). An empty value is left out, and every custom attribute value is cut to 255 characters. Every `setAttributes` call that sends these also carries the signed `name`, `email` and `hash`: with Secure Mode on, tawk.to answers `UNAUTHORIZED_API_CALL` to one without them and drops the attributes (found on a hosted site, changed 2026-11-21).
- **AC-6**: On a locked site the chat works: the entry is in the app menu, the locked Subscription banner shows a "Chat with support" button, and the chat opens and carries `phase: locked`.
- **AC-7**: The Subscription page shows a "Chat with support" button that opens the chat.
- **AC-8**: If the tawk.to script fails to load, or its `onLoad` has not fired 10 seconds after the pick, the user sees an orange toast that stays until closed: "Chat could not load. Write to {0}." with `books_support_email`, or "Chat could not load. Please try again later." when that is not set. The rest of /books keeps working, and picking the entry again tries again. An `onLoad` that arrives after the timeout does nothing.
- **AC-9**: Signing out from the app menu ends the tawk.to session first: if the script loaded, `Tawk_API.logout()` is called and awaited for up to 2 seconds, `books_support_chat_email` is cleared, then the Frappe logout runs. The next user on that browser never sees the previous user's chat or identity, including after a session that expired without a sign out.
- **AC-10**: At phone width (390 px) no tawk.to element floats over /books controls on any screen, the POS included, while the chat is closed.
- **AC-11**: Every new user facing string is translated at runtime (`t` tags in TS and Vue, `_()` in Python).

## Decision

**Chosen option**: Option 2: signed visitor in the boot, own launcher, loaded on first open.

/books opens a tawk.to chat from its own entries, with a Secure Mode visitor and support attributes computed by the server into the session boot, keys in the bench config, and the script loaded only when the user asks.

**Implementation skills**: `frappe-app-dev` (`frappe/skills`, `.agents/skills/frappe-app-dev/`) · `code-style` (`frappe/skills`, `.agents/skills/code-style/`) · `vue-best-practices` (`vuejs-ai/skills`, `.agents/skills/vue-best-practices/`) · `playwright-best-practices` (`currents-dev/playwright-best-practices-skill`, `.agents/skills/playwright-best-practices/`)

## Feature design

**Data model sketch**: no new DocType and no migration. The feature reads existing data only:
- `User`: `name`, `email`, `full_name` (the signed in user)
- `Books Accounting Settings` (single): `company_name`
- The subscription clock status (`current_clock().status()["phase"]`, spec 0005)
- Bench or site config keys (see *Configuration required*)

Client side state: `localStorage` key `books_support_chat_email` holds the email the tawk.to session in this browser was last opened for (wrapped in try/catch, see invariants).

**State transitions** (the client loader in `src/utils/supportChat.ts`):
`idle` (no script) → pick → `loading` (script tag added, 10 second timer, generation number incremented) → `onLoad` → `ready` (window open) · `loading` → script error or timeout → `failed` (toast; the script tag is removed so the next pick goes back to `loading`) · `ready` → minimize or close → `ready` (bubble hidden) · any → sign out → logout attempt → page leaves.
A pick while `loading` waits on the same pending load and does not add a second tag. An `onLoad` or error whose generation is not the current one is ignored, so a late `onLoad` after a timeout neither opens the window nor clears the toast.

**API surface**:
| Surface | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `extend_bootinfo` → `bootinfo.books.support_chat` (`frappe_books/support_chat.py`, `boot_block()`) | page boot (GET `/books`) | session user, `frappe.conf` | `null`, or `{property_id, widget_id, visitor: {name, email, hash}, attributes: {company?, site, roles?, "app-version"}, support_email?}` | signed in user with /books access (existing `get_context` check) | none: any failure building the block logs a warning through `frappe.logger("frappe_books.support_chat")` (never an Error Log, which a locked site's read only transaction can't write) and returns `null`, so it never breaks the boot |
| `openSupportChat()` (`src/utils/supportChat.ts`) | client function | none (reads `window.frappe.boot.books.support_chat`, stored at startup in `WebApp.vue` `initializeBooks` beside `setSubscriptionStatus`; the live `subscriptionStatus` ref; the current route) | opens the window, or the AC-8 toast | entry shown only when `support_chat` is set (`hasSupportChat()` from the same module) | load error, 10 s timeout |
| `endSupportChat()` (`src/utils/supportChat.ts`) | client function, awaited by `logOut()` in `src/utils/appMenu.ts` | none | resolves after `Tawk_API.logout` callback or 2 s | n/a | logout error: logged to console, sign out continues |
| tawk.to JS API (external) | browser | `Tawk_API.visitor`, `setAttributes`, `hideWidget`, `showWidget`, `maximize`, `onLoad`, `onChatMinimized`, `onChatHidden`, `logout` | | Secure Mode | `setAttributes` callback errors: logged to console only |

Script URL: `https://embed.tawk.to/{property_id}/{widget_id}`, added as an `async` script with `charset="UTF-8"` and `crossorigin="*"` (the tawk.to embed's own attributes).

**Value sourcing**:
| Action | Value produced / displayed | Source |
|---|---|---|
| boot block | on or off | all three `books_tawk_*` keys in `frappe.conf` truthy, and the user passes the real email rule: not Administrator or Guest, and `User.email` (read with `frappe.db.get_value("User", frappe.session.user, ["email", "full_name"])`) tested as `.strip().lower()` is neither empty nor ending in `@example.com`. A user with /books access but no Books role still gets the chat |
| boot block | `property_id`, `widget_id` | `frappe.conf.books_tawk_property_id`, `frappe.conf.books_tawk_widget_id` |
| boot block | `visitor.email` | `User.email`, sent exactly as stored (the strip and lower case are for the test only, so the hash matches) |
| boot block | `visitor.name` | `User.full_name`, else the email |
| boot block | `visitor.hash` | `hmac.new(api_key.encode(), email.encode(), hashlib.sha256).hexdigest()`, `api_key` = `frappe.conf.books_tawk_api_key` |
| boot block | `attributes.company` | `frappe.db.get_single_value("Books Accounting Settings", "company_name")`; left out when empty (before setup) |
| boot block | `attributes.site` | `frappe.local.site` (on the hosting bench the site name is its host) |
| open chat | `phase` | `phase` of the live `subscriptionStatus` ref in `src/utils/refs.ts` (seeded from the boot, refreshed by `fetchLockStatus`), read at the moment of the pick, because Frappe caches the boot per user and a boot value can be stale after a payment or lock (`unmanaged` on a non hosted site) |
| boot block | `attributes.roles` | the set from `frappe.get_roles()` filtered to Books Manager, Books User, Books Cashier, emitted in that fixed order, joined with `", "`; left out when none |
| boot block | `attributes["app-version"]` | `frappe_books.__version__` (in `frappe_books/__init__.py`) |
| boot block | `support_email` | `frappe.conf.books_support_email`; left out when not set |
| open chat | `attributes.screen` | `"/books" + router.currentRoute.value.path` at the moment of the pick (path only: no query string or hash, which can hold filters or document names) |
| open chat | custom attribute values | `[:255]` (tawk.to's limit) on the server for `company`, `site`, `roles`, `app-version`; on the client for `phase` and `screen`. `name` and `email` are not cut |
| failed load | toast | `showToast({ id: 'support-chat-failed', type: 'warning', duration: 'until_closed', message })` from `src/utils/interactive.ts` (warning is the orange toast, as in `serverMessages.ts`); `message` is `` t`Chat could not load. Write to ${support_email}.` `` or `` t`Chat could not load. Please try again later.` `` (AC-8) |
| sign out | whether to call logout | loader state is `ready`, or `loading` that reaches `ready` within the 2 s wait |

**Key invariants**:
- `books_tawk_api_key` is read only in `frappe_books/support_chat.py` and never returned, logged or put in an exception message.
- The hash is always computed from the same email string that is sent as `visitor.email`.
- The tawk.to script is added at most once per page, and only after a user pick.
- The tawk.to bubble is never visible: `hideWidget()` in `onLoad`, `onChatMinimized` and `onChatHidden`; `showWidget()` then `maximize()` on each pick.
- Identity (`name`, `email`, `hash`) is set only in `Tawk_API.visitor`, before the script tag is added. `setAttributes` carries only the custom attributes: all of them in `onLoad`, then `{phase, screen}` on later picks. The one exception is the expired session guard below.
- Expired session guard (AC-9): on `onLoad`, if `books_support_chat_email` in `localStorage` holds a different email, call `Tawk_API.logout()` and wait for its callback (2 s at most), then put identity back with `setAttributes({name, email, hash})` (the Secure Mode form tawk.to documents) before the custom attributes and `maximize`. Then store the current email. A clean sign out removes the key. A `localStorage` read or write that throws is skipped, never fatal. Accepted gap: if the key is missing (cleared site data) while tawk.to's own cookie still holds another user's chat, the guard can't tell.
- The boot block never raises: a failure returns `null` and logs a warning through `frappe.logger`, never an Error Log, so a tawk.to config mistake can't break /books or spam the Error Log on every page load.
- No server writes: the feature runs the same on a locked site (read only transaction) as on an open one.

**Security model**:
- Who: any signed in user who passes the existing /books app permission check (Books User, Manager, Cashier). No extra role check: the boot only describes the caller themselves. Administrator, Guest and placeholder emails are excluded (AC-2).
- What leaves the site: the caller's own name, email, Books roles, company name, site name, subscription phase, app version, and the current route, and only after they pick the entry. No other user's data, no ledger data.
- Secrets: the API key stays in the bench config, which only the operator edits (`bench set-config -g`). Site users can't read `frappe.conf` over HTTP and can't change the keys, so chats can't be redirected to another tawk.to account.
- Spoofing: with Secure Mode on in the tawk.to dashboard, an edited email without a matching hash is rejected by tawk.to. Turning Secure Mode on is a rollout step, not code.
- Privacy: users are told through the privacy policy that tawk.to handles support chats (engineer's pick; no in app note). See Follow-up.
- No compliance scope beyond normal personal data (name and email).

**Configuration required** (all in `common_site_config.json` on the hosting bench, `bench set-config -g <key> <value>`; a site's own `site_config.json` can override):
- `books_tawk_property_id`: the tawk.to property ID (first part of the embed URL)
- `books_tawk_widget_id`: the tawk.to widget ID (second part); its language is set in the tawk.to dashboard
- `books_tawk_api_key`: the property's Secure Mode API key (tawk.to dashboard, property settings), a secret
- `books_support_email` (optional): the address the AC-8 fallback shows

Prerequisites outside the code: a tawk.to account and property, Secure Mode turned on for it, and the widget language set in its dashboard.

**Critical test scenarios**:
- Happy path: a Books Cashier on a hosted site with the keys set picks "Chat with support"; the stub tawk.to script loads once, `visitor` and `setAttributes` get the boot values plus `screen`, `maximize` runs and the bubble stays hidden, verifies **AC-2**, **AC-3**, **AC-5**
- Signing: `boot_block()` for a test user returns the hash matching a fixed vector (known key and email), and the serialized boot contains no API key, verifies **AC-4**
- Off: any one of the three keys missing gives `support_chat: null`, no menu entry, and no request to `embed.tawk.to` (Playwright request listener), verifies **AC-1**
- Exclusions: Administrator and a user with an `@example.com` email get `null`, verifies **AC-2**
- Locked: with `set_hosted_phase` locked, the banner button opens the chat and `phase` is `locked`, verifies **AC-6**
- Subscription page button opens the chat, verifies **AC-7**
- Blocked: `page.route('**/embed.tawk.to/**', r => r.abort())` shows the toast with the support email; a stub that never calls `onLoad` shows it after 10 s (fake clock); the dashboard still loads and saves, verifies **AC-8**
- Sign out: with the chat ready, sign out calls `Tawk_API.logout` before the `logout` request; with a stub that never calls back, sign out still completes after 2 s, verifies **AC-9**
- Expired session: `books_support_chat_email` set to another email makes `onLoad` call `logout` before `setAttributes`, verifies **AC-9**
- Phone: at 390 px on the POS and dashboard, no element from tawk.to is visible before a pick or after minimize, verifies **AC-10**
- Strings appear in the extracted translation template, verifies **AC-11**

## Build plan

Tracer Bullet: the first task is a thin chat that works end to end (server boot, menu entry, signed visitor, real tawk.to on a dev bench); later tasks thicken it.

1. Server boot block: `frappe_books/support_chat.py` with `boot_block()` (config gate, real email rule, name, email, hash, `site`, `app-version`, `support_email`, never raises), wired into `extend_bootinfo` in `frappe_books/boot.py` as `books.support_chat`; its type in `src/web/api.ts`'s boot type; Python tests in `frappe_books/tests/test_support_chat.py` (off when a key is missing, excluded users including `Admin@Example.com`, fixed hash vector, no API key in the boot). Confirm on v16 that the `extend_bootinfo` output is cached per user (the reason `phase` comes from the live ref), satisfies **AC-1**, **AC-2**, **AC-4**
2. Client loader `src/utils/supportChat.ts`: `openSupportChat()` with the state machine above (script once, `Tawk_API.visitor`, `onLoad` hide then `setAttributes` and `maximize`, hide on minimize or hidden), the "Chat with support" item (icon `lucide-message-circle`) in the Help group of `getAppMenuItems` in `src/utils/appMenu.ts` shown only when `support_chat` is set; node tests with a stubbed `Tawk_API`. Check by hand on a dev bench with real keys that the chat opens and the visitor shows signed, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-10**
3. Support attributes: add `company` and `roles` (fixed order, tested) to the boot block and the 255 character cut; send `phase` from the live `subscriptionStatus` ref and `screen` (path only) on each pick; extend the Python and node tests, satisfies **AC-5**
4. Entry points: a "Chat with support" button on the locked state of `src/components/SubscriptionBanner.vue` and on `src/pages/Subscription/Subscription.vue`, both calling `openSupportChat()` and shown only when `support_chat` is set, satisfies **AC-6**, **AC-7**
5. Failure handling: script `onerror` and the 10 second timer move to `failed`, remove the tag, and show the AC-8 toast with `showToast`; the generation counter ignores a late `onLoad`; a pick while loading reuses the pending load; translated strings, satisfies **AC-3**, **AC-8**, **AC-11**
6. Session end: `endSupportChat()` awaited in `logOut()` (2 second cap, then clears `books_support_chat_email`), and the expired session guard in `onLoad`, satisfies **AC-9**
7. Playwright tests in `frontend/tests/ui/` with a stub tawk.to script served through `page.route` (no real tawk.to in CI): happy path, off, locked, Subscription page, blocked, timeout, sign out, phone width, satisfies **AC-1**, **AC-3**, **AC-6**, **AC-7**, **AC-8**, **AC-9**, **AC-10**
8. Rollout notes in `frappe_books/AGENTS.md` (config keys, Secure Mode on, where the API key lives, and that `bench get-config` prints it) and a manual check on a real hosted site with the real widget: a chat shows name, email and all attributes in the tawk.to dashboard, an email edited in the console is not accepted, and at 390 px no tawk.to bubble shows before a pick, after minimize, or while the script is still loading on a throttled line (the CI stub can't prove the real widget's hiding), satisfies **AC-4**, **AC-5**, **AC-10**

## Consequences

**Positive**:
- Support sees who is writing, from which company, site and phase, without asking.
- Users on a locked site can still reach help in one click.
- No third party script or data transfer until a user asks for help; a blocked tawk.to costs nothing elsewhere.

**Negative / tradeoffs**:
- No proactive chat: agents can't see users browsing or start a conversation.
- The first open waits for the tawk.to script to download (a second or two on a slow line).
- The boot grows by a small block on every page load, and the HMAC runs even for users who never chat.
- The design depends on tawk.to's JavaScript API (`hideWidget`, `onChatMinimized`, `logout`) staying stable; a change there breaks the hidden bubble or the shared till guard, and only the manual rollout check against the real service would catch it.
- One tawk.to property for the whole bench: a site can't have its own support team or language without a per site override.
- Users learn about tawk.to only from the privacy policy, not in the app.

**Neutral**:
- The widget's language is set in the tawk.to dashboard, not by the user's /books language.
- Turning on Secure Mode in tawk.to is a manual rollout step; until it is on, the hash is ignored and identities are unverified.
- The service worker only caches same origin `/assets`, so the tawk.to script is never cached by /books; no CSP exists to update.

## Follow-up

- [ ] Update the privacy policy (or terms) to name tawk.to as the processor for support chats and list what is shared (name, email, company, site, role, subscription phase, app version, current screen), before turning on the keys in production
- [ ] Turn on Secure Mode for the tawk.to property and set the widget language in its dashboard before the rollout check
- [ ] If the team grows or wants proactive chat, revisit loading the script at app start
- [ ] If users with other languages arrive, consider a widget per language (a map keyed by the user's Frappe language)
- [ ] Record in root `AGENTS.md` `## Agent skills`: `Declined:` the community tawk.to skills (`membranedev/application-skills@tawkto`, `fcakyon/claude-codex-settings@tawk-support`, `smithery.ai@tawkto`) and the third party hosted tawk.to MCP servers (Zapier, viaSocket, Pipedream, Boost.space), declined 2026-11-19
