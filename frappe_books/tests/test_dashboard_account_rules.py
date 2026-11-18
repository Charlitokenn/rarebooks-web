from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from frappe_books.frappe_books.doctype.books_accounting_settings.books_accounting_settings import (
	BooksAccountingSettings,
)

CONTROLLER = "frappe_books.frappe_books.doctype.books_accounting_settings.books_accounting_settings"


class UnitTestDashboardAccountRules(UnitTestCase):
	def settings(self, rows, previous=None):
		# Exercise the controller rule without loading Single metadata or writing settings.
		settings = Mock()
		settings.dashboard_accounts = [frappe._dict(name=name, account=account) for name, account in rows]
		settings.get_doc_before_save.return_value = (
			frappe._dict(
				dashboard_accounts=[frappe._dict(name=name, account=account) for name, account in previous]
			)
			if previous is not None
			else None
		)
		return settings

	def test_reordering_saved_rows_does_not_revalidate_stale_accounts(self):
		settings = self.settings([("b", "Loan"), ("a", "Cash")], [("a", "Cash"), ("b", "Loan")])
		with patch(f"{CONTROLLER}.validate_account") as validate:
			BooksAccountingSettings.validate_dashboard_accounts(settings)
		validate.assert_not_called()

	def test_replacing_a_saved_rows_account_validates_the_replacement(self):
		settings = self.settings([("a", "Income")], [("a", "Cash")])
		with patch(f"{CONTROLLER}.validate_account") as validate:
			BooksAccountingSettings.validate_dashboard_accounts(settings)
		validate.assert_called_once_with(
			settings.dashboard_accounts[0], "account", root_types=("Asset", "Liability")
		)

	def test_readding_an_account_as_a_new_row_revalidates_it(self):
		settings = self.settings([("new", "Cash")], [("old", "Cash")])
		with patch(f"{CONTROLLER}.validate_account") as validate:
			BooksAccountingSettings.validate_dashboard_accounts(settings)
		validate.assert_called_once_with(
			settings.dashboard_accounts[0], "account", root_types=("Asset", "Liability")
		)

	def test_saved_duplicates_are_refused_even_when_neither_row_changed(self):
		rows = [("a", "Cash"), ("b", "Cash")]
		with patch(f"{CONTROLLER}.validate_account") as validate:
			self.assertRaisesRegex(
				frappe.ValidationError,
				"more than once",
				BooksAccountingSettings.validate_dashboard_accounts,
				self.settings(rows, rows),
			)
		validate.assert_not_called()

	def test_empty_rows_and_removing_all_rows_need_no_account_validation(self):
		for rows in ([], [("new", ""), ("other", None)]):
			with self.subTest(rows=rows), patch(f"{CONTROLLER}.validate_account") as validate:
				BooksAccountingSettings.validate_dashboard_accounts(self.settings(rows, [("old", "Cash")]))
			validate.assert_not_called()
