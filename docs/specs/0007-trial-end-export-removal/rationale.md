# 0007. Trial end export and site removal: decision record

Build spec: [index.md](index.md).

## Context

Spec 0005 gives every hosted site a 30 day clock and a read only lock from day 26, and it names day 30 (`removal_on`) as the removal date. Nothing yet removes a site, so unpaid trials and long lapsed sites would sit read only on the hosting bench for good, using disk, backups and attention. Scope feature 7 asks for removal on day 30, with the owner's data sent to them first and warnings before.

The forces:
- **It can't be undone.** A dropped site and its database are gone. A bug, a missed payment, or a clock disagreement deletes a real customer's books. Any doubt must end in "don't drop".
- **A site can't remove itself.** `bench drop-site` needs the bench, the database root login and the shell. Code inside the site runs in a web worker or a background job of that same site, and so does the read only lock.
- **The clock already lives on the site.** Spec 0005 works the phase out from the stored facts, the site's time zone and today. A second copy of those rules elsewhere can disagree near midnight.
- **The owner must outlive the site.** Whoever receives the warnings and the export must be reachable after the site is gone, and must not be changeable by a site user who wants a copy of the books.
- **Exports can be large.** Years of invoices plus uploaded files go past email attachment limits, and once the site is dropped it can't serve a download.
- **Self hosting promise.** The app is AGPL, and an owner who leaves should be able to run their books on their own Frappe bench.
- **The control site isn't built yet** (feature 8). It is already the billing authority in spec 0005 and was named as the likely removal runner there.

## Options considered

### Option 1: The control site removes sites itself

The control site lives on the same bench and runs the export and `bench drop-site` from its own background jobs.

**Pros**:
- One place holds all the logic. No host script.

**Cons**:
- The control site needs shell access and the database root login for every customer site, which makes one web app able to drop the whole fleet.
- It ties the control site to the hosting bench, so you can't move or scale either one alone.

### Option 2: The control site decides, a bench command on the host carries it out (chosen)

A `bench books-removal-run` command in frappe_books, run hourly by host cron, reads each site's status in process, reports it in one signed call, and runs the instructions it gets back. The control site owns the case, the warnings, the emails and the go ahead.

**Pros**:
- The dangerous rights (bench, database root) stay on the host. The control site only says yes or no.
- The runner ships in the app that is already on every hosting bench, and it calls the export code directly with no HTTP.
- The site stays the only clock.

**Cons**:
- Three parts must agree on a contract, and the hourly cadence adds up to an hour of delay at each step.
- The host now keeps the database root password in its config for cron.

### Option 3: The control site flags, an operator removes by hand

The control site lists the sites due and sends warnings. You run the export and the drop yourself.

**Pros**:
- A human looks at every deletion.

**Cons**:
- Doesn't scale, and a busy week means sites linger past their date, which breaks the promise in the banner.
- Manual exports vary, so owners get different contents.

### Option 4: Each site schedules its own export, a host job only drops

The site's scheduler builds and emails its export on day 30, and a host cron drops any site marked done.

**Pros**:
- No control site involvement for the export.

**Cons**:
- On a locked site, scheduled jobs run, but its outgoing email and file writes go through the site, and the owner address would be the site's, which a site user can change.
- Two independent schedulers, with no single record of whether the owner was warned and the export delivered before the drop.

## Rationale

Option 2 is the only one that keeps both "a site can't remove itself" and "the dangerous rights stay on the host" while still running on its own. Shipping the runner inside frappe_books means one release changes both the export and the code that calls it, and the runner reads the site's clock directly, so the date in the banner is the date used. The control site was already the billing authority, so making it the decider puts the final "still unpaid?" check next to the payment record. Option 1 was the runner up: fewer parts, but a web app holding root over every customer database is the wrong place for that power.

The safety rules all come from the "can't be undone" force: a warning sent 24 hours or more before the export, a 72 hour hold that covers a weekend, a delivered export email before the drop, three tries then a human, two "still unpaid" checks at the last moment, and a `dry_run` mode before the first live run. Each one turns a failure into a delay, never into a deletion.

The export carries both a readable CSV set and a database backup, because an owner without Frappe needs to open their records, and an owner who wants to self host needs to restore them. Files appear once, loose in `files/`, so the zip isn't twice the size. The download link is a control site redirect because R2 and S3 presigned URLs last at most 7 days, and the link must work for 30. R2 was chosen for its free downloads and its lifecycle rules, which make the 90 day retention automatic.

### Smaller calls made while writing

- **Files once, not twice.** The readable `files/` folder doubles as the restore source (the README says to copy it into the new site), and the backup holds only the database. Runner up: the backup's own file tars as well, which doubles the zip.
- **No site config in the zip.** `site_config.json` holds `books_control_secret` and the database password. The README tells the owner to create a fresh site and restore into it.
- **Dry run emails go to `books_ops_email`.** You picked "warn, export and email, but never drop". Sending real owners "your site will be removed" during a rehearsal would alarm customers whose site isn't actually going, so dry run emails go to the ops address with the owner's address shown in the body. Runner up: send to owners, which tests deliverability but frightens them.
- **The hold starts when the email is `Sent`.** `frappe.sendmail` only queues, so the 72 hours count from the Email Queue sent time, and an email stuck unsent for 24 hours fails the case.
- **At most 3 exports per run.** This bounds a run's length under `flock`. Runner up: no cap, so a mass expiry could hold the lock for hours and delay drops.
- **Secrets in their own file, not `common_site_config.json`.** Every site reads `common_site_config.json` through `frappe.conf`, so anything there is visible to tenant code. `<bench>/config/books-runner.json` (mode 600) is never loaded by Frappe. Runner up: bench's own `root_login` and `root_password` keys, which bench already reads, but which every site could then see.
- **`dns_multitenant` required.** Then a dropped site needs no nginx regeneration and no `sudo` from cron.
- **The disk check is twice the database plus files.** It leaves room for the folder and the zip at once.
- **Approval on every drop at first** (your pick, after the cross check). With one operator and a delete that can't be undone, a manual click is the cheapest big safety gain, and the switch turns it off later. A daily cap and a kill switch for each bench stop a clock bug from removing many sites at once.
- **Lapsed removal 60 days after grace** (your pick). It gives a paying customer two months read only, so the lapsed date is `paid_until` plus 67.

### Cross check (2026-11-18)

An independent read on another model found gaps that the first draft left to the builder or got wrong. All fixes were applied on your instruction:
- Secrets moved out of `common_site_config.json`, hosted sites keep server scripts off, and the control site's answers are signed and checked (the runner acts on them, so they must be trusted).
- Dry run cases are tagged and cancelled by the first live report, so a rehearsal can never lead to a live drop of an owner who was never warned.
- The drop also refuses while a payment is pending, a checkout started in the last 24 hours, or `auto_renews` is set, and checkout is refused in the last hour before the hold ends, which closes the race between a late payment and the drop.
- Each export attempt gets its own R2 key and the runner never deletes objects, so a duplicate upload can't delete the good one; the drop checks the object is in R2 first.
- Drops are safe to repeat, use an exact archived path per case, and take the root login from the secrets file, never the command line.
- Deferred exports don't count as failures; stuck, silent and erroring cases alert ops.
- `removal_on` only moves later on the control site; the banner wording says "after" the date, so a delay never makes it false; the hold date shows in the site's time zone; the export adds `File.csv`, reads one consistent snapshot, and is honest about the hashes and secrets in the dump.
