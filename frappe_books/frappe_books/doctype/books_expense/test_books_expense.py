# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

from decimal import Decimal

import frappe
from frappe.desk.search import search_widget
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate
from frappe.utils.print_utils import get_print

from frappe_books.accounting.accounts import is_expense_payment_account, search_expense_payment_accounts
from frappe_books.accounting.money import as_decimal
from frappe_books.patches import add_expense_number_series
from frappe_books.reports.dashboard import get_top_expenses
from frappe_books.tests.accounting import (
	ensure_user,
	ledger_entries,
	make_account,
	make_number_series,
	make_party,
)

BOOKS_USER = "books-expense-user@example.com"
BOOKS_CASHIER = "books-expense-cashier@example.com"
BOOKS_MANAGER = "books-expense-manager@example.com"
PAID_FROM_QUERY = "frappe_books.accounting.accounts.search_expense_payment_accounts"

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestBooksExpense(IntegrationTestCase):
	def setUp(self):
		self.cash = make_account("Test Cash", account_type="Cash")
		self.rent = make_account("Test Rent", root_type="Expense")
		self.fuel = make_account("Test Fuel", root_type="Expense")

	def test_submit_debits_each_account_and_credits_paid_from(self):
		expense = make_expense(
			self.cash.name,
			[
				{"account": self.rent.name, "amount": 100},
				{"account": self.fuel.name, "amount": 30},
				{"account": self.fuel.name, "amount": 20},
			],
		)
		expense.submit()

		entries = ledger_entries(expense.doctype, expense.name)
		debits = {entry.account: as_decimal(entry.debit) for entry in entries if entry.debit}
		credits = {entry.account: as_decimal(entry.credit) for entry in entries if entry.credit}
		self.assertEqual(debits, {self.rent.name: Decimal("100"), self.fuel.name: Decimal("50")})
		self.assertEqual(credits, {self.cash.name: Decimal("150")})
		self.assertEqual(as_decimal(expense.total), Decimal("150"))
		self.assertEqual(expense.status, "Submitted")

	def test_ledger_rows_carry_no_party_and_the_expense_date(self):
		supplier = make_party(
			make_account("Test Payable", root_type="Liability", account_type="Payable").name, "Supplier"
		)
		expense = make_expense(
			self.cash.name, [{"account": self.rent.name, "amount": 10}], party=supplier.name
		)
		expense.submit()

		rows = frappe.get_all(
			"Books Ledger Entry",
			filters={"voucher_type": expense.doctype, "voucher_no": expense.name},
			fields=["party", "posting_date"],
		)
		self.assertTrue(rows)
		self.assertTrue(all(row.party is None for row in rows))
		self.assertTrue(all(str(row.posting_date) == str(expense.date) for row in rows))

	def test_rows_are_rounded_before_they_are_summed(self):
		expense = make_expense(
			self.cash.name,
			[{"account": self.rent.name, "amount": 10.004}, {"account": self.fuel.name, "amount": 10.004}],
		)
		self.assertEqual(as_decimal(expense.accounts[0].amount), Decimal("10.00"))
		self.assertEqual(as_decimal(expense.total), Decimal("20.00"))
		expense.submit()
		entries = ledger_entries(expense.doctype, expense.name)
		self.assertEqual(sum(as_decimal(entry.debit) for entry in entries), Decimal("20.00"))
		self.assertEqual(sum(as_decimal(entry.credit) for entry in entries), Decimal("20.00"))

	def test_a_row_that_rounds_to_zero_is_refused(self):
		self.assertRaisesRegex(
			frappe.ValidationError,
			"Row 1: amount must be greater than zero",
			make_expense,
			self.cash.name,
			[{"account": self.rent.name, "amount": 0.004}, {"account": self.fuel.name, "amount": 0.004}],
		)

	def test_submitted_expense_shows_in_top_expenses_until_cancelled(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 987654.32}])
		expense.submit()
		self.assertIn(self.rent.name, top_expense_accounts())

		expense.cancel()
		self.assertNotIn(self.rent.name, top_expense_accounts())
		entries = ledger_entries(expense.doctype, expense.name)
		self.assertEqual(len(entries), 4)
		self.assertTrue(all(entry.reverted for entry in entries))
		self.assertEqual(frappe.db.get_value(expense.doctype, expense.name, "status"), "Cancelled")

	def test_a_draft_can_be_edited_without_ledger_rows(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		expense.accounts[0].amount = 25
		expense.save()
		self.assertEqual(as_decimal(expense.total), Decimal("25"))
		self.assertEqual(expense.status, "Saved")
		self.assertFalse(ledger_entries(expense.doctype, expense.name))

	def test_a_submitted_expense_cannot_change(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		expense.submit()
		expense.paid_from = make_account("Other Cash", account_type="Cash").name
		self.assertRaises(frappe.UpdateAfterSubmitError, expense.save)

	def test_amend_names_the_new_draft_after_the_cancelled_one(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		expense.submit()
		expense.cancel()

		amended = frappe.copy_doc(expense)
		amended.amended_from = expense.name
		amended.docstatus = 0
		amended.insert()

		self.assertEqual(amended.name, f"{expense.name}-1")
		self.assertEqual(amended.status, "Saved")
		self.assertEqual(amended.paid_from, expense.paid_from)
		self.assertEqual(amended.accounts[0].account, self.rent.name)

	def test_new_expense_is_numbered_by_the_default_series(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		self.assertTrue(expense.name.startswith(expense.number_series))

	def test_preview_fills_the_series_and_total_without_saving(self):
		series = make_number_series("Expense")
		frappe.db.set_single_value("Books Defaults", "expense_number_series", series)
		expense = frappe.new_doc("Books Expense")
		expense.append("accounts", {"account": self.rent.name, "amount": 4.5})
		expense.append("accounts", {"account": self.fuel.name, "amount": 5.5})
		count = frappe.db.count("Books Expense")

		expense.preview()

		self.assertEqual(expense.number_series, series)
		self.assertEqual(as_decimal(expense.total), Decimal("10"))
		self.assertEqual(frappe.db.count("Books Expense"), count)

	def test_rejects_an_expense_with_no_rows(self):
		self.assertRaisesRegex(frappe.ValidationError, "at least one row", make_expense, self.cash.name, [])

	def test_rejects_a_zero_or_negative_amount(self):
		for amount in (0, -5):
			with self.subTest(amount=amount):
				self.assertRaisesRegex(
					frappe.ValidationError,
					"Row 1: amount must be greater than zero",
					make_expense,
					self.cash.name,
					[{"account": self.rent.name, "amount": amount}],
				)

	def test_rejects_row_accounts_that_are_not_expense_ledger_accounts(self):
		group = make_account("Test Expense Group", root_type="Expense", is_group=1)
		income = make_account("Test Income", root_type="Income")
		for account, message in ((group.name, "group account"), (income.name, "must be of type Expense")):
			with self.subTest(account=account):
				self.assertRaisesRegex(
					frappe.ValidationError,
					message,
					make_expense,
					self.cash.name,
					[{"account": account, "amount": 10}],
				)

	def test_paid_from_takes_cash_bank_or_an_untyped_liability(self):
		allowed = (
			self.cash.name,
			make_account("Test Bank", account_type="Bank").name,
			make_account("Test Loan", root_type="Liability").name,
		)
		for account in allowed:
			with self.subTest(account=account):
				make_expense(account, [{"account": self.rent.name, "amount": 10}])

		refused = (
			(
				make_account("Test Payable", root_type="Liability", account_type="Payable").name,
				"must be a Cash",
			),
			(make_account("Test Tax", root_type="Liability", account_type="Tax").name, "must be a Cash"),
			(make_account("Test Asset").name, "must be a Cash"),
			(make_account("Test Cash Group", is_group=1, account_type="Cash").name, "group account"),
		)
		for account, message in refused:
			with self.subTest(account=account):
				self.assertRaisesRegex(
					frappe.ValidationError,
					message,
					make_expense,
					account,
					[{"account": self.rent.name, "amount": 10}],
				)

	# covers: AC-3, AC-4
	def test_the_paid_from_search_offers_exactly_what_the_save_accepts(self):
		offered = (
			self.cash.name,
			make_account("Search Bank", account_type="Bank").name,
			make_account("Search Loan", root_type="Liability").name,
		)
		left_out = (
			make_account("Search Payable", root_type="Liability", account_type="Payable").name,
			make_account("Search Tax", root_type="Liability", account_type="Tax").name,
			make_account("Search Asset").name,
			make_account("Search Cash Group", is_group=1, account_type="Cash").name,
			self.rent.name,
		)

		found = [row.name for row in paid_from_search("")]

		for account in offered:
			self.assertIn(account, found)
		for account in left_out:
			self.assertNotIn(account, found)
		for account in found:
			values = frappe.db.get_value(
				"Books Account", account, ["is_group", "account_type", "root_type"], as_dict=True
			)
			self.assertTrue(is_expense_payment_account(values), account)
		for account in offered:
			with self.subTest(account=account):
				make_expense(account, [{"account": self.rent.name, "amount": 10}])

	# covers: AC-3
	def test_the_paid_from_search_matches_the_text_typed(self):
		loan = make_account("Search Typed Loan", root_type="Liability").name

		found = [row.name for row in paid_from_search(loan)]

		self.assertIn(loan, found)
		self.assertNotIn(self.cash.name, found)

	# covers: AC-8
	def test_a_cashier_gets_a_permission_error_from_the_paid_from_search(self):
		with self.set_user(ensure_user(BOOKS_CASHIER, "Books Cashier")):
			self.assertRaises(
				frappe.PermissionError,
				search_expense_payment_accounts,
				"Books Account",
				"",
				"name",
				0,
				20,
				[],
			)

	def test_a_books_user_can_use_the_paid_from_search(self):
		with self.set_user(ensure_user(BOOKS_USER, "Books User")):
			found = [row.name for row in paid_from_search("")]
		self.assertIn(self.cash.name, found)

	def test_party_must_be_a_supplier(self):
		receivable = make_account("Test Receivable", account_type="Receivable").name
		payable = make_account("Test Payable", root_type="Liability", account_type="Payable").name
		customer = make_party(receivable, "Customer")
		self.assertRaisesRegex(
			frappe.ValidationError,
			"must be a Supplier",
			make_expense,
			self.cash.name,
			[{"account": self.rent.name, "amount": 10}],
			party=customer.name,
		)
		for role in ("Supplier", "Both"):
			party = make_party(payable if role == "Supplier" else receivable, role)
			make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}], party=party.name)

	def test_warns_but_saves_when_a_supplier_reference_repeats(self):
		payable = make_account("Test Payable", root_type="Liability", account_type="Payable").name
		supplier = make_party(payable, "Supplier")
		rows = [{"account": self.rent.name, "amount": 10}]
		first = make_expense(self.cash.name, rows, party=supplier.name, reference_number="R-77")
		first.submit()
		frappe.clear_messages()

		second = make_expense(self.cash.name, rows, party=supplier.name, reference_number="R-77")

		self.assertTrue(second.name)
		messages = [frappe.parse_json(message).get("message") for message in frappe.message_log]
		self.assertIn(f"{first.name} already has reference R-77 for {supplier.name}.", messages)

	def test_books_user_cannot_delete_but_a_manager_can(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		with self.set_user(ensure_user(BOOKS_USER, "Books User")), self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(expense.doctype, expense.name)

		expense.submit()
		expense.cancel()
		with self.set_user(ensure_user(BOOKS_MANAGER, "Books Manager")):
			frappe.delete_doc(expense.doctype, expense.name)
		self.assertFalse(frappe.db.exists(expense.doctype, expense.name))
		self.assertFalse(ledger_entries(expense.doctype, expense.name))

	def test_a_submitted_expense_cannot_be_deleted(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		expense.submit()
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, expense.doctype, expense.name)

	def test_books_user_records_submits_cancels_and_amends(self):
		with self.set_user(ensure_user(BOOKS_USER, "Books User")):
			expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
			expense.submit()
			expense.cancel()
			amended = frappe.copy_doc(expense)
			amended.amended_from = expense.name
			amended.docstatus = 0
			amended.insert()
		self.assertEqual(amended.amended_from, expense.name)

	def test_a_cashier_has_no_rights_on_expenses(self):
		expense = make_expense(self.cash.name, [{"account": self.rent.name, "amount": 10}])
		with self.set_user(ensure_user(BOOKS_CASHIER, "Books Cashier")):
			self.assertRaises(frappe.PermissionError, frappe.get_list, "Books Expense")
			self.assertRaises(
				frappe.PermissionError,
				make_expense,
				self.cash.name,
				[{"account": self.rent.name, "amount": 10}],
			)
			self.assertRaises(frappe.PermissionError, frappe.new_doc("Books Expense").preview)
			self.assertFalse(frappe.has_permission("Books Expense", "read", doc=expense.name))

	def test_prints_the_rows_and_total_by_default(self):
		expense = make_expense(
			self.cash.name,
			[{"account": self.rent.name, "description": "November rent", "amount": 1234.5}],
			reference_number="RCPT-9",
		)
		html = get_print(expense.doctype, expense.name)

		for text in (
			'class="books-print"',
			expense.name,
			self.cash.name,
			self.rent.name,
			"November rent",
			"RCPT-9",
		):
			self.assertIn(text, html)

	def test_patch_adds_the_series_and_keeps_a_chosen_default(self):
		chosen = make_number_series("Expense")
		frappe.db.set_single_value("Books Defaults", "expense_number_series", chosen)
		add_expense_number_series.execute()
		self.assertTrue(frappe.db.exists("Books Number Series", "EXP-"))
		self.assertEqual(frappe.db.get_single_value("Books Defaults", "expense_number_series"), chosen)

		frappe.db.set_single_value("Books Defaults", "expense_number_series", None)
		add_expense_number_series.execute()
		self.assertEqual(frappe.db.get_single_value("Books Defaults", "expense_number_series"), "EXP-")


def top_expense_accounts():
	return [row["account"] for row in get_top_expenses("This Month")]


def paid_from_search(text):
	"""Search the Paid From picker as the /books link search does."""
	return search_widget("Books Account", text, query=PAID_FROM_QUERY, page_length=1000, as_dict=True)


def make_expense(paid_from, accounts, **values):
	return frappe.get_doc(
		{
			"doctype": "Books Expense",
			"date": nowdate(),
			"paid_from": paid_from,
			"accounts": accounts,
			**values,
		}
	).insert()
