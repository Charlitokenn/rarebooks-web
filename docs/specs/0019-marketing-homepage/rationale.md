# 0019. Marketing homepage: rationale

The decision record behind [index.md](index.md). `/develop` builds from `index.md` and can skip this file.

## Context

The `rarebooks-site` homepage is the first page most visitors see and the start of every sign up. Today it is built from seven older components on the purple tokens in `global.css`: a hero with an inline Arcade demo, an old way versus RareBooks list, a trial steps section, full pricing, and a closing call to action. Specs 0017 and 0018 have built the new `mk` design system and the new header and footer, and the homepage already sits between MkNav and MkFooter, so its body is now the odd one out.

The page carries real business weight. It must keep two versions, one for Tanzania (shops moving off notebooks, TZS, mobile money, a paid setup offer) and one for everyone else (books and tax, USD, data import), picked on the server from the visitor's country. It must stay fast on a phone, since most Tanzanian visitors arrive on mobile data, and the inline Arcade iframe is the heaviest thing on it today. Its trial wording is out of step with the product: the constants and copy say a 30 day free trial, but spec 0005 runs it as 21 free days, a pay window to day 30, read only from day 26, and spec 0007 removes an unpaid site on day 30. The legal drafts from spec 0018 already state the real numbers.

The scope's done line asks for real product screenshots in every feature row. The repo has one sample image, and screenshots of a live customer's books can't be used. Whatever produces the images has to be repeatable, because the /books UI keeps changing under the version-16 line, and spec 0017 already settled that images are resized ahead of time by `npm run screenshots` since the Cloudflare adapter can't resize at request time.

Not deciding means `/develop` would invent the section copy, the claims made about the product, and where screenshots come from, which is exactly where a marketing page goes wrong: promises the product doesn't keep, or pictures that leak real data.

## Options considered

### Option 1: Seven `mk` bands, scripted screenshots from a seeded demo shop, demo in a dialog

The page is rebuilt from spec 0017 components with every string fixed in the spec. A dev only seed command in `rarebooks-web` fills two local sites (TZS and USD) with a fictional shop; a Playwright script captures five screens from each; the Arcade demo loads only when a visitor asks for it.

**Pros**:
- Real screens in the visitor's currency, and no customer data anywhere near the pipeline.
- Screenshots can be taken again in minutes after a UI change.
- The heaviest third party embed leaves the first load, which protects mobile LCP (Largest Contentful Paint, when the biggest thing on screen finishes drawing).
- Copy reviewed once in the spec, then built word for word.

**Cons**:
- Two moving parts to maintain: the seed (which must follow doctype changes) and the capture script.
- Ten image sources in the repo.
- One more inline script on the page.

### Option 2: Same page, screenshots taken by hand

The same bands and copy, but you capture each screen yourself from a demo site and drop the files in.

**Pros**:
- No seed or capture code to write or keep working.
- You choose exactly what each frame shows, by eye.

**Cons**:
- Every refresh is manual, so screenshots drift out of date as /books changes.
- Two currency sets by hand doubles the work and invites mismatched shots.
- Nothing stops a real customer's site being used by accident.

### Option 3: Keep the Arcade demo as the hero, restyle the rest

The interactive demo stays inline as the hero visual, with feature rows and the other bands rebuilt below.

**Pros**:
- The demo is the richest picture of the product, right at the top.
- Fewer screenshots needed.

**Cons**:
- The iframe and its scripts load on every visit, hurting mobile LCP and the Lighthouse numbers the scope asks to keep.
- An iframe as the largest element is hard to make the LCP target reliably.
- The demo shows one currency and one shop for every visitor.

## Rationale

Option 1 is chosen because it meets the three forces that matter most at once: real screenshots in every row without touching customer data, a phone first load light enough to keep LCP good, and a page that keeps telling the truth as the product changes. The seed and capture script cost a day or two up front, but the version-16 UI is still moving, and hand taken shots (Option 2) would go stale with no one noticing, in two currencies. Seeding through the normal controllers also means the dashboard cards, best sellers and profit and loss show numbers the product really computed, not mock ups.

Moving the Arcade demo into a dialog (instead of Option 3) follows directly from the speed requirement: a screenshot with `fetchpriority="high"` is a predictable LCP element, while a third party iframe is not. The demo stays one click away for the visitors who want it, and the always present link to open it in a new tab covers browsers that block the embed.

Fixing the copy in the spec is deliberate. The old page claimed features (stock out notifications to your phone, instant tax ready financials) that this spec can't confirm the version-16 app has, so every claim in the new copy is tied to a screen and checked on the seeded site before merge (AC-14). The trial wording follows spec 0005 rather than the old "30 days free", because the legal drafts already state 21 and 30, and a homepage that promises more than the terms is the kind of mismatch that turns into support tickets on day 26.

Smaller calls made here: the trust row shows the quote only once you supply a real one, rather than shipping a placeholder; signed in visitors see "Go to your dashboard" in the body, matching the spec 0018 nav, since a second sign up isn't allowed (spec 0014); and the old hero and closing `cta_location` names are kept so the analytics history carries across the redesign.
