from itertools import product
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from frappe_books.accounting.accounts import (
	check_expense_picker_permission,
	is_expense_payment_account,
	validate_expense_payment_account,
)


class UnitTestExpenseAccountRules(UnitTestCase):
	def test_payment_account_eligibility_for_every_root_type(self):
		for root, kind, group in product(
			("Asset", "Liability", "Income", "Expense", "Equity"),
			("Cash", "Bank", "Receivable", "Payable", "", None),
			(0, 1),
		):
			with self.subTest(root=root, kind=kind, group=group):
				values = frappe._dict(root_type=root, account_type=kind, is_group=group)
				expected = not group and (kind in ("Cash", "Bank") or (root == "Liability" and not kind))
				self.assertEqual(is_expense_payment_account(values), expected)

	def test_empty_payment_account_does_not_query_the_database(self):
		with patch("frappe.db.get_value") as get_value:
			validate_expense_payment_account(frappe._dict(paid_from=None), "paid_from")
		get_value.assert_not_called()

	def test_missing_account_is_left_to_link_validation(self):
		with patch("frappe.db.get_value", return_value=None):
			validate_expense_payment_account(frappe._dict(paid_from="Deleted account"), "paid_from")

	def test_picker_accepts_create_or_write_but_never_read_alone(self):
		for rights in (set(), {"read"}, {"create"}, {"write"}, {"create", "write"}):
			with (
				self.subTest(rights=rights),
				patch(
					"frappe.has_permission", side_effect=lambda doctype, ptype, rights=rights: ptype in rights
				),
			):
				if rights & {"create", "write"}:
					check_expense_picker_permission()
				else:
					self.assertRaises(frappe.PermissionError, check_expense_picker_permission)
