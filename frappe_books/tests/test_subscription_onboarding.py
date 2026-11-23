"""The control site's claim of a pool site and its owner's first link (spec 0014 AC-22 to AC-24)."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime, now_datetime

from frappe_books.subscription import onboarding
from frappe_books.subscription.clock import DOCTYPE, utc_now
from frappe_books.tests.subscription import TEST_SECRET, SubscriptionTestMixin, managed_site, store_facts
from frappe_books.tests.test_subscription_remote import signed_json, site_call

OWNER = "owner-claim@example.com"
HOST = "https://acme.rarebooks.cc"
CLAIM = {
	"owner_email": OWNER,
	"first_name": "Asha",
	"last_name": "Mrema",
	"company_name": "  Acme Traders  ",
	"time_zone": "Africa/Dar_es_Salaam",
}


class IntegrationTestClaimSite(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for patcher in (
			managed_site(),
			patch("frappe_books.subscription.remote.site_secret", return_value=TEST_SECRET),
		):
			patcher.__enter__()
			self.addCleanup(patcher.__exit__, None, None, None)
		frappe.cache.delete_keys("rl:")
		self._clear_owners()

	def _clear_owners(self):
		"""A pool site has no owner yet: disable the test site's other users while the test runs, then restore."""
		others = onboarding._system_users()
		zone = frappe.db.get_single_value("System Settings", "time_zone")
		frappe.db.set_value("User", {"name": ("in", others or [""])}, "enabled", 0)
		frappe.db.commit()

		def restore():
			frappe.db.rollback()
			if frappe.db.exists("User", OWNER):
				frappe.delete_doc("User", OWNER, ignore_permissions=True, force=True)
			if others:
				frappe.db.set_value("User", {"name": ("in", others)}, "enabled", 1)
			frappe.db.set_single_value("System Settings", "time_zone", zone)
			for key in (onboarding.COMPANY_DEFAULT, onboarding.OWNER_DEFAULT):
				frappe.db.set_default(key, None)
			frappe.db.commit()
			frappe.clear_cache()

		self.addCleanup(restore)

	def claim(self, **overrides):
		_body, response = site_call("claim_site", {**CLAIM, **overrides})
		frappe.db.rollback()  # the request thread committed; read its result in a new snapshot
		return response

	def test_a_claim_makes_the_owner_sets_the_zone_and_company_and_restarts_the_trial(self):
		# covers: AC-22, AC-24
		store_facts(trial_started_on=utc_now() - timedelta(days=40))
		before = utc_now()
		emails = frappe.db.count("Email Queue")

		response = self.claim()

		self.assertEqual(response.status_code, 200, response.get_data()[:300])
		self.assertEqual(signed_json(response)["status"], "claimed")
		user = frappe.get_doc("User", OWNER)
		self.assertTrue(user.enabled)
		self.assertEqual(user.user_type, "System User")
		self.assertEqual((user.first_name, user.last_name), ("Asha", "Mrema"))
		self.assertEqual(
			{row.role for row in user.roles} & {"Books Manager", "System Manager"},
			{"Books Manager", "System Manager"},
		)
		self.assertEqual(frappe.db.count("Email Queue"), emails, "no welcome email")
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), "Africa/Dar_es_Salaam")
		self.assertEqual(frappe.db.get_default(onboarding.COMPANY_DEFAULT), "Acme Traders")
		started = get_datetime(frappe.get_doc(DOCTYPE).trial_started_on)
		self.assertGreaterEqual(started, before.replace(microsecond=0))

	def test_a_claim_works_before_the_setup_wizard_with_language_and_zone_empty(self):
		# covers: AC-22 (a new Frappe Cloud pool site has no language or time zone until the setup wizard)
		language = frappe.db.get_single_value("System Settings", "language")
		self.addCleanup(
			lambda: frappe.db.set_single_value("System Settings", "language", language) or frappe.db.commit()
		)
		frappe.db.set_single_value("System Settings", {"language": None, "time_zone": None})
		frappe.db.commit()

		response = self.claim()

		self.assertEqual(response.status_code, 200, response.get_data()[:300])
		self.assertEqual(signed_json(response)["status"], "claimed")
		self.assertTrue(frappe.db.exists("User", OWNER))
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), "Africa/Dar_es_Salaam")

	def test_a_repeat_with_the_same_email_answers_claimed_and_changes_nothing(self):
		# covers: AC-22
		self.assertEqual(self.claim().status_code, 200)
		started = frappe.get_doc(DOCTYPE).trial_started_on
		response = self.claim(company_name="Other Name", time_zone="Europe/Berlin")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(signed_json(response)["status"], "claimed")
		self.assertEqual(frappe.get_doc(DOCTYPE).trial_started_on, started)
		self.assertEqual(frappe.db.get_default(onboarding.COMPANY_DEFAULT), "Acme Traders")
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), "Africa/Dar_es_Salaam")

	def test_a_claim_with_another_email_once_owned_answers_409(self):
		# covers: AC-22 (a replay can't add a second owner)
		self.assertEqual(self.claim().status_code, 200)
		response = self.claim(owner_email="someone-else@example.com")
		self.assertEqual(response.status_code, 409)
		signed_json(response)
		self.assertFalse(frappe.db.exists("User", "someone-else@example.com"))

	def test_an_unknown_zone_becomes_utc_and_bad_values_answer_400(self):
		# covers: AC-22
		self.assertEqual(self.claim(time_zone="Mars/Olympus").status_code, 200)
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), "UTC")
		for bad in (
			{"owner_email": "not-an-email"},
			{"company_name": "  "},
			{"company_name": "x" * 141},
			{"first_name": ""},
		):
			with self.subTest(bad=bad):
				self.assertEqual(
					self.claim(**{**bad, "owner_email": bad.get("owner_email", "new-" + OWNER)}).status_code,
					400,
				)

	def test_an_unsigned_claim_gets_a_signed_401(self):
		# covers: AC-22
		_body, response = site_call("claim_site", CLAIM, secret=b"not-the-secret-0123456789abcdef0123456789")
		self.assertEqual(response.status_code, 401)
		signed_json(response)
		self.assertFalse(frappe.db.exists("User", OWNER))

	def test_owner_link_waits_for_the_subdomain_then_mints_a_fresh_link_each_time(self):
		# covers: AC-23
		self.assertEqual(self.claim().status_code, 200)
		_body, response = site_call("owner_link")
		self.assertEqual(response.status_code, 409, "not before the address is primary")

		with patch("frappe_books.subscription.onboarding._primary_host", return_value=HOST):
			first = signed_json(site_call("owner_link")[1])
			second = signed_json(site_call("owner_link")[1])
		self.assertFalse(first["password_set"])
		self.assertIn("/update-password?key=", first["url"])
		self.assertNotEqual(first["url"], second["url"], "each call makes a new key")

		frappe.db.set_value("User", OWNER, "last_login", now_datetime())
		frappe.db.commit()
		with patch("frappe_books.subscription.onboarding._primary_host", return_value=HOST):
			answer = signed_json(site_call("owner_link")[1])
		self.assertEqual(answer["url"], f"{HOST}/login")
		self.assertTrue(answer["password_set"])

	def test_claim_report_shows_the_owner_and_whether_they_logged_in(self):
		# covers: AC-23 (read before a discard, AC-19)
		answer = signed_json(site_call("claim_report")[1])
		self.assertEqual((answer["owner_email"], answer["owner_logged_in"]), (None, False))
		self.claim()
		answer = signed_json(site_call("claim_report")[1])
		self.assertEqual((answer["owner_email"], answer["owner_logged_in"]), (OWNER, False))
		frappe.db.set_value("User", OWNER, "last_login", now_datetime())
		frappe.db.commit()
		self.assertTrue(signed_json(site_call("claim_report")[1])["owner_logged_in"])

	def test_the_primary_host_is_the_host_name_only_when_it_is_not_the_pool_name(self):
		# covers: AC-23
		cases = {
			None: None,
			frappe.local.site: None,
			f"https://{frappe.local.site}": None,
			"acme.rarebooks.cc": HOST,
			HOST: HOST,
		}
		for host_name, expected in cases.items():
			with self.subTest(host_name=host_name), patch.dict(frappe.local.conf, {"host_name": host_name}):
				self.assertEqual(onboarding._primary_host(), expected)
