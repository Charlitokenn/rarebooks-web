from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.subscription.clock import SubscriptionClock, is_locked, offered_plan

# 10:00 UTC on 1 January 2031 is day 1 in UTC and in Dar es Salaam (UTC+3).
STARTED = datetime(2031, 1, 1, 10, 0)


def facts(**values):
	defaults = {
		"trial_started_on": STARTED,
		"paid_until": None,
		"provider": "",
		"billing_period": "",
		"auto_renews": 0,
		"exempt": 0,
		"checkout_started_on": None,
	}
	return frappe._dict({**defaults, **values})


def on_day(day: int, hour: int = 12) -> datetime:
	return datetime(2031, 1, 1, hour) + timedelta(days=day - 1)


@contextmanager
def site_time_zone(name):
	"""get_system_settings reads frappe.local.system_settings first."""
	previous = getattr(frappe.local, "system_settings", None)
	frappe.local.system_settings = frappe._dict(time_zone=name)
	try:
		yield
	finally:
		frappe.local.system_settings = previous


def clock(now, managed=True, time_zone="UTC", **values):
	with site_time_zone(time_zone):
		return SubscriptionClock(facts(**values), managed, now)


class IntegrationTestSubscriptionClock(IntegrationTestCase):
	def test_trial_days_give_trial_prompt_and_locked(self):
		expected = {1: "trial", 21: "trial", 22: "prompt", 25: "prompt", 26: "locked", 30: "locked"}
		for day, phase in expected.items():
			with self.subTest(day=day):
				subject = clock(on_day(day))
				self.assertEqual(subject.day_number, day)
				self.assertEqual(subject.phase, phase)
				self.assertEqual(subject.locked, phase == "locked")

	def test_the_lock_starts_at_local_midnight(self):
		late_on_day_25 = on_day(25, hour=23) + timedelta(minutes=30)
		self.assertEqual(clock(late_on_day_25, time_zone="UTC").phase, "prompt")
		dar = clock(late_on_day_25, time_zone="Africa/Dar_es_Salaam")
		self.assertEqual((dar.day_number, dar.phase), (26, "locked"))

	def test_an_empty_time_zone_uses_utc_not_kolkata(self):
		# 22:00 UTC on 1 January is already 2 January in Kolkata.
		started_late = datetime(2031, 1, 1, 22, 0)
		self.assertEqual(
			clock(on_day(1, hour=23), time_zone=None, trial_started_on=started_late).day_number, 1
		)
		kolkata = clock(on_day(2, hour=23), time_zone="Asia/Kolkata", trial_started_on=started_late)
		self.assertEqual(kolkata.day_number, 2)

	def test_status_dates_follow_day_one(self):
		status = clock(on_day(23)).status()
		self.assertEqual(status["phase"], "prompt")
		self.assertEqual(status["today"], "2031-01-23")
		self.assertEqual(status["trial_ends_on"], "2031-01-21")
		self.assertEqual(status["lock_starts_on"], "2031-01-26")
		self.assertEqual(status["removal_on"], "2031-01-30")
		self.assertIsNone(status["paid_until"])

	def test_paid_lifecycle_boundaries(self):
		today = on_day(100)
		paid = lambda days, **values: clock(today, paid_until=(today + timedelta(days=days)).date(), **values)  # noqa: E731
		self.assertEqual(paid(0, auto_renews=1).phase, "active")
		self.assertEqual(paid(400, auto_renews=1).phase, "active")
		self.assertEqual(paid(15).phase, "active")
		self.assertEqual(paid(14, provider="ClickPesa").phase, "renew_soon")
		self.assertEqual(paid(0).phase, "renew_soon")
		self.assertEqual(paid(-1).phase, "grace")
		self.assertEqual(paid(-7).phase, "grace")
		lapsed = paid(-8)
		self.assertEqual((lapsed.phase, lapsed.locked), ("lapsed", True))

	def test_a_paid_site_never_returns_to_the_trial_rows(self):
		# Paid early in the trial, then lapsed long ago: still lapsed, never "trial".
		self.assertEqual(clock(on_day(5), paid_until=on_day(-30).date()).phase, "lapsed")

	def test_paid_status_has_grace_end_and_no_removal(self):
		status = clock(on_day(100), paid_until=on_day(90).date(), provider="PayPal").status()
		self.assertEqual(status["phase"], "lapsed")
		self.assertEqual(status["grace_ends_on"], on_day(97).date().isoformat())
		self.assertIsNone(status["removal_on"])
		self.assertEqual(status["provider"], "PayPal")

	def test_unmanaged_and_exempt_sites_are_never_locked(self):
		self.assertEqual(clock(on_day(40), managed=False).phase, "unmanaged")
		self.assertEqual(clock(on_day(40), exempt=1).phase, "exempt")
		self.assertFalse(clock(on_day(40), managed=False).locked)
		# Unmanaged beats exempt and paid facts: the site is simply not on the clock.
		self.assertEqual(clock(on_day(40), managed=False, exempt=1).phase, "unmanaged")

	def test_is_locked_reads_nothing_on_an_unmanaged_site(self):
		with patch("frappe.get_cached_doc") as get_cached_doc:
			self.assertFalse(is_locked())
		get_cached_doc.assert_not_called()

	def test_payment_pending_lasts_24_hours(self):
		now = on_day(27)
		self.assertTrue(clock(now, checkout_started_on=now - timedelta(hours=23)).status()["payment_pending"])
		self.assertFalse(
			clock(now, checkout_started_on=now - timedelta(hours=25)).status()["payment_pending"]
		)
		self.assertFalse(clock(now).status()["payment_pending"])

	def test_can_subscribe_only_for_system_and_books_managers(self):
		for roles, expected in (
			(["System Manager"], True),
			(["Books Manager"], True),
			(["Books User"], False),
			(["Books Cashier"], False),
		):
			with self.subTest(roles=roles), patch("frappe.get_roles", return_value=roles):
				self.assertEqual(clock(on_day(1)).status()["can_subscribe"], expected)

	def test_offered_plan_follows_the_company_country(self):
		for country, expected in (
			("Tanzania", ("ClickPesa", ["Yearly"])),
			("Kenya", ("PayPal", ["Monthly", "Yearly"])),
			(None, (None, [])),
		):
			with (
				self.subTest(country=country),
				patch("frappe_books.subscription.clock.company_country", return_value=country),
			):
				self.assertEqual(offered_plan(), expected)
