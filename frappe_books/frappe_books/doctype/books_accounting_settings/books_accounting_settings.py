# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from frappe_books.accounting.accounts import (
	DASHBOARD_ROOT_TYPES,
	validate_account,
	validate_changed_accounts,
)
from frappe_books.coa import ensure_discount_account
from frappe_books.regional import validate_gstin
from frappe_books.settings import company_country, validate_one_way_switches

POINT_OF_SALE_FEATURES = (
	"enable_batches",
	"enable_uom_conversions",
	"enable_serial_number",
	"enable_barcodes",
	"enable_point_of_sale",
)
ONE_WAY_SWITCHES = (
	"enable_discounting",
	"enable_inventory",
	"enable_lead",
	"enable_invoice_returns",
	"enable_loyalty_program",
	"enable_point_of_sale_with_out_inventory",
	"enableitem_group",
)

ACCOUNT_TYPES = {
	"write_off_account": {"root_types": ("Expense",)},
	"round_off_account": {"root_types": ("Expense",)},
	"discount_account": {"root_types": ("Income",)},
}


class BooksAccountingSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from frappe_books.frappe_books.doctype.books_dashboard_account.books_dashboard_account import (
			BooksDashboardAccount,
		)

		bank_name: DF.Data
		company_name: DF.Data
		country: DF.Link | None
		dashboard_accounts: DF.Table[BooksDashboardAccount]
		discount_account: DF.Link | None
		email: DF.Data
		enable_coupon_code: DF.Check
		enable_discounting: DF.Check
		enable_form_customization: DF.Check
		enable_inventory: DF.Check
		enable_invoice_returns: DF.Check
		enable_item_enquiry: DF.Check
		enable_lead: DF.Check
		enable_loyalty_program: DF.Check
		enable_partial_payment: DF.Check
		enable_point_of_sale_with_out_inventory: DF.Check
		enable_price_list: DF.Check
		enable_pricing_rule: DF.Check
		enableitem_group: DF.Check
		fiscal_year_end: DF.Date
		fiscal_year_start: DF.Date
		fullname: DF.Data
		gstin: DF.Data | None
		round_off_account: DF.Link | None
		setup_complete: DF.Check
		tax_id: DF.Data | None
		write_off_account: DF.Link | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Books Accounting Settings"

	@property
	def country(self):
		"""The company country, which Frappe's System Settings holds."""
		return company_country()

	def before_validate(self):
		if self.is_enabled_now("enable_discounting") and not self.discount_account:
			self.discount_account = ensure_discount_account()

	def on_update(self):
		if self.is_enabled_now("enable_point_of_sale_with_out_inventory"):
			inventory_settings = frappe.get_single("Books Inventory Settings")
			inventory_settings.update(dict.fromkeys(POINT_OF_SALE_FEATURES, 1))
			inventory_settings.save()

	def is_enabled_now(self, fieldname):
		return bool(self.get(fieldname)) and self.has_value_changed(fieldname)

	def validate(self):
		validate_one_way_switches(self, ONE_WAY_SWITCHES)
		validate_changed_accounts(self, ACCOUNT_TYPES)
		self.validate_dashboard_accounts()
		if self.gstin and company_country() == "India":
			self.gstin = validate_gstin(self.gstin)

	def validate_dashboard_accounts(self):
		"""Refuse a duplicate pick, and check the rows that are new or changed.

		A saved row whose account has since stopped qualifying is left alone, so it does not block saving
		other settings; the card skips it.
		"""
		rows = [row for row in self.dashboard_accounts if row.account]
		seen = set()
		for row in rows:
			if row.account in seen:
				frappe.throw(_("{0} is on the dashboard more than once.").format(row.account))
			seen.add(row.account)
		before = self.get_doc_before_save()
		previous = {row.name: row.account for row in before.dashboard_accounts} if before else {}
		for row in rows:
			if previous.get(row.name) != row.account:
				validate_account(row, "account", root_types=DASHBOARD_ROOT_TYPES)
