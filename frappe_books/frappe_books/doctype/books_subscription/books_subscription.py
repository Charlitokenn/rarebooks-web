# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class BooksSubscription(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		auto_renews: DF.Check
		billing_period: DF.Literal["", "Monthly", "Yearly"]
		checkout_started_on: DF.Datetime | None
		exempt: DF.Check
		last_synced_on: DF.Datetime | None
		paid_until: DF.Date | None
		provider: DF.Literal["", "ClickPesa", "PayPal"]
		provider_reference: DF.Data | None
		trial_started_on: DF.Datetime
	# end: auto-generated types

	_DOCTYPE_NAME = "Books Subscription"

	def validate(self):
		# No role writes this single: only the sync paths in frappe_books.subscription set the flag.
		if not frappe.flags.books_subscription_sync:
			frappe.throw(_("The subscription changes only through billing."), frappe.PermissionError)
		self.keep_last_synced_forward()

	def keep_last_synced_forward(self):
		before = self.get_doc_before_save()
		previous = before and before.last_synced_on
		if previous and (
			not self.last_synced_on or get_datetime(self.last_synced_on) < get_datetime(previous)
		):
			self.last_synced_on = previous
