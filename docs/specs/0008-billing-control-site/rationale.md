# 0008. Billing control site: rationale

## Context

Spec 0005 built the customer site side of the paywall: a 30 day clock, a read only lock, and a signed contract (`get_state`, `create_checkout`, the `receive_state` push) with a central control site that it assumed but did not build. Spec 0007 then put the removal records (Books Hosting Bench, Books Removal Case, the runner endpoints) on that same control site. Until it exists, no hosted site can take a real payment, and the only way to lift a lock is `bench execute apply_state`.

The forces:
- **Two providers, two shapes.** ClickPesa (mobile money, Tanzania) is a one off hosted checkout link with no sandbox, a fixed return URL set in its dashboard, and a body checksum signed with a separate key. PayPal Subscriptions renews by itself, has a sandbox, sends events that can arrive late, twice or out of order, and verifies them through an API call.
- **Money and personal data.** A wrong unlock gives free access, and a missed payment locks out a payer. Webhooks hold payer names, emails and phones. Card data stays with the providers.
- **The site is the clock.** Spec 0005 makes the customer site the only judge of its phase and dates. The control site must compute `paid_until` (including "the paid period starts at trial end when someone pays early") without becoming a second clock.
- **One operator.** You run the hosting bench yourself. Whatever runs here has to be cheap to operate, and must say clearly when it needs you.
- **Existing pieces.** `rarebooks-site` (Astro on Cloudflare Workers, D1) already holds working ClickPesa credentials, a PayPal business account, and Resend for email. Spec 0007's removal side already assumes Frappe features (Email Queue, track changes, `frappe.only_for`).

## Options considered

### Option 1: Frappe app on its own bench, verify then fetch, full state push

`rarebooks_control` as a Frappe 16 app. Every webhook is verified, then the provider is asked for the current state, and one locked apply step writes it and pushes the full state to the site.

**Pros**:
- Same stack, conventions and test tools as this repo, and spec 0007's removal side fits as is.
- Fetching provider state makes event order and replays harmless.

**Cons**:
- A second Frappe bench to run.
- Extra provider API calls per event.

### Option 2: Billing inside rarebooks-site (Cloudflare Workers and D1)

Extend the marketing site, which already talks to ClickPesa and Resend.

**Pros**:
- No server to run, and credentials and the email setup already exist.

**Cons**:
- Spec 0007's removal side (Email Queue, track changes, roles, desk actions) would need rebuilding on another stack, and the signing code would exist in TypeScript and Python.
- No desk for support edits. D1 and Worker limits shape the background retries.

### Option 3: A merchant of record billing platform

A hosted billing service that handles subscriptions, tax and receipts.

**Pros**:
- Fiscal handling, dunning (chasing failed payments) and receipts come with it.

**Cons**:
- No Tanzanian mobile money, which is the main market. It would still need ClickPesa beside it, so it adds a third provider instead of removing one.

### Option 4: Trust webhook bodies, push deltas

The same app as Option 1, but it applies each verified event body directly and pushes only changed fields.

**Pros**:
- Fewer API calls and simpler handlers.

**Cons**:
- PayPal events arrive out of order. A late `ACTIVATED` after a `CANCELLED` would turn renewals back on, and a lost delta leaves a site wrong until the next change.

## Rationale

Option 1 is the only one that keeps a single stack for both control site halves (billing here, removal in 0007) and gives you a desk for the support cases the interview surfaced (mismatched payments, refunds, comped sites). Option 2's credential reuse is real, but it splits the control site across two stacks. Verify then fetch, plus a full state push, answers the money force directly: the provider's own API is the truth, and every push repairs any earlier loss. Option 4 fails exactly on PayPal's out of order delivery.

Sub decisions from the interview:
- **Registry by signed `register_site`** (over a bench command by hand or desk entry): it reuses 0007's runner secret, and the site secret is born in one place and never typed.
- **PayPal charges at trial end through `start_time`**, with `paid_until` pushed only once money arrives (over pushing `paid_until` = trial end): a failed first charge then still follows the day 30 trial path rather than gaining grace and a 60 day lapsed hold. The cost is the small customer site "starts on" note (AC-21).
- **ClickPesa year starts at the latest of old end + 1, payment day, trial end + 1**: no one pays for locked time, early renewals lose nothing, and trial payers keep their free days.
- **PayPal `paid_until` from `next_billing_time`** (over our own math): it always matches PayPal's real cycle.
- **Refunds alert and change nothing; mismatches don't push**: at this volume a refund is your own deliberate act, and an underpayment must never buy a year.
- **Password fields for site secrets** (over a site_config map or a vault): encrypted at rest, scales to many sites, no new service.
- **Rotation through the runner**: the runner already writes site files under its own signed channel, so rotation needs no hand typed secret. Accepting both secrets while the rotation is pending (instead of keeping a previous secret for a while after the swap) covers a runner that dies between writing the file and confirming, with one less field.
- **Cross check fixes (Sonnet, 2026-11-18)**: lock the row before the provider read (so events can't apply out of order), `state_version` with one push job per site (so a push can't carry older data), PayPal state only from the `provider_reference` subscription (so auto cancelling a duplicate doesn't stop renewals), raw signed responses (Frappe's wrapper and `frappe.throw` would break the byte exact signature), per site rate limits (all sites share one IP), and `paid_on` instead of ClickPesa's `updatedAt` (which moves at settlement).
- **Control site return page that confirms with the provider**: it is the only way ClickPesa's single dashboard return URL can serve many sites, and confirming there makes the one minute unlock independent of webhook speed.
- **Site facts sent on each signed call** (over the hourly runner report): they are fresh at the moment of payment, at the cost of an amendment to spec 0005.
- **Retries that never give up**: the state is small and idempotent, and stopping would leave a paid site locked.
- **Resend**, already used by rarebooks-site; **two factor sign in for all**; **Billing Manager separate from Removal Manager** so editing payment state and approving a drop stay separate rights.
- **Hosting.** I recommended a separate small VPS. You chose the same server with a separate bench. That works, but it means accepting that a hosting server compromise or outage takes billing with it, and that the runner's MariaDB root login can read the control database. It is acceptable only with the AC-22 isolation in place, and the Redis passwords in particular are not optional, because an open RQ queue lets any local user run code as `control`. Moving to its own VPS later is a backup and restore plus a DNS change, with no code change.
- **Recommended without asking:** `requests` over provider SDKs (two small REST surfaces; the Python PayPal SDK adds weight for five calls; runner up: `paypal-server-sdk`). Refusal codes translated by the customer site (the control site doesn't know the user's language; runner up: English messages from the control site). Copied signing code with shared golden vectors (runner up: a shared Python package, too heavy for one module). PayPal plan ids pasted by hand (runner up: a sync command, worth it only if plans change often). Hourly and daily reconcile jobs as a safety net for missed webhooks. Frappe's S3 Backup Settings to a separate R2 bucket, since the control database becomes the record of who paid.
