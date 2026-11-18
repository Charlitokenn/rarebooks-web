"""The control site contract (spec 0005, milestone 3): the signed push, the pull and checkout."""

import json
import time
from contextlib import contextmanager
from datetime import timedelta
from threading import Event, Thread
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, get_datetime, getdate

from frappe_books.subscription import get_subscription, start_checkout
from frappe_books.subscription.api import LAST_PULL_KEY, _claim_pull_window
from frappe_books.subscription.clock import DOCTYPE, current_clock, utc_now
from frappe_books.subscription.control import parse_issued_at, sign
from frappe_books.subscription.state import mark_checkout_started, set_facts
from frappe_books.tests.subscription import (
	CHECKOUT_URL,
	TEST_SECRET,
	ControlStub,
	SubscriptionTestMixin,
	control_site,
	error_log_count,
	iso_ago,
	lock_site,
	make_user,
	post_push,
	push,
	push_together,
	push_url,
	pushing,
	reset_last_synced,
	signed_push,
	store_facts,
	unlock_site,
)

BOOKS_USER = "books-user-control@example.com"
BOOKS_MANAGER = "books-manager-control@example.com"
UNREACHABLE = "Couldn't reach billing. Try again."
RATE_LIMIT_KEY = "rl:frappe_books.subscription.api.receive_state:*"
BAD_PUSH_LOG = "Books billing: receive_state refused a bad value"
BAD_PULL_LOG = "Books billing: get_state sent a bad value"
BAD_LINK_LOG = "Books billing: create_checkout sent a link that isn't https"


def a_year_out() -> str:
	return str(add_days(getdate(), 365))


def facts():
	return frappe.get_single(DOCTYPE)


