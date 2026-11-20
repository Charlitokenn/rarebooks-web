import json

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.accounting.accounts import DASHBOARD_ROOT_TYPES
from frappe_books.tests.accounting import make_account, set_dashboard_accounts

SETTINGS = "Books Accounting Settings"


class IntegrationTestSettingsAccounts(IntegrationTestCase):
	def test_settings_reject_accounts_of_the_wrong_type(self):
		cash = make_account("Settings Cash", account_type="Cash").name
		receivable = make_account("Settings Receivable", account_type="Receivable").name
		for doctype, fieldname, account in (
			("Books Accounting Settings", "discount_account", cash),
			("Books Inventory Settings", "stock_in_hand", cash),
			("Books Inventory Settings", "stock_adjustment", cash),
			("Books Pos Settings", "cash_account", receivable),
			("Books Pos Settings", "write_off_account", cash),
			("Books Pos Settings", "default_account", cash),
			("Books Defaults", "sales_payment_account", receivable),
			("Books Defaults", "purchase_payment_account", receivable),
		):
			with self.subTest(fieldname=fieldname):
				self.assertRaisesRegex(
					frappe.ValidationError, "must be of type", self.save, doctype, fieldname, account
				)

	def test_settings_reject_group_accounts(self):
		group = make_account("Settings Cash Group", account_type="Cash", is_group=1).name
		for doctype, fieldname in (
			("Books Pos Settings", "cash_account"),
			("Books Defaults", "sales_payment_account"),
		):
			with self.subTest(fieldname=fieldname):
				self.assertRaisesRegex(
					frappe.ValidationError, "group account", self.save, doctype, fieldname, group
				)

	def test_payment_defaults_take_cash_or_bank_accounts(self):
		for account_type in ("Cash", "Bank"):
			account = make_account(f"Settings {account_type}", account_type=account_type).name
			for fieldname in ("sales_payment_account", "purchase_payment_account"):
				with self.subTest(account_type=account_type, fieldname=fieldname):
					self.save("Books Defaults", fieldname, account)

	def save(self, doctype, fieldname, account):
		settings = frappe.get_single(doctype)
		settings.set(fieldname, account)
		_save(settings)


class IntegrationTestDashboardAccountRules(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(set_dashboard_accounts)

	def test_a_leaf_asset_and_a_leaf_liability_can_be_picked(self):
		bank = make_account("Dashboard Bank", account_type="Bank").name
		loan = make_account("Dashboard Loan", root_type="Liability").name
		set_dashboard_accounts(bank, loan)
		saved = [row.account for row in frappe.get_single(SETTINGS).dashboard_accounts]
		self.assertEqual(saved, [bank, loan])

	def test_a_duplicate_a_group_or_another_root_type_is_refused(self):
		bank = make_account("Dashboard Twice", account_type="Bank").name
		group = make_account("Dashboard Group", is_group=1).name
		income = make_account("Dashboard Income", root_type="Income").name
		for accounts, message in (
			((bank, bank), "more than once"),
			((group,), "group account"),
			((income,), "must be of type"),
		):
			with self.subTest(message=message):
				self.assertRaisesRegex(frappe.ValidationError, message, set_dashboard_accounts, *accounts)

	# covers: AC-3
	def test_an_equity_leaf_is_refused_with_the_field_label_and_the_allowed_types(self):
		equity = make_account("Dashboard Equity", root_type="Equity").name
		self.assertRaisesRegex(
			frappe.ValidationError,
			rf"^Account must be of type Asset or Liability, but {equity} is not\.$",
			set_dashboard_accounts,
			equity,
		)

	def test_a_pick_that_stopped_qualifying_does_not_block_other_settings(self):
		stale = self.stale_pick("Dashboard Stale")
		# Saving runs every rule, so a save that changes nothing else stands in for one of another setting.
		_save(frappe.get_single(SETTINGS))

		income = make_account("Dashboard Changed Income", root_type="Income").name
		settings = frappe.get_single(SETTINGS)
		self.assertEqual(settings.dashboard_accounts[0].account, stale)
		settings.dashboard_accounts[0].account = income
		self.assertRaisesRegex(frappe.ValidationError, "must be of type", _save, settings)

	def test_a_row_edited_onto_a_removed_rows_stale_account_is_checked(self):
		bank = make_account("Dashboard Kept", account_type="Bank").name
		stale = self.stale_pick("Dashboard Removed", bank)
		settings = frappe.get_single(SETTINGS)
		first, second = settings.dashboard_accounts
		settings.remove(first)
		second.account = stale
		self.assertRaisesRegex(frappe.ValidationError, "group account", _save, settings)

	def test_the_picker_filters_mirror_the_save_rule(self):
		field = frappe.get_meta("Books Dashboard Account").get_field("account")
		filters = {
			(name, operator): value for _doctype, name, operator, value in json.loads(field.link_filters)
		}
		self.assertEqual(filters, {("is_group", "="): 0, ("root_type", "in"): list(DASHBOARD_ROOT_TYPES)})

	def stale_pick(self, label, *others):
		"""Save a bank account as the first pick, then turn it into a group, as a chart change would."""
		account = make_account(label, account_type="Bank").name
		set_dashboard_accounts(account, *others)
		frappe.db.set_value("Books Account", account, "is_group", 1)
		self.addCleanup(frappe.db.set_value, "Books Account", account, "is_group", 0)
		return account


def _save(settings):
	# A test site skips the setup wizard that fills the company details.
	settings.flags.ignore_mandatory = True
	settings.save()
