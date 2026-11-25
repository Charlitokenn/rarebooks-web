from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from frappe_books.demo import shop
from frappe_books.tests.accounting import insert_sales_invoice

FRESH_SITE = {"developer_mode": 1, "books_control_url": None}


class IntegrationTestDemoShop(IntegrationTestCase):
	"""The seed can never touch a customer site (spec 0019 AC-15)."""

	def test_refuses_without_developer_mode(self):  # covers: AC-15
		with patch.dict(frappe.conf, {**FRESH_SITE, "developer_mode": 0}):
			self.assert_refused("developer mode")

	def test_refuses_a_hosted_site(self):  # covers: AC-15
		with patch.dict(frappe.conf, {**FRESH_SITE, "books_control_url": "https://control.example"}):
			self.assert_refused("books_control_url")

	def test_refuses_a_site_with_a_submitted_sales_invoice(self):  # covers: AC-15
		insert_sales_invoice(now_datetime(), [])
		with patch.dict(frappe.conf, FRESH_SITE):
			self.assert_refused("submitted sales invoices")

	def test_refuses_any_other_currency(self):  # covers: AC-15
		with patch.dict(frappe.conf, FRESH_SITE):
			with self.assertRaisesRegex(frappe.ValidationError, "TZS or USD"):
				shop.seed("EUR")

	def assert_refused(self, reason):
		with self.assertRaisesRegex(frappe.ValidationError, reason):
			shop.seed("TZS")
		self.assertFalse(frappe.db.exists("Books Party", shop.WALK_IN))