class IntegrationTestReceiveState(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		lock_site()
		reset_last_synced()

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
		# Starts from auto_renews off, whatever the test site was left with (spec 0007 AC-8).
		store_facts(auto_renews=0)
		for state in ({"provider": "Stripe"}, {"billing_period": "Weekly"}, {"paid_until": "soon"}):
			body, signature = signed_push({**state, "auto_renews": 1})
			self.assertEqual(push(body, signature).status_code, 400, state)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertFalse(facts().auto_renews)

	def test_a_bad_value_is_logged_once_without_the_secret(self):
		# covers: AC-11 (one "refused a bad value" Error Log row per refused push)
		title = "Books billing: receive_state refused a bad value"
		frappe.deferred_insert.save_to_db()  # rows queued by earlier pushes
		before = frappe.db.count("Error Log", {"method": title})
		body, signature = signed_push({"provider": "Stripe"})
		self.assertEqual(push(body, signature).status_code, 400)
		frappe.deferred_insert.save_to_db()
		rows = frappe.get_all("Error Log", {"method": title}, ["error"], order_by="creation desc")
		self.assertEqual(len(rows), before + 1)
		self.assertNotIn(TEST_SECRET.decode(), rows[0].error)

	def test_the_61st_push_in_a_minute_is_rate_limited(self):
		# covers: AC-11 (receive_state allows 60 calls a minute per address)
		frappe.cache.delete_keys(RATE_LIMIT_KEY)
		self.addCleanup(frappe.cache.delete_keys, RATE_LIMIT_KEY)
		codes = [push(b"{}", None).status_code for _ in range(61)]
		self.assertEqual(set(codes[:60]), {401})
		self.assertEqual(codes[60], 429)

	def test_an_applied_push_clears_the_last_pull_result(self):
		# covers: AC-12. A Retry from before the push must not hide the new state for 10 seconds.
		frappe.cache.set_value(LAST_PULL_KEY, UNREACHABLE, expires_in_sec=10)
		body, signature = signed_push({"paid_until": a_year_out()})
		self.assertEqual(push(body, signature).json["message"]["result"], "applied")
		self.assertIsNone(frappe.cache.get_value(LAST_PULL_KEY, use_local_cache=False))

	def test_unknown_keys_are_ignored(self):
		body, signature = signed_push({"paid_until": a_year_out(), "colour": "blue"})
		self.assertEqual(push(body, signature).json["message"]["result"], "applied")

	def test_a_newer_paid_until_clears_the_pending_checkout(self):
		store_facts(checkout_started_on=utc_now() - timedelta(hours=1))
		body, signature = signed_push({"paid_until": a_year_out()})
		push(body, signature)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertIsNone(facts().checkout_started_on)


@contextmanager
def slow_apply(seconds=0.5):
	"""Make each apply sleep inside the row lock, so pushes that arrive together truly overlap.

	Yields the (started, finished, entered) record: two lists of times and an Event set on the first entry.
	"""
	record = ([], [], Event())

	def slow(facts, state):
		record[0].append(time.monotonic())
		record[2].set()
		time.sleep(seconds)
		set_facts(facts, state)
		record[1].append(time.monotonic())

	with patch("frappe_books.subscription.state.set_facts", side_effect=slow):
		yield record


class IntegrationTestPushHardening(SubscriptionTestMixin, IntegrationTestCase):
	"""Spec 0007: pushes, pulls and checkout serialized by the row lock, and the 400 or 500 split."""

	def setUp(self):
		super().setUp()
		lock_site()
		reset_last_synced()
		frappe.cache.delete_keys(RATE_LIMIT_KEY)

	def test_two_pushes_at_once_both_answer_and_the_newer_wins(self):
		# covers: AC-1
		bad_values = error_log_count(BAD_PUSH_LOG)
		older = signed_push({"issued_at": iso_ago(seconds=30), "paid_until": str(add_days(getdate(), 100))})
		newer = signed_push({"issued_at": iso_ago(seconds=10), "paid_until": a_year_out()})
		with slow_apply() as (started, finished, _entered):
			responses = push_together(older, newer)
		for response in responses:
			self.assertEqual(response.status_code, 200, response.json)
			self.assertIn(response.json["message"]["result"], ("applied", "ignored"))
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertEqual(str(facts().paid_until), a_year_out())
		self.assertEqual(
			get_datetime(facts().last_synced_on), parse_issued_at(json.loads(newer[0])["issued_at"])
		)
		# The second apply began only once the first had finished and committed.
		if len(started) == 2:
			self.assertGreaterEqual(started[1], finished[0])
		self.assertEqual(error_log_count(BAD_PUSH_LOG), bad_values)

	def test_two_pushes_at_once_in_the_other_order_still_keep_the_newer(self):
		# covers: AC-1. Whichever push takes the row lock first, the older one can't overwrite the newer.
		bad_values = error_log_count(BAD_PUSH_LOG)
		newer = signed_push({"issued_at": iso_ago(seconds=10), "paid_until": a_year_out()})
		older = signed_push({"issued_at": iso_ago(seconds=30), "paid_until": str(add_days(getdate(), 100))})
		with slow_apply():
			responses = push_together(newer, older)
		results = sorted(response.json["message"]["result"] for response in responses)
		for response in responses:
			self.assertEqual(response.status_code, 200, response.json)
		self.assertIn(results, (["applied", "applied"], ["applied", "ignored"]))
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertEqual(str(facts().paid_until), a_year_out())
		self.assertEqual(
			get_datetime(facts().last_synced_on), parse_issued_at(json.loads(newer[0])["issued_at"])
		)
		self.assertEqual(error_log_count(BAD_PUSH_LOG), bad_values)

	def test_a_bad_value_still_answers_400_and_logs_once(self):
		# covers: AC-2
		before = error_log_count(BAD_PUSH_LOG)
		body, signature = signed_push({"provider": "Stripe", "auto_renews": 1})
		self.assertEqual(push(body, signature).status_code, 400)
		self.assertEqual(error_log_count(BAD_PUSH_LOG), before + 1)

	def test_any_other_push_failure_is_a_500_that_changes_nothing(self):
		# covers: AC-2. The control site retries a 500, so it must not be dropped as a bad value.
		before = error_log_count(BAD_PUSH_LOG)
		body, signature = signed_push({"paid_until": a_year_out(), "auto_renews": 1})
		with patch(
			"frappe_books.subscription.state.save_facts", side_effect=frappe.QueryDeadlockError("deadlock")
		):
			response = push(body, signature)
		self.assertEqual(response.status_code, 500)
		self.assertEqual(error_log_count(BAD_PUSH_LOG), before)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertIsNone(facts().paid_until)
		self.assertIsNone(facts().last_synced_on)

	def test_any_other_pull_failure_is_not_logged_as_a_bad_value(self):
		# covers: AC-2
		before = error_log_count(BAD_PULL_LOG)
		with (
			control_site(ControlStub(state={"paid_until": a_year_out()})),
			patch(
				"frappe_books.subscription.state.save_facts",
				side_effect=frappe.QueryDeadlockError("deadlock"),
			),
		):
			self.assertRaises(frappe.QueryDeadlockError, get_subscription, refresh=True)
		frappe.db.rollback()
		self.assertEqual(error_log_count(BAD_PULL_LOG), before)

	def test_a_bad_pulled_value_logs_and_gives_the_retry_state(self):
		# covers: AC-2
		before = error_log_count(BAD_PULL_LOG)
		with control_site(ControlStub(state={"provider": "Stripe"})):
			status = get_subscription(refresh=True)
		self.assertEqual(status["plans_error"], UNREACHABLE)
		self.assertEqual(error_log_count(BAD_PULL_LOG), before + 1)

	def test_a_checkout_during_a_push_waits_and_both_save(self):
		# covers: AC-3
		body, signature = signed_push({"paid_until": a_year_out()})
		responses = []
		with slow_apply() as (_started, _finished, entered), pushing():
			url = push_url()
			thread = Thread(target=lambda: responses.append(post_push(url, body, signature)))
			thread.start()
			self.assertTrue(entered.wait(10))
			# The push holds the row lock now: this waits for its commit, then saves on top of it.
			mark_checkout_started()
			frappe.db.commit()
			thread.join()
		self.assertEqual(responses[0].status_code, 200, responses[0].json)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		self.assertEqual(str(facts().paid_until), a_year_out())
		self.assertIsNotNone(facts().checkout_started_on)


class IntegrationTestPullAndCheckout(SubscriptionTestMixin, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(BOOKS_USER, "Books User")
		make_user(BOOKS_MANAGER, "Books Manager")

	def setUp(self):
		super().setUp()
		unlock_site()
		reset_last_synced()

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

	def test_a_stale_or_future_pull_response_changes_nothing(self):
		# covers: AC-11, AC-12. The pull keeps the push's 5 minute issued_at window.
		lock_site()
		for issued_at in (iso_ago(minutes=10), iso_ago(minutes=-30)):
			with self.subTest(issued_at=issued_at):
				reset_last_synced(utc_now() - timedelta(days=1))
				stub = ControlStub(state={"issued_at": issued_at, "paid_until": a_year_out()})
				with control_site(stub):
					status = get_subscription(refresh=True)
				self.assertEqual(status["plans_error"], UNREACHABLE)
				self.assertTrue(status["locked"])
				frappe.clear_document_cache(DOCTYPE, DOCTYPE)
				self.assertIsNone(facts().paid_until)

	def test_only_a_subscriber_can_ask_for_a_pull(self):
		frappe.set_user(BOOKS_USER)
		stub = ControlStub(state={"paid_until": a_year_out()})
		with control_site(stub):
			get_subscription(refresh=True)
		self.assertEqual(stub.calls, [])

	def test_repeated_refreshes_pull_at_most_once_in_a_short_interval(self):
		# A loop of refreshes, or of page opens while billing is down, must not tie up workers.
		lock_site()
		for stub in (ControlStub(), ControlStub(error=requests.Timeout())):
			with self.subTest(error=stub.error), control_site(stub):
				first = get_subscription(refresh=True)
				for _ in range(3):
					again = get_subscription(refresh=True)
				self.assertEqual(len(stub.calls), 1)
				self.assertEqual(again["plans_error"], first["plans_error"])

	def test_a_pull_already_running_elsewhere_is_not_repeated(self):
		# covers: AC-16. Another worker holds the window while its pull waits: this call shows Retry, no call.
		lock_site()
		stub = ControlStub(state={"paid_until": a_year_out()})
		with control_site(stub):
			self.assertTrue(_claim_pull_window())
			self.assertFalse(_claim_pull_window())
			status = get_subscription(refresh=True)
		self.assertEqual(stub.calls, [])
		self.assertEqual(status["plans_error"], UNREACHABLE)
		self.assertTrue(status["locked"])

	def test_a_status_only_call_never_pulls(self):
		# covers: spec 0007 AC-7, for every role that can read the status and whatever `refresh` says
		lock_site()
		for user in (BOOKS_MANAGER, BOOKS_USER, "Administrator"):
			with self.subTest(user=user):
				frappe.set_user(user)
				stub = ControlStub(state={"paid_until": a_year_out()})
				with control_site(stub):
					status = get_subscription(refresh=True, with_plans=False)
				self.assertEqual(stub.calls, [])
				self.assertNotIn("plans", status)
				self.assertNotIn("plans_error", status)
				self.assertTrue(status["locked"])

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

	def test_a_plain_http_control_url_is_never_called_outside_developer_mode(self):
		# covers: the security model (only https carries the secret)
		lock_site()
		stub = ControlStub(state={"paid_until": a_year_out()})
		with (
			control_site(stub),
			patch.dict(frappe.conf, {"books_control_url": "http://control.example.com", "developer_mode": 0}),
		):
			status = get_subscription(refresh=True)
		self.assertEqual(stub.calls, [])
		self.assertEqual(status["plans_error"], UNREACHABLE)
		self.assertTrue(status["locked"])

	def test_the_status_never_carries_the_secret_or_the_control_url(self):
		# covers: AC-17 (every Books role reads the status), security model
		with control_site(ControlStub()):
			status = json.dumps(get_subscription(refresh=True), default=str)
		self.assertNotIn(TEST_SECRET.decode(), status)
		self.assertNotIn("control.example.com", status)

	def test_a_checkout_link_must_be_https_outside_developer_mode(self):
		# covers: AC-3
		lock_site()
		frappe.set_user(BOOKS_MANAGER)
		for link in ("http://pay.example.com/checkout/abc", "javascript:alert(1)", "pay.example.com"):
			with self.subTest(link=link):
				before = error_log_count(BAD_LINK_LOG)
				with (
					control_site(ControlStub(checkout_url=link)),
					patch.dict(frappe.conf, {"developer_mode": 0}),
				):
					self.assertRaisesRegex(frappe.ValidationError, UNREACHABLE, start_checkout, "Yearly")
				self.assertEqual(error_log_count(BAD_LINK_LOG), before + 1)
				self.assertIsNone(facts().checkout_started_on)

	def test_developer_mode_accepts_a_plain_http_checkout_link(self):
		# covers: AC-3, as `control_url` already allows
		lock_site()
		frappe.set_user(BOOKS_MANAGER)
		link = "http://pay.example.com/checkout/abc"
		with control_site(ControlStub(checkout_url=link)), patch.dict(frappe.conf, {"developer_mode": 1}):
			self.assertEqual(start_checkout("Yearly"), {"checkout_url": link})

	def test_checkout_on_an_unreachable_control_site(self):
		frappe.clear_messages()
		with control_site(ControlStub(error=requests.Timeout())):
			self.assertRaisesRegex(frappe.ValidationError, "Couldn't reach billing", start_checkout, "Yearly")
		self.assertIsNone(facts().checkout_started_on)
		# Thrown, not raised, so /books shows the message instead of a generic server error.
		self.assertIn("Couldn't reach billing", str(frappe.get_message_log()))


class UnitTestSigning(UnitTestCase):
	def test_issued_at_must_carry_a_time_zone(self):
		self.assertIsNone(parse_issued_at("2026-11-18T10:00:00"))
		self.assertEqual(str(parse_issued_at("2026-11-18T13:00:00+03:00")), "2026-11-18 10:00:00")
		self.assertIsNone(parse_issued_at(None))
