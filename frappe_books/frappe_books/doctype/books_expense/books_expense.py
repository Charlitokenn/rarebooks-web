# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from frappe_books.accounting.accounts import (
	validate_account,
	validate_expense_payment_account,
	validate_party_role,
)
from frappe_books.accounting.ledger import LedgerPosting, delete_entries, reverse_entries
from frappe_books.accounting.money import rounded, sum_decimal
from frappe_books.permissions import check_preview_permission
from frappe_books.series import SeriesNamingMixin
from frappe_books.status import StatusMixin


class BooksExpense(StatusMixin, SeriesNamingMixin, Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from frappe_books.frappe_books.doctype.books_expense_account.books_expense_account import (
			BooksExpenseAccount,
		)

		accounts: DF.Table[BooksExpenseAccount]
		amended_from: DF.Link | None
		attachment: DF.Attach | None
		date: DF.Date
		number_series: DF.Link
		paid_from: DF.Link
		party: DF.Link | None
		reference_number: DF.Data | None
		status: DF.Literal["Saved", "Submitted", "Cancelled"]
		total: DF.Currency
		user_remark: DF.Text | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Books Expense"

	@frappe.whitelist()
	def preview(self):
		"""Fill the values a save would fill, without saving, for the form to show them."""
		check_preview_permission(self)
		self.set_number_series()
		self._set_total()

	def validate(self):
		if not self.accounts:
			frappe.throw(_("An expense needs at least one row."))
		self._set_total()
		for row in self.accounts:
			if row.amount <= 0:
				frappe.throw(_("Row {0}: amount must be greater than zero.").format(row.idx))
			validate_account(row, "account", root_types=("Expense",))
		validate_expense_payment_account(self, "paid_from")
		validate_party_role(self, is_purchase=True)
		self._warn_duplicate_reference()

	def on_submit(self):
		posting = LedgerPosting(self)
		for row in self.accounts:
			posting.debit(row.account, row.amount)
		posting.credit(self.paid_from, self.total)
		posting.post()

	def on_cancel(self):
		reverse_entries(self)

	def on_trash(self):
		delete_entries(self)

	def _set_total(self):
		"""Round each row first, so the debits always sum to the one credit."""
		for row in self.accounts:
			row.amount = rounded(row.amount)
		self.total = sum_decimal(row.amount for row in self.accounts)

	def _warn_duplicate_reference(self):
		"""Name a submitted expense the user can read with the same supplier and reference, without refusing."""
		if not (self.party and self.reference_number):
			return
		filters = {
			"party": self.party,
			"reference_number": self.reference_number,
			"docstatus": 1,
			"name": ["!=", self.name],
		}
		other = frappe.get_list(self.doctype, filters=filters, pluck="name", limit=1)
		if other:
			frappe.msgprint(
				_("{0} already has reference {1} for {2}.").format(
					other[0], self.reference_number, self.party
				)
			)
