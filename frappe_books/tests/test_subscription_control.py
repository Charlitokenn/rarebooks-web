"""The control site contract (spec 0005, milestone 3): the signed push, the pull and checkout."""

import json
from datetime import timedelta

import frappe
import requests
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, getdate

from frappe_books.subscription import get_subscription, start_checkout
from frappe_books.subscription.clock import DOCTYPE, current_clock, utc_now
from frappe_books.subscription.control import parse_issued_at, sign
from frappe_books.tests.subscription import (
	CHECKOUT_URL,
	TEST_SECRET,
	ControlStub,
	SubscriptionTestMixin,
	control_site,
	iso_ago,
	lock_site,
	make_user,
	push,
	signed_push,
	store_facts,
	unlock_site,
)

BOOKS_USER = "books-user-control@example.com"
BOOKS_MANAGER = "books-manager-control@example.com"
UNREACHABLE = "Couldn't reach billing. Try again."


def a_year_out() -> str:
	return str(add_days(getdate(), 365))


def facts():
	return frappe.get_single(DOCTYPE)


class IntegrationTestReceiveState(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		lock_site()
		store_facts(last_synced_on=None)

	def test_a_signed_push_lifts_the_lock(self):
		body, signature = signed_push({"paid_until": a_year_out(), "provider": "PayPal", "auto_renews": 1})
		response = push(body, signature)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"], {"result": "applied"})
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertEqual(str(facts().paid_until), a_year_out())
		self.assertIsNotNone(facts().last_synced_on)

	def test_a_bad_signature_changes_nothing(self):
		body, _signature = signed_push({"paid_until": a_year_out()})
		for signature in (None, sign(body, b"another-secret"), "sha256=00"):
			response = push(body, signature)
			self.assertEqual(response.status_code, 401)
		self.assertIsNone(facts().paid_until)

	def test_a_push_for_another_site_changes_nothing(self):
		body = json.dumps(
			{"site": "other.example.com", "issued_at": iso_ago(seconds=1), "paid_until": a_year_out()}
		)
		response = push(body.encode(), sign(body.encode(), TEST_SECRET))
		self.assertEqual(response.status_code, 401)
		self.assertIsNone(facts().paid_until)

	def test_a_stale_or_naive_issued_at_changes_nothing(self):
		naive = utc_now().isoformat()
		for issued_at in (iso_ago(minutes=6), naive, "not a date"):
			body, signature = signed_push({"issued_at": issued_at, "paid_until": a_year_out()})
			self.assertEqual(push(body, signature).status_code, 401, issued_at)
		self.assertIsNone(facts().paid_until)

	def test_a_replayed_older_push_is_ignored(self):
		newer, newer_signature = signed_push({"issued_at": iso_ago(seconds=10), "paid_until": a_year_out()})
		older, older_signature = signed_push({"issued_at": iso_ago(seconds=60), "paid_until": None})
		self.assertEqual(push(newer, newer_signature).json["message"]["result"], "applied")
		for body, signature in ((older, older_signature), (newer, newer_signature)):
			self.assertEqual(push(body, signature).json["message"]["result"], "ignored")
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertEqual(str(facts().paid_until), a_year_out())

	def test_a_bad_value_answers_400_and_changes_nothing(self):
		for state in ({"provider": "Stripe"}, {"billing_period": "Weekly"}, {"paid_until": "soon"}):
			body, signature = signed_push({**state, "auto_renews": 1})
			self.assertEqual(push(body, signature).status_code, 400, state)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertFalse(facts().auto_renews)

	def test_unknown_keys_are_ignored(self):
		body, signature = signed_push({"paid_until": a_year_out(), "colour": "blue"})
		self.assertEqual(push(body, signature).json["message"]["result"], "applied")

	def test_a_newer_paid_until_clears_the_pending_checkout(self):
		store_facts(checkout_started_on=utc_now() - timedelta(hours=1))
		body, signature = signed_push({"paid_until": a_year_out()})
		push(body, signature)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertIsNone(facts().checkout_started_on)


class IntegrationTestPullAndCheckout(SubscriptionTestMixin, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(BOOKS_USER, "Books User")
		make_user(BOOKS_MANAGER, "Books Manager")

	def setUp(self):
		super().setUp()
		unlock_site()
		store_facts(last_synced_on=None)

	def test_the_return_refresh_pulls_fresh_state(self):
		lock_site()
		stub = ControlStub(state={"paid_until": a_year_out(), "provider": "PayPal", "auto_renews": 1})
		with control_site(stub):
			status = get_subscription(refresh=True)
		self.assertEqual(status["phase"], "active")
		self.assertFalse(status["locked"])
		self.assertEqual(stub.calls[0][0], "rarebooks_control.api.get_state")
		self.assertEqual(stub.calls[0][1]["site"], frappe.local.site)

	def test_managers_get_the_plans_for_their_country(self):
		with control_site(ControlStub(), country="Kenya"):
			status = get_subscription()
		self.assertEqual([plan["billing_period"] for plan in status["plans"]], ["Monthly", "Yearly"])
		self.assertIsNone(status["plans_error"])
		with control_site(ControlStub(), country="Tanzania"):
			status = get_subscription()
		self.assertEqual(
			[(plan["provider"], plan["billing_period"]) for plan in status["plans"]],
			[("ClickPesa", "Yearly")],
		)

	def test_plans_are_cached(self):
		stub = ControlStub()
		with control_site(stub):
			get_subscription()
			get_subscription()
		self.assertEqual(len(stub.calls), 1)

	def test_a_books_user_gets_no_plans(self):
		frappe.set_user(BOOKS_USER)
		with control_site(ControlStub()):
			status = get_subscription()
		self.assertNotIn("plans", status)

	def test_an_unreachable_control_site_gives_the_retry_state(self):
		lock_site()
		for stub in (
			ControlStub(error=requests.Timeout()),
			ControlStub(error=requests.ConnectionError()),
			ControlStub(sign_with=b"another-secret", state={"paid_until": a_year_out()}),
		):
			with control_site(stub):
				status = get_subscription(refresh=True)
			self.assertEqual(status["plans_error"], UNREACHABLE)
			self.assertEqual(status["plans"], [])
			self.assertTrue(status["locked"])

	def test_checkout_returns_the_link_and_marks_payment_pending(self):
		lock_site()
		frappe.set_user(BOOKS_MANAGER)
		stub = ControlStub()
		with control_site(stub):
			result = start_checkout("Yearly")
			status = current_clock().status()
		self.assertEqual(result, {"checkout_url": CHECKOUT_URL})
		method, body = stub.calls[0]
		self.assertEqual(method, "rarebooks_control.api.create_checkout")
		self.assertEqual((body["provider"], body["billing_period"]), ("PayPal", "Yearly"))
		self.assertTrue(body["return_url"].endswith("/books/subscription?checkout=returned"))
		self.assertTrue(status["payment_pending"])
		self.assertTrue(status["locked"])

	def test_a_books_user_cannot_start_checkout(self):
		frappe.set_user(BOOKS_USER)
		with control_site(ControlStub()):
			self.assertRaises(frappe.PermissionError, start_checkout, "Yearly")

	def test_checkout_refusals(self):
		with control_site(ControlStub(), country="Tanzania"):
			self.assertRaises(frappe.ValidationError, start_checkout, "Monthly")
		with control_site(ControlStub(), country=None):
			self.assertRaisesRegex(frappe.ValidationError, "Finish setup first", start_checkout, "Yearly")
		store_facts(paid_until=a_year_out(), auto_renews=1)
		with control_site(ControlStub()):
			self.assertRaisesRegex(frappe.ValidationError, "subscription is active", start_checkout, "Yearly")

	def test_checkout_on_an_unreachable_control_site(self):
		with control_site(ControlStub(error=requests.Timeout())):
			self.assertRaisesRegex(frappe.ValidationError, "Couldn't reach billing", start_checkout, "Yearly")
		self.assertIsNone(facts().checkout_started_on)


class UnitTestSigning(UnitTestCase):
	def test_issued_at_must_carry_a_time_zone(self):
		self.assertIsNone(parse_issued_at("2026-11-18T10:00:00"))
		self.assertEqual(str(parse_issued_at("2026-11-18T13:00:00+03:00")), "2026-11-18 10:00:00")
		self.assertIsNone(parse_issued_at(None))
