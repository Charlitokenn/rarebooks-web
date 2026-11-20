import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

import frappe_books
from frappe_books.boot import extend_bootinfo
from frappe_books.support_chat import boot_block, has_real_email
from frappe_books.tests.subscription import make_user

API_KEY = "tawk-test-key"
CHAT_CONFIG = {
	"books_tawk_property_id": "property-123",
	"books_tawk_widget_id": "widget-abc",
	"books_tawk_api_key": API_KEY,
}
CASHIER = "support-chat-cashier@books.test"
# HMAC SHA256 of CASHIER keyed with API_KEY, worked out once outside the app.
CASHIER_HASH = "3d5a7d57b8fbddb92c107e174e0f7382d56698538c9fe01e2287d5d81de1134e"
PLACEHOLDER_USER = "Support-Chat@Example.com"


def chat_config(**overrides):
	return patch.dict(frappe.conf, {**CHAT_CONFIG, **overrides})


class IntegrationTestSupportChat(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(CASHIER, "Books Cashier")
		make_user(PLACEHOLDER_USER.lower(), "Books User")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def block_for(self, user, **config):
		frappe.set_user(user)
		with chat_config(**config):
			return boot_block()

	def test_a_signed_visitor_for_a_books_user(self):
		block = self.block_for(CASHIER, books_support_email="help@books.test")
		self.assertEqual(block["property_id"], "property-123")
		self.assertEqual(block["widget_id"], "widget-abc")
		self.assertEqual(block["visitor"]["email"], CASHIER)
		self.assertEqual(block["visitor"]["hash"], CASHIER_HASH)
		self.assertEqual(block["visitor"]["name"], "Books Cashier")
		self.assertEqual(block["support_email"], "help@books.test")
		attributes = block["attributes"]
		self.assertEqual(attributes["site"], frappe.local.site)
		self.assertEqual(attributes["roles"], "Books Cashier")
		self.assertEqual(attributes["app-version"], frappe_books.__version__)

	def test_off_when_any_key_is_missing(self):
		for key in CHAT_CONFIG:
			with self.subTest(key=key):
				self.assertIsNone(self.block_for(CASHIER, **{key: None}))

	def test_no_support_email_leaves_it_out(self):
		self.assertNotIn("support_email", self.block_for(CASHIER))

	def test_administrator_guest_and_placeholder_emails_get_no_chat(self):
		for user in ("Administrator", "Guest", PLACEHOLDER_USER.lower()):
			with self.subTest(user=user):
				self.assertIsNone(self.block_for(user))

	def test_the_real_email_rule_ignores_case_and_spaces(self):
		self.assertFalse(has_real_email(" Admin@Example.COM "))
		self.assertFalse(has_real_email("  "))
		self.assertFalse(has_real_email(None))
		self.assertTrue(has_real_email(CASHIER))

	def test_the_boot_never_carries_the_api_key(self):
		frappe.set_user(CASHIER)
		bootinfo = frappe._dict()
		with chat_config():
			extend_bootinfo(bootinfo)
		self.assertIsNotNone(bootinfo.books["support_chat"])
		self.assertNotIn(API_KEY, json.dumps(bootinfo, default=str))

	def test_roles_are_sent_in_a_fixed_order(self):
		frappe.set_user(CASHIER)
		roles = ["Books Cashier", "System Manager", "Books User", "Books Manager"]
		with chat_config(), patch("frappe_books.support_chat.frappe.get_roles", return_value=roles):
			block = boot_block()
		self.assertEqual(block["attributes"]["roles"], "Books Manager, Books User, Books Cashier")

	def test_no_books_role_still_chats_without_roles(self):
		frappe.set_user(CASHIER)
		with chat_config(), patch("frappe_books.support_chat.frappe.get_roles", return_value=["Guest"]):
			block = boot_block()
		self.assertNotIn("roles", block["attributes"])

	def test_attribute_values_are_cut_to_255_characters(self):
		frappe.set_user(CASHIER)
		long_name = "C" * 300
		with chat_config(), patch.object(frappe.db, "get_single_value", return_value=long_name):
			block = boot_block()
		self.assertEqual(block["attributes"]["company"], "C" * 255)

	def test_an_empty_company_is_left_out(self):
		frappe.set_user(CASHIER)
		with chat_config(), patch.object(frappe.db, "get_single_value", return_value=None):
			block = boot_block()
		self.assertNotIn("company", block["attributes"])

	def test_a_failure_turns_the_chat_off_without_raising(self):
		frappe.set_user(CASHIER)
		with chat_config(), patch.object(frappe.db, "get_value", side_effect=RuntimeError("boom")):
			self.assertIsNone(boot_block())
