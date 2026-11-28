import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.analytics import SETTINGS, boot_block, person_id
from frappe_books.boot import extend_bootinfo
from frappe_books.tests.subscription import make_user

SALT = "test-posthog-salt"
ANALYTICS_CONFIG = {
	"books_control_url": "https://control.books.test",
	"books_posthog_key": "phc_test_key",
	"books_posthog_salt": SALT,
}
CASHIER = "analytics-cashier@books.test"
MANAGER = "analytics-manager@books.test"
STAFF = "analytics-staff@books.test"
# HMAC SHA256 of "duka.rarebooks.cc:asha@books.test" keyed with SALT, first 32 hex characters,
# worked out once outside the app.
ASHA_ID = "d9f957b938db79e1fc183ae612d775f7"
# The plain SHA256 of the email, which the id must never be.
ASHA_EMAIL_SHA = "e08adda062555e37598c8859cc48b9a3"


def analytics_config(**overrides):
	return patch.dict(frappe.conf, {**ANALYTICS_CONFIG, **overrides})


class IntegrationTestAnalytics(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(CASHIER, "Books Cashier")
		make_user(MANAGER, "Books Manager")
		make_user(STAFF, "System Manager")

	def setUp(self):
		frappe.db.set_single_value(SETTINGS, "share_usage_analytics", 1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value(SETTINGS, "share_usage_analytics", 1)
		super().tearDown()

	def block_for(self, user, **config):
		frappe.set_user(user)
		with analytics_config(**config):
			return boot_block()

	# covers: AC-1
	def test_a_block_for_a_books_user_on_a_hosted_site(self):
		block = self.block_for(CASHIER)
		self.assertEqual(set(block), {"key", "distinct_id", "site_key", "roles", "country_code", "language"})
		self.assertEqual(block["key"], "phc_test_key")
		self.assertEqual(block["site_key"], frappe.local.site)
		self.assertEqual(block["roles"], ["Books Cashier"])
		self.assertEqual(block["distinct_id"], person_id(SALT, frappe.local.site, CASHIER))
		self.assertEqual(block["language"], frappe.local.lang)

	# covers: AC-1, AC-19
	def test_off_when_any_config_key_is_missing(self):
		for key in ANALYTICS_CONFIG:
			with self.subTest(key=key):
				self.assertIsNone(self.block_for(CASHIER, **{key: None}))

	# covers: AC-1
	def test_administrator_guest_and_staff_without_a_books_role_get_none(self):
		for user in ("Administrator", "Guest", STAFF):
			with self.subTest(user=user):
				self.assertIsNone(self.block_for(user))

	# covers: AC-10
	def test_off_when_the_shop_turned_it_off(self):
		frappe.db.set_single_value(SETTINGS, "share_usage_analytics", 0)
		self.assertIsNone(self.block_for(MANAGER))

	# covers: AC-2
	def test_the_person_id_is_a_keyed_hash_of_site_and_user(self):
		self.assertEqual(person_id(SALT, "duka.rarebooks.cc", "asha@books.test"), ASHA_ID)
		self.assertNotEqual(ASHA_ID, ASHA_EMAIL_SHA)
		self.assertEqual(
			person_id(SALT, "duka.rarebooks.cc", "asha@books.test"),
			person_id(SALT, "duka.rarebooks.cc", "asha@books.test"),
		)
		self.assertNotEqual(
			person_id(SALT, "duka.rarebooks.cc", "asha@books.test"),
			person_id(SALT, "other.rarebooks.cc", "asha@books.test"),
		)

	# covers: AC-1, AC-2
	def test_the_boot_never_carries_the_salt_or_the_email(self):
		frappe.set_user(CASHIER)
		bootinfo = frappe._dict()
		with analytics_config():
			extend_bootinfo(bootinfo)
		block = json.dumps(bootinfo.books["analytics"])
		self.assertNotIn(SALT, block)
		self.assertNotIn(CASHIER, block)

	# covers: AC-1
	def test_a_failure_turns_analytics_off_instead_of_breaking_the_boot(self):
		frappe.set_user(CASHIER)
		with analytics_config(), patch("frappe_books.analytics.regional_code", side_effect=RuntimeError):
			self.assertIsNone(boot_block())

	# covers: AC-10
	def test_saving_the_settings_drops_every_cached_boot(self):
		frappe.cache.hset("bootinfo", CASHIER, {"books": {}})
		settings = frappe.get_single(SETTINGS)
		settings.share_usage_analytics = 0
		settings.save()
		self.assertIsNone(frappe.cache.hget("bootinfo", CASHIER))
