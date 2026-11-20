from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.boot import extend_bootinfo
from frappe_books.subscription import get_subscription
from frappe_books.subscription.clock import utc_now
from frappe_books.tests.subscription import (
	SubscriptionTestMixin,
	call,
	lock_site,
	login_sid,
	make_user,
	managed_site,
	store_facts,
	unlock_site,
)

BOOKS_USER = "books-user-status@example.com"


class IntegrationTestSubscriptionStatus(SubscriptionTestMixin, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(BOOKS_USER, "Books User")

	def test_boot_carries_the_status_dict(self):
		store_facts(trial_started_on=utc_now() - timedelta(days=22), paid_until=None, exempt=0)
		bootinfo = frappe._dict()
		with managed_site():
			extend_bootinfo(bootinfo)
		status = bootinfo.books["subscription"]
		self.assertEqual(status["phase"], "prompt")
		self.assertEqual(status["day_number"], 23)
		self.assertFalse(status["locked"])

	def test_an_unmanaged_site_boots_as_unmanaged(self):
		bootinfo = frappe._dict()
		with managed_site(False):
			extend_bootinfo(bootinfo)
		self.assertEqual(bootinfo.books["subscription"]["phase"], "unmanaged")

	def test_every_books_role_reads_the_status(self):
		unlock_site()
		frappe.set_user(BOOKS_USER)
		with managed_site():
			status = get_subscription()
		self.assertEqual(status["phase"], "trial")
		self.assertFalse(status["can_subscribe"])

	def test_a_user_without_read_is_refused(self):
		frappe.set_user("Guest")
		with managed_site():
			self.assertRaises(frappe.PermissionError, get_subscription)

	def test_a_locked_site_still_answers_the_status(self):
		lock_site()
		sid = login_sid(BOOKS_USER)
		with managed_site():
			response = call("get", "/api/method/frappe_books.subscription.get_subscription", sid)
		self.assertEqual(response.status_code, 200, response.json)
		self.assertEqual(response.json["message"]["phase"], "locked")
		self.assertTrue(response.json["message"]["locked"])
