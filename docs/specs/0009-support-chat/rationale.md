# 0009. Support chat with a signed tawk.to visitor: rationale

The decision record behind [index.md](index.md).

## Context

Hosted customers have no way to reach support from inside /books. When something goes wrong (the read only lock, a failed checkout, a confusing screen) they leave the app to find an email address, and support then has to ask who they are, which company, which site and what state the subscription is in. The scope picks tawk.to as the provider (scope row 10).

Forces that shape the design:

- **Identity must be trustworthy.** A chat widget runs in the browser, so anything the page tells tawk.to can be edited in the console. Support acts on what the visitor says (a subscription question, a data fix), so a visitor who can claim any email is a real risk.
- **The lock must not cut off help.** A locked site runs every request in a read only transaction (spec 0005). The user who most needs support is the one looking at the lock notice.
- **Phones and shared tills.** The POS phone view has bottom bars a floating bubble would cover. Cashiers share one device, so one person's chat must not follow the next person.
- **Third party script.** tawk.to can be blocked (ad blockers, school or office networks) or down. /books must work normally either way, and users should not send data to a third party they never asked to talk to.
- **One operator, many sites.** All hosted sites live on one hosting bench and are supported by one team. Customers must not be able to point the chat at their own tawk.to account or read the signing key.

## Options considered

### Option 1: Unsigned widget with the tawk.to bubble

Paste the standard embed snippet into the /books page with the keys in the build, and set the name and email in the browser from the boot. Fewest moving parts.

**Pros**: almost no code; the bubble and its defaults just work.
**Cons**: anyone can claim any email from the console; the bubble covers POS controls on a phone; every session loads a third party script and sends data to tawk.to whether or not the user wanted help; keys in the build turn the chat on for every install.

### Option 2: Signed visitor in the boot, own launcher, loaded on first open (chosen)

The server adds a `support_chat` block to `extend_bootinfo` with the widget IDs, the visitor signed with Secure Mode, and the attributes. /books shows its own "Chat with support" entries, loads the script only when one is picked, keeps the bubble hidden, and ends the tawk.to session at sign out.

**Pros**: identity can't be faked; nothing goes to tawk.to until the user asks; works on a locked site with no new endpoint; no floating element over controls; keys stay operator only.
**Cons**: more client code (a loader with timeout, hide on minimize, logout); the agents can't see users browsing or reach out first; relies on tawk.to keeping its JavaScript API stable.

### Option 3: Signed visitor from a whitelisted method on open

Same as Option 2, but the client calls a new `get_support_chat()` method when the chat is first opened instead of reading the boot.

**Pros**: data is fresh at the moment of opening; nothing extra in the boot.
**Cons**: one more request that can fail on its own; needs a slot in the lock's `ALLOWED_METHODS` and its allowlist test; adds a second failure path before the script even starts loading.

## Rationale

Trustworthy identity is the line the scope draws ("a user can't pose as someone else"), and only Secure Mode meets it, so the API key has to live on the server and the hash has to be computed there. That rules out Option 1. Between the two server options, the boot wins on the lock force: the boot is already built for every /books page load, the lock reads it today for the banner, and it needs no change to `ALLOWED_METHODS`. Computing one HMAC per page load costs nothing. The only gain of Option 3 (freshness) doesn't matter here, since a name or company change is rare and the next page load picks it up.

Loading on first open and using our own entries answer the phone, shared till and third party forces together: nothing floats over POS controls, a blocked tawk.to can only affect the moment someone asks for help, and no data leaves for tawk.to until the user picks the entry. The cost is losing proactive chat (agents can't see users browsing). For a small support team at Beta that's an acceptable trade. Putting the keys in `common_site_config.json` gives one property for the whole hosting bench, out of reach of any site user (Frappe exposes no site config over HTTP), and naturally off on self hosted or dev benches.
