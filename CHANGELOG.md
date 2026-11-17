# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Expenses: record money the business has already paid out that isn't a purchase invoice (rent, fuel, bank fees). Find them under Purchases → Expenses in the sidebar, with their own list and form. Pick the account it was paid from (Cash, Bank, or a liability with no account type, such as a loan) and add one or more rows, each with an Expense account and an amount. (see spec 0004)
- Submitting an expense posts it to the ledger: each row debits its account, and the total credits the account it was paid from. It then shows in the General Ledger (with "Expenses" as a Ref Type), Top Expenses, and profit and loss for the month of its date. Cancelling reverses those rows. To correct a submitted expense, cancel it and use Duplicate.
- New expenses are numbered from the `EXP-` series by default (Books Defaults → Expense Number Series). Existing sites get the series through a patch when they run `bench migrate`.
- A warning when an expense repeats a supplier's reference number already used on a submitted expense you can read. The save still goes through.
- Expenses on the phone: an "Expense" entry in the dashboard's create menu, a two line list row, and rows edited in a sheet.
- Expenses in search (by number, supplier or reference number), in the Linked entries of a supplier or account (with the expense total), in the Import Wizard (saved as drafts), and in a new "Business - Expense" print format, which is the default.
- A Books User can record expenses without rights on the chart of accounts. Paid From and the row accounts are picked from two server searches that offer only the accounts a save accepts. A Books Cashier gets no access to expenses.
- Choose which accounts the dashboard's Account balances card lists: Settings → General has a new Dashboard section with a Dashboard Accounts table. Pick any leaf Asset or Liability account, such as petty cash or a loan; a liability shows its balance in red and lowers the Total. With the table empty, the card lists every Cash and Bank account, as before. (see spec 0003)
- A "Choose accounts" button on the Account balances card opens those settings, for users who can change Accounting Settings.

### Changed
- A message the server sends with a successful save, delete, submit or cancel now shows as a toast on every form, instead of being dropped. Warnings and errors stay until you close them, and other messages fade after five seconds. The form's live preview stays quiet. (see spec 0006)
- List filters leave out link fields whose target you can't read, so a Books User sees no Paid From filter on Expenses.
- The Account balances card's default list now leaves out Cash and Bank accounts whose root type is not Asset or Liability.
- Reading the Account balances card now also needs read on Accounting Settings. Every Books role has it today, so no one loses the card.
- Saving Accounting Settings is refused when a new or changed Dashboard Accounts row holds a group account or one that isn't Asset or Liability, or when an account is picked twice. Deleting an account that is on the table is refused while it stays there.
