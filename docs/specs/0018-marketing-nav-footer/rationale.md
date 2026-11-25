# 0018. Marketing nav and footer: rationale

## Context

Slice 10 restyles the public pages of `rarebooks.cc` on the spec 0017 design system. The header and footer appear on every one of those pages, so they come before the homepage (feature 18), pricing (feature 19) and the compare pages (feature 20). Today `Navbar.astro` is a floating, blurred pill with five homepage anchors and one "Client Portal" button that leads every visitor to `/dashboard`, signed in or not. Below `md` it shows no links at all: a phone visitor sees only the logo and that button. `Footer.astro` has three columns, commented out legal links, and the 404 page has a footer but no header. Both use the old tokens (`brand`, `ink`, `muted`, `pill`).

Three forces shape the design. Accessibility: the scope asks for menus that open, close and trap focus correctly with keyboard and screen reader, and the slice targets WCAG 2.2 AA. Weight: spec 0017 keeps marketing components free of client JavaScript, and the logo today hydrates a React island on every page only to render a link. Identity: the site already runs `clerkMiddleware` on every request, and the AGENTS.md rule is that identity comes from Clerk on the server.

There are no privacy or terms pages, yet the site sends personal data to Clerk, Cloudflare, Google Tag Manager, tawk.to, Resend, ClickPesa, PayPal and Frappe Cloud, and spec 0009's rollout needs a privacy policy naming tawk.to. Legal text needs the owner's approval before it goes public.

## Options considered

### Option 1: Flat links, server rendered state, native dialog menu (chosen)

Four top level links, no dropdowns. The signed in check runs in the Astro component on the server. The phone menu is a `<dialog>` opened with `showModal()` by the existing `data-open-modal` handler, plus a tiny inline script for backdrop, link tap and resize closing.

**Pros**:
- The browser gives focus trapping, Escape, inert background and focus return for free.
- No dropdown keyboard logic to build or test; every page is one tap from the header.
- No flash of the wrong buttons, and no Clerk client script loaded for the nav.

**Cons**:
- Marketing HTML varies by visitor, which rules out a shared edge cache later.
- Needs a small inline script, an exception to spec 0017's no JS rule.

### Option 2: Two dropdown menus (Product, Resources)

Wave style menus, built with the disclosure pattern and a script for open state, Escape and outside click.

**Pros**:
- Room for many more pages without crowding the bar.
- Familiar on larger SaaS sites.

**Cons**:
- About eight pages today; menus would hide links for no gain.
- Hand written menu keyboard handling is where accessibility bugs live, and needs more JS on every page.

### Option 3: A React island for the whole header

One React component with state for the menu and Clerk's React hooks for the signed in state.

**Pros**:
- One mental model for state; easy to extend.
- Clerk's hooks are documented and well known.

**Cons**:
- Hydrates React on every marketing page, the cost spec 0017 tried to avoid.
- Signed in state resolves on the client, so the buttons can flash or shift on slow phones.

### Option 4: A details disclosure menu with no JavaScript

A `<details>` element whose summary is the Menu button.

**Pros**:
- Zero JavaScript.
- Simplest markup.

**Cons**:
- No focus trap and no Escape handling, so it fails the scope's "trap focus" bar.
- The page behind stays reachable by Tab while the menu covers it.

## Rationale

The site has few pages, so flat links show everything and remove a whole class of accessibility work. The native dialog is the strongest fit for the scope's focus requirements: `showModal()` already does the hard parts, and the project already opens every modal through `data-open-modal`, so the menu reuses a proven path. The extra script is only the three close rules the browser doesn't give, well under 1 KB.

Reading the session on the server follows the AGENTS.md identity rule and removes the flash that a client check causes. The cost is that pages vary by visitor. That is acceptable now because no marketing page is cached at the edge today, and it is written down as an invariant so a later caching change doesn't serve one person's Dashboard button to everyone.

The full width bar was chosen over today's floating pill because the blur costs paint time on low end phones and the pill doesn't match the calm, banded look of spec 0017. Sticky positioning keeps the bar in the page flow, so pages no longer need hand tuned top padding. Gating the legal column behind an approval flag lets the pages be drafted, reviewed at their real URL and shipped without the risk of an unreviewed policy being indexed. The footer sits on the `tint` band (runner up: `ink`) so it reads apart from a canvas page and doesn't merge with an ink closing call to action that feature 18 may add.
