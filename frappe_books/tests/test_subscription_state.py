from datetime import date, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime, getdate

from frappe_books.patches import start_subscription_trial
from frappe_books.subscription import SiteLockedError, apply_state, refuse_when_locked, start_trial
from frappe_books.subscription.api import STAGING_CLOCK_KEY, set_trial_day
from frappe_books.subscription.clock import DOCTYPE, current_clock, is_managed, utc_now
from frappe_books.subscription.lock import UNGUARDED_DOCTYPES
from frappe_books.tests.subscription import SubscriptionTestMixin, make_user, store_facts

BOOKS_ROLES = ("System Manager", "Books Manager", "Books User", "Books Cashier")
STAGING_MANAGER = "books-staging-clock-manager@example.com"


class IntegrationTestSubscriptionState(SubscriptionTestMixin, IntegrationTestCase):
	def test_no_one_saves_the_single_outside_the_sync_paths(self):
		facts = frappe.get_single(DOCTYPE)
		facts.exempt = 1
		self.assertRaises(frappe.PermissionError, facts.save, ignore_permissions=True)
		self.assertEqual(frappe.db.get_single_value(DOCTYPE, "exempt"), 0)

	def test_every_books_role_reads_and_none_writes(self):
		for role in BOOKS_ROLES:
			with self.subTest(role=role):
				perm = frappe.get_meta(DOCTYPE).get("permissions", {"role": role})
				self.assertTrue(perm and perm[0].read)
				self.assertFalse(perm[0].write or perm[0].create or perm[0].delete)

	def test_changes_are_tracked(self):
		# Frappe skips Versions while tests run, so check the doctype keeps them.
		self.assertEqual(frappe.get_meta(DOCTYPE).track_changes, 1)

	def test_start_trial_sets_the_clock_once(self):
		frappe.db.set_single_value(DOCTYPE, "trial_started_on", None)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		start_subscription_trial.execute()
		started = frappe.db.get_single_value(DOCTYPE, "trial_started_on")
		self.assertLess(abs((utc_now() - started).total_seconds()), 60)
		with patch("frappe_books.subscription.state.utc_now", return_value=utc_now() + timedelta(days=3)):
			start_trial()
		self.assertEqual(frappe.db.get_single_value(DOCTYPE, "trial_started_on"), started)

	def test_apply_state_sets_the_paid_facts(self):
		paid_until = date.today() + timedelta(days=365)
		apply_state(
			{
				"paid_until": paid_until.isoformat(),
				"provider": "PayPal",
				"billing_period": "Yearly",
				"auto_renews": True,
				"provider_reference": "I-ABC",
				"unknown_key": "ignored",
			}
		)
		facts = frappe.get_single(DOCTYPE)
		self.assertEqual(getdate(facts.paid_until), paid_until)
		self.assertEqual((facts.provider, facts.billing_period, facts.auto_renews), ("PayPal", "Yearly", 1))
		self.assertEqual(facts.provider_reference, "I-ABC")

	def test_apply_state_refuses_a_bad_value_and_changes_nothing(self):
		# Compare with the stored facts, not blanks: a site that ran a live checkout keeps its provider.
		before = {field: frappe.db.get_single_value(DOCTYPE, field) for field in ("provider", "paid_until")}
		for state in ({"provider": "Stripe"}, {"billing_period": "Weekly"}, {"paid_until": "soon"}):
			with self.subTest(state=state):
				self.assertRaises(frappe.ValidationError, apply_state, state)
				after = {field: frappe.db.get_single_value(DOCTYPE, field) for field in before}
				self.assertEqual(after, before)

	def test_a_newer_paid_until_clears_the_pending_checkout(self):
		store_facts(paid_until=date(2031, 1, 1), checkout_started_on=utc_now())
		apply_state({"auto_renews": 1})
		self.assertTrue(frappe.get_single(DOCTYPE).checkout_started_on)
		apply_state({"paid_until": "2030-12-31"})
		self.assertTrue(frappe.get_single(DOCTYPE).checkout_started_on)
		apply_state({"paid_until": "2032-01-01"})
		self.assertIsNone(frappe.get_single(DOCTYPE).checkout_started_on)

	def test_last_synced_on_only_moves_forward(self):
		later = utc_now()
		store_facts(last_synced_on=later)
		store_facts(last_synced_on=later - timedelta(hours=1))
		self.assertEqual(get_datetime(frappe.get_single(DOCTYPE).last_synced_on), later)

	def test_managed_follows_the_control_url_in_site_config(self):
		with patch.dict(frappe.conf, {"books_control_url": "https://control.example.com"}):
			self.assertTrue(is_managed())
		with patch.dict(frappe.conf, {"books_control_url": ""}):
			self.assertFalse(is_managed())

	def test_doc_events_refuse_only_while_the_lock_flag_is_set(self):
		todo = frappe.get_doc({"doctype": "ToDo", "description": "lock flag"})
		refuse_when_locked(todo)
		frappe.flags.books_site_locked = True
		try:
			self.assertRaises(SiteLockedError, refuse_when_locked, todo)
			for doctype in UNGUARDED_DOCTYPES:
				refuse_when_locked(frappe._dict(doctype=doctype))
		finally:
			frappe.flags.books_site_locked = False

	# covers: spec 0010 build task 13 (the staging clock)
	def test_set_trial_day_makes_today_that_day_and_only_moves_the_start_earlier(self):
		store_facts(trial_started_on=utc_now(), paid_until=None, exempt=0)
		with patch.dict(
			frappe.conf, {STAGING_CLOCK_KEY: 1, "books_control_url": "https://control.example.com"}
		):
			status = set_trial_day(30)
			started = get_datetime(frappe.get_single(DOCTYPE).trial_started_on)
			self.assertEqual(current_clock().day_number, 30)
			self.assertEqual(status["removal_on"], current_clock().status()["removal_on"])
			self.assertRaises(frappe.ValidationError, set_trial_day, 5)
			self.assertRaises(frappe.ValidationError, set_trial_day, 30)
			self.assertEqual(get_datetime(frappe.get_single(DOCTYPE).trial_started_on), started)
			for day in (0, 61):
				self.assertRaises(frappe.ValidationError, set_trial_day, day)

	def test_set_trial_day_is_refused_without_the_site_flag_or_for_anyone_but_administrator(self):
		store_facts(trial_started_on=utc_now())
		started = get_datetime(frappe.get_single(DOCTYPE).trial_started_on)
		with patch.dict(frappe.conf, {STAGING_CLOCK_KEY: 0}):
			self.assertRaises(frappe.PermissionError, set_trial_day, 30)
		make_user(STAGING_MANAGER, "System Manager")
		with patch.dict(frappe.conf, {STAGING_CLOCK_KEY: 1}):
			frappe.set_user(STAGING_MANAGER)
			try:
				self.assertRaises(frappe.PermissionError, set_trial_day, 30)
			finally:
				frappe.set_user("Administrator")
		self.assertEqual(get_datetime(frappe.get_single(DOCTYPE).trial_started_on), started)
