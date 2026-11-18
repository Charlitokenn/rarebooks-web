from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import frappe
from frappe.tests import UnitTestCase

from frappe_books.subscription.clock import SubscriptionClock
from frappe_books.subscription.state import set_facts, syncing


class UnitTestSubscriptionStateRules(UnitTestCase):
	def test_invalid_flags_do_not_partially_apply_valid_fields(self):
		for field in ("exempt", "auto_renews"):
			for value in ("0", "1", "false", None, -1, 2):
				with self.subTest(field=field, value=value):
					facts = frappe._dict(provider="PayPal", checkout_started_on="2031-01-01")
					before = dict(facts)
					self.assertRaises(
						frappe.ValidationError, set_facts, facts, {"provider": "ClickPesa", field: value}
					)
					self.assertEqual(facts, before)

	def test_unknown_fields_cannot_overwrite_local_facts(self):
		facts = frappe._dict(paid_until=date(2031, 1, 31), exempt=1, provider="PayPal")
		before = dict(facts)
		set_facts(facts, {"trial_started_on": "2000-01-01", "last_synced_on": "2099-01-01"})
		self.assertEqual(facts, before)
		set_facts(facts, {})
		self.assertEqual(facts, before)

	def test_only_a_strictly_newer_paid_date_clears_pending_checkout(self):
		for old, new, clears in (
			(None, "2031-01-31", True),
			("2031-01-31", "2031-02-01", True),
			("2031-01-31", "2031-01-31", False),
			("2031-01-31", "2031-01-30", False),
			("2031-01-31", None, False),
		):
			with self.subTest(old=old, new=new):
				pending = datetime(2031, 1, 1)
				facts = frappe._dict(paid_until=old, checkout_started_on=pending)
				set_facts(facts, {"paid_until": new})
				self.assertEqual(facts.checkout_started_on, None if clears else pending)
				self.assertEqual(facts.paid_until, date.fromisoformat(new) if new else None)

	def test_explicit_empty_values_clear_optional_provider_details(self):
		facts = frappe._dict(provider="PayPal", billing_period="Yearly", provider_reference="I-123")
		set_facts(facts, {"provider": None, "billing_period": "", "provider_reference": ""})
		self.assertEqual((facts.provider, facts.billing_period, facts.provider_reference), ("", "", None))

	def test_sync_guard_is_cleared_when_saving_raises(self):
		with patch.dict(frappe.flags, {"books_subscription_sync": False}):
			with self.assertRaisesRegex(RuntimeError, "save failed"), syncing():
				self.assertTrue(frappe.flags.books_subscription_sync)
				raise RuntimeError("save failed")
			self.assertFalse(frappe.flags.books_subscription_sync)


class UnitTestSubscriptionClockBoundaries(UnitTestCase):
	def clock(self, now, **values):
		facts = frappe._dict(
			trial_started_on=datetime(2031, 1, 1),
			paid_until=None,
			provider="",
			billing_period="",
			auto_renews=0,
			exempt=0,
			checkout_started_on=None,
		)
		facts.update(values)
		with patch("frappe_books.subscription.clock.site_zone", return_value=ZoneInfo("UTC")):
			return SubscriptionClock(facts, True, now)

	def test_pending_payment_expires_after_24_hours_without_lifting_lock(self):
		now = datetime(2031, 2, 1)
		for age, pending in (
			(timedelta(hours=24) - timedelta(microseconds=1), True),
			(timedelta(hours=24), True),
			(timedelta(hours=24, microseconds=1), False),
		):
			with (
				self.subTest(age=age),
				patch("frappe_books.subscription.clock.offered_plan", return_value=(None, [])),
				patch("frappe_books.subscription.clock.can_subscribe", return_value=False),
			):
				status = self.clock(now, checkout_started_on=now - age).status()
				self.assertEqual(status["payment_pending"], pending)
				self.assertTrue(status["locked"])

	def test_auto_renew_does_not_extend_access_past_the_grace_period(self):
		for days, phase in ((0, "active"), (1, "grace"), (7, "grace"), (8, "lapsed")):
			with self.subTest(days=days):
				clock = self.clock(
					datetime(2031, 2, 1) + timedelta(days=days),
					paid_until="2031-02-01",
					auto_renews=1,
				)
				self.assertEqual(clock.phase, phase)
				self.assertEqual(clock.locked, phase == "lapsed")

	def test_exemption_takes_precedence_over_lapsed_paid_access(self):
		clock = self.clock(datetime(2031, 2, 1), paid_until="2031-01-01", exempt=1)
		self.assertEqual(clock.phase, "exempt")
		self.assertFalse(clock.locked)
