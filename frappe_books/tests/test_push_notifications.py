"""Push notifications through Firebase Cloud Messaging (spec 0026)."""

import hashlib
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import frappe
import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, formatdate, now_datetime

from frappe_books import notifications
from frappe_books.boot import extend_bootinfo
from frappe_books.notifications import devices, events, fcm, sending
from frappe_books.tests.accounting import (
	ensure_user,
	make_account,
	make_invoice,
	make_item,
	make_party,
	unique_name,
)
from frappe_books.tests.push import TEST_SERVICE_ACCOUNT, TEST_VAPID_KEY, TEST_WEB_CONFIG, test_push_config

DEVICE = "Books Push Device"
SETTINGS = "Books Notification Settings"
MANAGER = "push-manager@books.test"
OTHER_MANAGER = "push-manager-two@books.test"
CASHIER = "push-cashier@books.test"
BOOKS_USER = "push-user@books.test"


def push_on(service_account=None):
	return patch.dict(frappe.conf, test_push_config(service_account))


def rsa_pem():
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	return key.private_bytes(
		serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
	).decode()


def push_off():
	"""No Firebase keys, whatever the site config holds."""
	return patch.dict(frappe.conf, dict.fromkeys(fcm.CONFIG_KEYS))


def add_device(user, token=None, last_seen=None):
	token = token or unique_name("token")
	return frappe.get_doc(
		{
			"doctype": DEVICE,
			"user": user,
			"token": token,
			"token_hash": devices.hash_token(token),
			"device_label": "Chrome on Android",
			"last_seen": last_seen or now_datetime(),
		}
	).insert(ignore_permissions=True)


def response(status, body=None):
	answer = MagicMock(status_code=status)
	answer.json.return_value = body if body is not None else {}
	return answer


def fcm_error(status, state, error_code=None, field=None):
	details = []
	if error_code:
		details.append(
			{"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": error_code}
		)
	if field:
		details.append(
			{"@type": "type.googleapis.com/google.rpc.BadRequest", "fieldViolations": [{"field": field}]}
		)
	return response(status, {"error": {"code": status, "status": state, "details": details}})


class QueuedPushes:
	"""Captures `send_job`'s queued messages instead of queueing them."""

	def __init__(self):
		self.calls = []

	def __call__(self, method, **kwargs):
		self.calls.append((method, kwargs))

	@property
	def messages(self):
		return [message for _method, kwargs in self.calls for message in kwargs["messages"]]

	def by_user(self):
		users = dict(frappe.get_all(DEVICE, fields=["name", "user"], as_list=True))
		return sorted(users.get(message["device"]) for message in self.messages)


def queued_pushes():
	queue = QueuedPushes()
	return queue, patch.object(sending.frappe, "enqueue", queue)


class UnitTestFcm(IntegrationTestCase):
	def setUp(self):
		frappe.cache.delete_value(fcm.TOKEN_CACHE_KEY)

	def test_off_unless_all_three_keys_are_set(self):  # covers: AC-1
		config = test_push_config()
		for key in fcm.CONFIG_KEYS:
			with patch.dict(frappe.conf, {**config, key: ""}):
				self.assertFalse(fcm.is_configured())
		with push_on():
			self.assertTrue(fcm.is_configured())

	def test_access_token_is_a_signed_exchange_and_cached(self):  # covers: AC-10
		private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		pem = private_key.private_bytes(
			serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
		).decode()
		account = {**TEST_SERVICE_ACCOUNT, "private_key": pem}
		with push_on(account), patch.object(fcm.requests, "post") as post:
			post.return_value = response(200, {"access_token": "ya29.test", "expires_in": 3599})
			self.assertEqual(fcm.access_token(), "ya29.test")
			self.assertEqual(fcm.access_token(), "ya29.test")

		self.assertEqual(post.call_count, 1)
		(_url,) = post.call_args.args
		self.assertEqual(_url, fcm.TOKEN_URL)
		claims = jwt.decode(
			post.call_args.kwargs["data"]["assertion"],
			private_key.public_key(),
			algorithms=["RS256"],
			audience=fcm.TOKEN_URL,
		)
		self.assertEqual((claims["iss"], claims["scope"]), (account["client_email"], fcm.SCOPE))
		self.assertEqual(claims["exp"] - claims["iat"], 3600)

	def test_send_is_a_data_message_with_a_ten_second_limit(self):  # covers: AC-10, AC-11
		with push_on(), patch.object(fcm, "access_token", return_value="ya29.test"):
			with patch.object(fcm.requests, "post", return_value=response(200, {"name": "m/1"})) as post:
				outcome = fcm.send(
					"tok", "Payment received", "Asha paid TZS 5,000", "/books/edit/Payment/P1", "payment:P1"
				)

		self.assertEqual(outcome, fcm.SENT)
		self.assertEqual(post.call_args.args[0], fcm.SEND_URL.format(project_id="books-push-test"))
		self.assertEqual(post.call_args.kwargs["timeout"], 10)
		message = post.call_args.kwargs["json"]["message"]
		self.assertEqual(message["token"], "tok")
		self.assertEqual(message["data"]["link"], "/books/edit/Payment/P1")
		self.assertNotIn("notification", message)
		self.assertEqual(message["webpush"]["headers"], {"Urgency": "high", "TTL": "86400"})

	def test_a_refused_token_exchange_is_an_error_with_only_its_code(self):  # covers: AC-10, AC-12
		account = {**TEST_SERVICE_ACCOUNT, "private_key": rsa_pem()}
		refused = response(400, {"error": "invalid_grant"})
		with push_on(account), patch.object(fcm.requests, "post", return_value=refused):
			with self.assertRaises(fcm.FcmError) as raised:
				fcm.access_token()
		self.assertEqual((raised.exception.status, raised.exception.code), (400, "invalid_grant"))
		self.assertNotIn("PRIVATE KEY", str(raised.exception))
		self.assertIsNone(frappe.cache.get_value(fcm.TOKEN_CACHE_KEY))

	def test_an_unreadable_private_key_fails_the_job_once_without_raising(self):  # covers: AC-10, AC-12
		# A key that is present but can't be parsed must fail like any other bad key: one tidy Error Log, no crash.
		frappe.db.delete("Error Log")
		device = add_device(ensure_user(MANAGER, "Books Manager"))
		messages = [{"device": device.name, "title": "t", "body": "b", "link": "/books/", "tag": "x"}]
		with push_on(), patch.object(fcm.requests, "post") as post:
			sending.send_job(messages)
		post.assert_not_called()
		logs = frappe.get_all("Error Log", fields=["method", "error"])
		self.assertEqual(len(logs), 1)
		self.assertNotIn("PRIVATE KEY", json.dumps(logs))

	def test_a_token_exchange_that_times_out_is_an_error(self):  # covers: AC-10
		account = {**TEST_SERVICE_ACCOUNT, "private_key": rsa_pem()}
		with push_on(account), patch.object(fcm.requests, "post", side_effect=requests.Timeout):
			with self.assertRaises(fcm.FcmError) as raised:
				fcm.access_token()
		self.assertEqual((raised.exception.status, raised.exception.code), (None, "timeout"))

	def test_an_answer_without_a_token_is_an_error_and_caches_nothing(self):  # covers: AC-10
		account = {**TEST_SERVICE_ACCOUNT, "private_key": rsa_pem()}
		with (
			push_on(account),
			patch.object(fcm.requests, "post", return_value=response(200, {"expires_in": 3599})),
		):
			with self.assertRaises(fcm.FcmError) as raised:
				fcm.access_token()
		self.assertEqual(raised.exception.code, "no_access_token")
		self.assertIsNone(frappe.cache.get_value(fcm.TOKEN_CACHE_KEY))

	def test_an_odd_expiry_from_google_still_caches_the_token_for_an_hour(self):  # covers: AC-10
		account = {**TEST_SERVICE_ACCOUNT, "private_key": rsa_pem()}
		answer = response(200, {"access_token": "ya29.odd", "expires_in": "soon"})
		with push_on(account), patch.object(fcm.requests, "post", return_value=answer):
			self.assertEqual(fcm.access_token(), "ya29.odd")
		self.assertEqual(frappe.cache.get_value(fcm.TOKEN_CACHE_KEY), "ya29.odd")

	def test_a_broken_service_account_fails_the_send_without_raising(self):  # covers: AC-10
		with patch.dict(frappe.conf, {**test_push_config(), "books_fcm_service_account": "{}"}):
			with patch.object(fcm.requests, "post") as post:
				outcome = fcm.send("tok", "t", "b", "/books/", "x")
		self.assertEqual((outcome, outcome.code), (fcm.FAILED, "bad_service_account"))
		post.assert_not_called()

	def test_outcomes_follow_fcm_errors(self):  # covers: AC-10
		cases = [
			(fcm_error(404, "NOT_FOUND", "UNREGISTERED"), fcm.DEAD),
			(fcm_error(400, "INVALID_ARGUMENT", field="message.token"), fcm.DEAD),
			(fcm_error(400, "INVALID_ARGUMENT", field="message.data"), fcm.FAILED),
			(fcm_error(403, "PERMISSION_DENIED", "SENDER_ID_MISMATCH"), fcm.FAILED),
			(fcm_error(429, "RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"), fcm.FAILED),
			(response(503), fcm.FAILED),
		]
		with push_on(), patch.object(fcm, "access_token", return_value="ya29.test"):
			for answer, expected in cases:
				with patch.object(fcm.requests, "post", return_value=answer):
					self.assertEqual(fcm.send("tok", "t", "b", "/books/", "x"), expected)
			with patch.object(fcm.requests, "post", side_effect=requests.Timeout):
				outcome = fcm.send("tok", "t", "b", "/books/", "x")
		self.assertEqual((outcome, outcome.code), (fcm.FAILED, "timeout"))


class IntegrationTestPushDevices(IntegrationTestCase):
	def setUp(self):
		for user in (MANAGER, OTHER_MANAGER):
			ensure_user(user, "Books Manager")
		ensure_user(BOOKS_USER, "Books User")
		frappe.db.delete(DEVICE)

	def register(self, user, token, **kwargs):
		with self.set_user(user):
			return devices.register_device(token, **kwargs)

	def test_register_stores_one_row_per_token(self):  # covers: AC-3
		with push_on():
			name = self.register(MANAGER, "token-a", device_label="Chrome on Android")["name"]
			self.register(MANAGER, "token-a", device_label="Chrome on Android")

		row = frappe.get_doc(DEVICE, name)
		self.assertEqual((row.user, row.token, row.device_label), (MANAGER, "token-a", "Chrome on Android"))
		self.assertEqual(row.token_hash, devices.hash_token("token-a"))
		self.assertEqual(frappe.db.count(DEVICE), 1)

	def test_a_token_moves_to_the_user_who_registers_it(self):  # covers: AC-3
		with push_on():
			name = self.register(MANAGER, "shared")["name"]
			self.assertEqual(self.register(OTHER_MANAGER, "shared")["name"], name)

		self.assertEqual(frappe.db.get_value(DEVICE, name, "user"), OTHER_MANAGER)

	def test_a_rotated_token_replaces_the_old_row(self):  # covers: AC-3
		with push_on():
			self.register(MANAGER, "old")
			self.register(MANAGER, "new", previous_token="old")

		self.assertEqual(frappe.get_all(DEVICE, pluck="token"), ["new"])

	def test_a_register_within_the_hour_writes_nothing(self):  # covers: AC-3
		with push_on():
			name = self.register(MANAGER, "token-a")["name"]
			seen = add_to_date(now_datetime(), minutes=-30)
			frappe.db.set_value(DEVICE, name, "last_seen", seen)
			self.register(MANAGER, "token-a")
			self.assertEqual(frappe.db.get_value(DEVICE, name, "last_seen"), seen)

			frappe.db.set_value(DEVICE, name, "last_seen", add_to_date(now_datetime(), hours=-2))
			self.register(MANAGER, "token-a")
		self.assertGreater(frappe.db.get_value(DEVICE, name, "last_seen"), seen)

	def test_an_eleventh_device_replaces_the_oldest(self):  # covers: AC-3
		oldest = add_device(MANAGER, "oldest", last_seen=add_to_date(now_datetime(), days=-5))
		for index in range(9):
			add_device(MANAGER, f"d{index}", last_seen=add_to_date(now_datetime(), days=-1))
		with push_on():
			self.register(MANAGER, "eleventh")

		self.assertEqual(frappe.db.count(DEVICE, {"user": MANAGER}), 10)
		self.assertFalse(frappe.db.exists(DEVICE, oldest.name))

	def test_off_without_keys(self):  # covers: AC-1
		with push_off(), self.assertRaises(frappe.PermissionError):
			self.register(MANAGER, "token-a")
		with push_off(), self.set_user(MANAGER), self.assertRaises(frappe.PermissionError):
			devices.unregister_device("token-a")

	def test_a_placeholder_email_may_not_register(self):  # covers: AC-2
		user = ensure_user("push-placeholder@example.com", "Books Manager")
		with push_on(), self.assertRaises(frappe.PermissionError):
			self.register(user, "token-a")
		with push_on(), self.assertRaises(frappe.PermissionError):
			self.register("Administrator", "token-a")

	def test_unregister_deletes_only_your_own_row(self):  # covers: AC-3, AC-4
		theirs = add_device(MANAGER, "theirs")
		mine = add_device(BOOKS_USER, "mine")
		with push_on(), self.set_user(BOOKS_USER):
			self.assertEqual(devices.unregister_device("theirs"), {"deleted": False})
			self.assertEqual(devices.unregister_device("mine"), {"deleted": True})

		self.assertTrue(frappe.db.exists(DEVICE, theirs.name))
		self.assertFalse(frappe.db.exists(DEVICE, mine.name))

	def test_a_user_reads_only_their_own_rows(self):  # covers: AC-3
		add_device(MANAGER, "theirs")
		mine = add_device(BOOKS_USER, "mine")
		with self.set_user(BOOKS_USER):
			self.assertEqual(frappe.get_list(DEVICE, pluck="name"), [mine.name])
		with self.set_user(OTHER_MANAGER):
			self.assertEqual(frappe.get_list(DEVICE, pluck="name"), [])

	def test_a_locked_site_registers_nothing_and_keeps_rows(self):  # covers: AC-13
		add_device(MANAGER, "kept")
		with push_on(), patch.dict(frappe.flags, {"books_site_locked": True}):
			with self.assertRaises(notifications.devices.SiteLockedError):
				self.register(MANAGER, "token-a")
			with self.set_user(MANAGER):
				self.assertEqual(devices.unregister_device("kept"), {"deleted": False})
		self.assertEqual(frappe.db.count(DEVICE), 1)

	def test_boot_carries_only_the_public_config(self):  # covers: AC-1, AC-12
		bootinfo = frappe._dict()
		with self.set_user(MANAGER):
			with push_off():
				extend_bootinfo(bootinfo)
			self.assertIsNone(bootinfo.books["push"])
			with push_on():
				extend_bootinfo(bootinfo)

		self.assertEqual(bootinfo.books["push"], {"web_config": TEST_WEB_CONFIG, "vapid_key": TEST_VAPID_KEY})
		self.assertNotIn("PRIVATE KEY", json.dumps(bootinfo, default=str))

	def test_a_register_after_an_hour_updates_last_seen(self):  # covers: AC-3
		with push_on():
			name = self.register(MANAGER, "token-a")["name"]
			old = add_to_date(now_datetime(), hours=-2)
			frappe.db.set_value(DEVICE, name, "last_seen", old)
			self.register(MANAGER, "token-a")
		self.assertGreater(frappe.db.get_value(DEVICE, name, "last_seen"), old)

	def test_the_row_keeps_a_hash_of_the_token_and_the_session_user(self):  # covers: AC-3, AC-12
		with push_on():
			name = self.register(MANAGER, "token-a", device_label="x" * 300)["name"]
		row = frappe.get_doc(DEVICE, name)
		self.assertEqual(row.token_hash, hashlib.sha256(b"token-a").hexdigest())
		self.assertEqual(row.user, MANAGER)
		# The label is cut to 140 characters, the field's length.
		self.assertEqual(len(row.device_label), 140)

	def test_an_empty_or_oversized_token_is_refused(self):  # covers: AC-3
		with push_on():
			for token in ("", "   ", "t" * 5000):
				with self.assertRaises(frappe.ValidationError):
					self.register(MANAGER, token)
		self.assertEqual(frappe.db.count(DEVICE), 0)

	def test_a_user_cannot_delete_another_users_row_through_the_api(self):  # covers: AC-3
		theirs = add_device(MANAGER, "theirs")
		with self.set_user(BOOKS_USER), self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(DEVICE, theirs.name)
		self.assertTrue(frappe.db.exists(DEVICE, theirs.name))
		self.assertFalse(frappe.has_permission(DEVICE, "read", doc=theirs, user=BOOKS_USER))

	def test_nobody_creates_or_edits_rows_through_the_api(self):  # covers: AC-3
		mine = add_device(BOOKS_USER, "mine")
		self.assertFalse(frappe.has_permission(DEVICE, "create", user=BOOKS_USER))
		self.assertFalse(frappe.has_permission(DEVICE, "write", doc=mine, user=BOOKS_USER))

	def test_a_broken_web_config_turns_push_off_in_the_boot(self):  # covers: AC-1
		with (
			push_on(),
			patch.dict(frappe.conf, {"books_fcm_web_config": "{not json"}),
			self.set_user(MANAGER),
		):
			self.assertIsNone(devices.boot_block())

	def test_stale_devices_go_after_ninety_days(self):  # covers: AC-14
		stale = add_device(MANAGER, "stale", last_seen=add_to_date(now_datetime(), days=-91))
		fresh = add_device(MANAGER, "fresh", last_seen=add_to_date(now_datetime(), days=-89))

		notifications.delete_stale_devices()

		self.assertFalse(frappe.db.exists(DEVICE, stale.name))
		self.assertTrue(frappe.db.exists(DEVICE, fresh.name))


class IntegrationTestNotificationSettings(IntegrationTestCase):
	def test_events_default_on_and_only_managers_read(self):  # covers: AC-8
		frappe.db.delete("Singles", {"doctype": SETTINGS})
		self.assertTrue(sending.event_enabled("payment_received"))
		frappe.db.set_single_value(SETTINGS, "payment_received", 0)
		self.assertFalse(sending.event_enabled("payment_received"))
		self.assertTrue(sending.event_enabled("low_stock"))

		ensure_user(BOOKS_USER, "Books User")
		ensure_user(MANAGER, "Books Manager")
		self.assertFalse(frappe.has_permission(SETTINGS, "read", user=BOOKS_USER))
		self.assertTrue(frappe.has_permission(SETTINGS, "write", user=MANAGER))

	def test_a_new_site_shows_every_event_on_after_the_hourly_job(self):  # covers: AC-8
		from frappe_books.setup import bootstrap

		frappe.db.delete("Singles", {"doctype": SETTINGS})
		bootstrap()
		# The job stores the phase on every site; Frappe then stops filling defaults for the switches.
		notifications.notify_subscription_phase()
		frappe.clear_document_cache(SETTINGS, SETTINGS)

		settings = frappe.get_doc(SETTINGS)
		self.assertEqual(
			(settings.payment_received, settings.low_stock, settings.low_stock_daily, settings.subscription),
			(1, 1, 1, 1),
		)

	def test_the_daily_reminder_counts_as_on_until_switched_off(self):  # covers: AC-8, AC-15
		frappe.db.delete("Singles", {"doctype": SETTINGS})
		self.assertTrue(sending.event_enabled("low_stock_daily"))
		frappe.db.set_single_value(SETTINGS, "low_stock_daily", 0)
		self.assertFalse(sending.event_enabled("low_stock_daily"))

	def test_four_switches_and_a_hidden_day(self):  # covers: AC-8, AC-15
		meta = frappe.get_meta(SETTINGS)
		checks = [field.label for field in meta.fields if field.fieldtype == "Check"]
		self.assertEqual(
			checks, ["Payment received", "Low stock", "Daily low stock reminder", "Subscription"]
		)
		day = meta.get_field("last_low_stock_nudge_on")
		self.assertEqual((day.fieldtype, day.hidden, day.read_only), ("Date", 1, 1))

	def test_the_patch_turns_every_event_on(self):  # covers: AC-8
		from frappe_books.patches import add_notification_settings

		frappe.db.delete("Singles", {"doctype": SETTINGS})
		frappe.db.set_single_value(SETTINGS, "low_stock", 0)

		add_notification_settings.execute()

		stored = frappe.db.get_singles_dict(SETTINGS)
		self.assertEqual((stored.payment_received, stored.low_stock, stored.subscription), ("1", "0", "1"))


class PushEventsBase(IntegrationTestCase):
	def setUp(self):
		ensure_user(MANAGER, "Books Manager")
		ensure_user(OTHER_MANAGER, "Books Manager")
		ensure_user(CASHIER, "Books Cashier")
		frappe.db.delete(DEVICE)
		frappe.db.delete("Singles", {"doctype": SETTINGS})
		self.manager_device = add_device(MANAGER)
		self.other_device = add_device(OTHER_MANAGER)
		add_device(CASHIER)


class IntegrationTestPaymentPushes(PushEventsBase):
	def setUp(self):
		super().setUp()
		self.receivable = make_account("Push Receivable", account_type="Receivable")
		self.cash = make_account("Push Cash", account_type="Cash")
		self.income = make_account("Push Income", root_type="Income", account_type="Income Account")
		expense = make_account("Push Expense", root_type="Expense", account_type="Expense Account")
		self.item = make_item(self.income.name, expense.name)
		self.party = make_party(self.receivable.name)

	def make_payment(self, payment_type="Receive"):
		return frappe.get_doc(
			{
				"doctype": "Books Payment",
				"party": self.party.name,
				"date": now_datetime(),
				"payment_type": payment_type,
				"account": self.receivable.name,
				"payment_account": self.cash.name,
				"payment_method": "Cash",
				"amount": 5000,
			}
		).insert()

	def test_a_receive_payment_pushes_managers_after_commit(self):  # covers: AC-5, AC-10
		queue, enqueue = queued_pushes()
		with push_on(), enqueue, self.set_user(MANAGER):
			payment = self.make_payment()
			payment.submit()

		((method, kwargs),) = queue.calls
		self.assertEqual((method, kwargs["queue"], kwargs["timeout"]), (sending.JOB, "short", 120))
		self.assertTrue(kwargs["enqueue_after_commit"])
		# The Manager who took it is skipped; the Cashier gets none of these events.
		self.assertEqual(queue.by_user(), [OTHER_MANAGER])
		message = queue.messages[0]
		self.assertEqual(message["title"], "Payment received")
		self.assertIn(self.party.name, message["body"])
		self.assertIn("5,000", message["body"])
		self.assertEqual(message["link"], f"/books/edit/Payment/{payment.name}")
		self.assertEqual(message["tag"], f"payment:{payment.name}")

	def test_pay_cancel_amend_and_a_switched_off_event_send_nothing(self):  # covers: AC-5, AC-8
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			self.make_payment("Pay").submit()
			payment = self.make_payment()
			payment.submit()
			payment.cancel()
			amended = frappe.copy_doc(payment)
			amended.amended_from = payment.name
			amended.docstatus = 0
			amended.insert().submit()
			frappe.db.set_single_value(SETTINGS, "payment_received", 0)
			self.make_payment().submit()

		self.assertEqual(len(queue.calls), 1)

	def test_a_failure_while_building_the_push_never_fails_the_payment(self):  # covers: AC-10
		frappe.db.delete("Error Log")
		with push_on(), patch.object(sending, "recipients", side_effect=ValueError("boom")):
			payment = self.make_payment()
			payment.submit()
		self.assertEqual(frappe.db.get_value("Books Payment", payment.name, "docstatus"), 1)
		self.assertEqual(frappe.db.count("Error Log", {"method": ["like", "Books push%"]}), 1)

	def test_nothing_without_keys(self):  # covers: AC-1
		queue, enqueue = queued_pushes()
		with push_off(), enqueue:
			self.make_payment().submit()
		self.assertEqual(queue.calls, [])

	def test_a_pos_sale_pushes_once_with_its_total(self):  # covers: AC-5
		from frappe_books.frappe_books.doctype.books_pos_opening_shift.test_books_pos_opening_shift import (
			start_pos_shift,
		)
		from frappe_books.tests.test_pos_payments import make_payment_method

		start_pos_shift()
		# Each tendered row pays part of the sale.
		frappe.db.set_single_value("Books Accounting Settings", "enable_partial_payment", 1)
		card = make_payment_method("Push Card", make_account("Push Card Clearing", account_type="Bank").name)
		invoice = make_invoice(
			"Books Sales Invoice",
			self.party.name,
			self.receivable.name,
			self.item.name,
			self.income.name,
			is_pos=1,
			payments=[
				{"payment_method": "Cash", "amount": 100},
				{"payment_method": card.name, "amount": 80, "reference_id": "R1"},
			],
		)
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			invoice.submit()

		self.assertEqual(len(queue.calls), 1)
		message = queue.messages[0]
		self.assertIn("180", message["body"])
		self.assertEqual(message["link"], f"/books/edit/SalesInvoice/{invoice.name}")
		self.assertEqual(message["tag"], f"payment:{invoice.name}")

	def test_paying_a_pos_invoice_later_pushes_that_calls_total(self):  # covers: AC-5
		from frappe_books.frappe_books.doctype.books_pos_opening_shift.test_books_pos_opening_shift import (
			start_pos_shift,
		)
		from frappe_books.frappe_books.doctype.books_sales_invoice.books_sales_invoice import pay_pos_invoice

		start_pos_shift()
		frappe.db.set_single_value("Books Accounting Settings", "enable_partial_payment", 1)
		invoice = make_invoice(
			"Books Sales Invoice",
			self.party.name,
			self.receivable.name,
			self.item.name,
			self.income.name,
			is_pos=1,
		)
		invoice.submit()
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			pay_pos_invoice(invoice.name, [{"payment_method": "Cash", "amount": 50}])

		self.assertEqual(len(queue.calls), 1)
		self.assertIn("50", queue.messages[0]["body"])
		self.assertEqual(queue.messages[0]["link"], f"/books/edit/SalesInvoice/{invoice.name}")

	def test_a_system_manager_without_a_books_role_gets_pushes(self):  # covers: AC-5
		admin = ensure_user("push-sysadmin@books.test", "System Manager")
		device = add_device(admin)
		names = [name for names in sending.recipients().values() for name in names]
		self.assertIn(device.name, names)

	def test_each_push_is_in_its_recipients_language(self):  # covers: AC-9
		frappe.db.set_value("User", OTHER_MANAGER, "language", "fr")
		try:
			with patch.object(events, "_", side_effect=lambda text, lang=None: f"[{lang}] {text}"):
				messages = sending.build_messages(
					lambda lang: {
						"title": events._("Payment received", lang=lang),
						"body": "",
						"link": "",
						"tag": "",
					}
				)
		finally:
			frappe.db.set_value("User", OTHER_MANAGER, "language", None)

		titles = {message["device"]: message["title"] for message in messages}
		self.assertEqual(titles[self.other_device.name], "[fr] Payment received")
		self.assertNotEqual(titles[self.manager_device.name], "[fr] Payment received")

	def test_a_disabled_manager_gets_nothing(self):  # covers: AC-5
		frappe.db.set_value("User", OTHER_MANAGER, "enabled", 0)
		try:
			devices_by_language = sending.recipients()
		finally:
			frappe.db.set_value("User", OTHER_MANAGER, "enabled", 1)
		names = [name for names in devices_by_language.values() for name in names]
		self.assertEqual(names, [self.manager_device.name])


class IntegrationTestSendJob(PushEventsBase):
	def test_dead_rows_go_failures_log_once_without_secrets(self):  # covers: AC-10, AC-12
		frappe.db.delete("Error Log")
		messages = [
			{"device": self.manager_device.name, "title": "t", "body": "b", "link": "/books/", "tag": "x"},
			{"device": self.other_device.name, "title": "t", "body": "b", "link": "/books/", "tag": "x"},
		]
		outcomes = {
			self.manager_device.token: fcm.Outcome(fcm.DEAD, 404, "UNREGISTERED"),
			self.other_device.token: fcm.Outcome(fcm.FAILED, None, "timeout"),
		}
		with (
			push_on(),
			patch.object(fcm, "access_token", return_value="ya29.test"),
			patch.object(fcm, "send", side_effect=lambda token, *args: outcomes[token]),
		):
			notifications.send_job(messages)

		self.assertFalse(frappe.db.exists(DEVICE, self.manager_device.name))
		self.assertTrue(frappe.db.exists(DEVICE, self.other_device.name))
		logs = frappe.get_all("Error Log", fields=["method", "error"])
		self.assertEqual(len(logs), 1)
		text = json.dumps(logs)
		self.assertIn("timeout", text)
		for secret in (self.manager_device.token, self.other_device.token, "PRIVATE KEY", "ya29"):
			self.assertNotIn(secret, text)

	def test_a_sender_mismatch_keeps_the_rows(self):  # covers: AC-10
		messages = [
			{"device": self.manager_device.name, "title": "t", "body": "b", "link": "/books/", "tag": "x"}
		]
		with (
			push_on(),
			patch.object(fcm, "access_token", return_value="ya29.test"),
			patch.object(fcm, "send", return_value=fcm.Outcome(fcm.FAILED, 403, "SENDER_ID_MISMATCH")),
		):
			notifications.send_job(messages)
		self.assertTrue(frappe.db.exists(DEVICE, self.manager_device.name))

	def test_a_bad_key_logs_once_and_sends_nothing(self):  # covers: AC-10
		frappe.db.delete("Error Log")
		messages = [
			{"device": self.manager_device.name, "title": "t", "body": "b", "link": "/books/", "tag": "x"}
		]
		with (
			push_on(),
			patch.object(fcm, "access_token", side_effect=fcm.FcmError(400, "invalid_grant")),
			patch.object(fcm, "send") as send,
		):
			notifications.send_job(messages)
		send.assert_not_called()
		self.assertEqual(frappe.db.count("Error Log"), 1)


class IntegrationTestSendReport(PushEventsBase):
	def message(self, device):
		return {"device": device.name, "title": "t", "body": "b", "link": "/books/", "tag": "x"}

	def send_job(self, outcomes, token_error=None):
		messages = [self.message(self.manager_device), self.message(self.other_device)]
		by_token = dict(zip((self.manager_device.token, self.other_device.token), outcomes, strict=True))
		with (
			push_on(),
			patch.object(fcm, "access_token", return_value="ya29.test", side_effect=token_error),
			patch.object(fcm, "send", side_effect=lambda token, *args: by_token[token]),
		):
			return notifications.send_job(messages)

	def test_counts_the_pushes_sent_and_refused(self):  # covers: AC-10, AC-15
		report = self.send_job([fcm.SENT, fcm.Outcome(fcm.FAILED, 503, "UNAVAILABLE")])
		self.assertEqual((report.sent, report.failed, report.ok), (1, 1, True))

	def test_every_send_refused_is_not_ok(self):  # covers: AC-7, AC-10
		failed = fcm.Outcome(fcm.FAILED, 503, "UNAVAILABLE")
		report = self.send_job([failed, failed])
		self.assertEqual((report.sent, report.failed, report.ok), (0, 2, False))

	def test_a_bad_key_counts_every_message_as_refused(self):  # covers: AC-10
		report = self.send_job([fcm.SENT, fcm.SENT], token_error=fcm.FcmError(400, "invalid_grant"))
		self.assertEqual((report.sent, report.failed, report.ok), (0, 2, False))

	def test_dead_devices_are_neither_sent_nor_refused(self):  # covers: AC-10, AC-15
		dead = fcm.Outcome(fcm.DEAD, 404, "UNREGISTERED")
		report = self.send_job([dead, dead])
		self.assertEqual((report.sent, report.failed, report.ok), (0, 0, True))

	def test_nothing_to_send_reports_nothing(self):  # covers: AC-1, AC-10
		with push_on():
			self.assertEqual(notifications.send_job([]), sending.SendReport(0, 0))
		with push_off():
			self.assertEqual(sending.send_now(lambda lang: {}), sending.SendReport(0, 0))


class IntegrationTestLowStockPushes(PushEventsBase):
	def setUp(self):
		super().setUp()
		from frappe_books.frappe_books.doctype.books_shipment.test_books_shipment import seed_stock

		self.seed_stock = seed_stock
		income = make_account("Push Stock Income", root_type="Income")
		# A tracked item's purchase account is stock received but not billed, a liability.
		expense = make_account("Push Stock Received", root_type="Liability")
		self.item = make_item(income.name, expense.name, track_item=1).name

	def move(self, quantity):
		from frappe_books.frappe_books.doctype.books_stock_movement.test_books_stock_movement import (
			movement_values,
		)

		movement_type = "MaterialReceipt" if quantity > 0 else "MaterialIssue"
		location = {"to_location": "Stores"} if quantity > 0 else {"from_location": "Stores"}
		row = {"item": self.item, "quantity": abs(quantity), "rate": 10, **location}
		movement = frappe.get_doc(movement_values(movement_type, [row])).insert()
		movement.submit()
		return movement

	def set_level(self, level):
		item = frappe.get_doc("Books Item", self.item)
		item.reorder_level = level
		item.save()

	def test_alerts_once_until_restocked(self):  # covers: AC-6
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			self.move(12)
			self.set_level(10)
			self.assertEqual(queue.calls, [])
			self.move(-3)
			self.move(-1)
			self.assertEqual(len(queue.calls), 1)
			self.move(7)
			self.assertFalse(frappe.db.get_value("Books Item", self.item, "low_stock_notified"))
			self.move(-8)

		self.assertEqual(len(queue.calls), 2)
		message = queue.messages[0]
		self.assertEqual(message["title"], f"Low stock: {self.item}")
		self.assertIn("9", message["body"])
		self.assertIn("reorder level 10", message["body"])
		self.assertEqual(message["link"], f"/books/edit/Item/{self.item}")
		self.assertEqual(message["tag"], f"low-stock:{self.item}")

	def test_a_cancel_that_drops_stock_alerts(self):  # covers: AC-6
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			self.move(5)
			receipt = self.move(10)
			self.set_level(8)
			receipt.cancel()
		self.assertEqual(len(queue.calls), 1)

	def test_a_level_set_above_stock_alerts_on_that_save(self):  # covers: AC-6
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			self.move(5)
			self.set_level(8)
			self.assertEqual(len(queue.calls), 1)
			self.set_level(0)
			self.assertFalse(frappe.db.get_value("Books Item", self.item, "low_stock_notified"))
			self.move(-1)
		self.assertEqual(len(queue.calls), 1)

	def test_moving_stock_between_locations_sends_nothing(self):  # covers: AC-6
		from frappe_books.frappe_books.doctype.books_stock_movement.test_books_stock_movement import (
			movement_values,
		)

		shop = frappe.get_doc({"doctype": "Books Location", "name": unique_name("Shop")}).insert().name
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			self.move(12)
			self.set_level(10)
			row = {
				"item": self.item,
				"quantity": 5,
				"rate": 10,
				"from_location": "Stores",
				"to_location": shop,
			}
			frappe.get_doc(movement_values("MaterialTransfer", [row])).insert().submit()
		# Stores drops to 7, but the total across locations stays 12.
		self.assertEqual(queue.calls, [])
		self.assertFalse(frappe.db.get_value("Books Item", self.item, "low_stock_notified"))

	def test_an_untracked_item_is_never_checked(self):  # covers: AC-6
		income = make_account("Push Service Income", root_type="Income")
		expense = make_account("Push Service Expense", root_type="Expense")
		service = make_item(income.name, expense.name, item_type="Service").name
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			notifications.check_low_stock([service])
		self.assertEqual(queue.calls, [])
		self.assertFalse(frappe.db.get_value("Books Item", service, "low_stock_notified"))

	def test_a_failing_low_stock_check_never_fails_the_stock_transaction(self):  # covers: AC-10
		with push_on():
			self.move(12)
			self.set_level(10)
			with patch.object(events, "_stock_on_hand", side_effect=ValueError("boom")):
				movement = self.move(-3)
		self.assertEqual(movement.docstatus, 1)
		# The check's partial writes are undone with it.
		self.assertFalse(frappe.db.get_value("Books Item", self.item, "low_stock_notified"))

	def test_an_item_without_a_level_takes_no_lock(self):  # covers: AC-6
		with push_on(), patch.object(events.frappe.db, "get_value", wraps=frappe.db.get_value) as get_value:
			self.move(5)
		locked = [call for call in get_value.call_args_list if call.kwargs.get("for_update")]
		self.assertEqual(locked, [])

	def test_the_switch_keeps_the_flag_but_sends_nothing(self):  # covers: AC-6, AC-8
		frappe.db.set_single_value(SETTINGS, "low_stock", 0)
		queue, enqueue = queued_pushes()
		with push_on(), enqueue:
			self.move(5)
			self.set_level(8)
		self.assertEqual(queue.calls, [])
		self.assertTrue(frappe.db.get_value("Books Item", self.item, "low_stock_notified"))


class IntegrationTestSubscriptionPushes(PushEventsBase):
	def setUp(self):
		super().setUp()
		self.sent = []
		self.send = patch.object(
			fcm,
			"send",
			side_effect=lambda token, title, body, link, tag: self.sent.append((title, body, link, tag))
			or fcm.SENT,
		)
		self.token = patch.object(fcm, "access_token", return_value="ya29.test")

	def run_at(self, phase, subscription_starts_on=None, **status):
		clock = MagicMock(phase=phase, subscription_starts_on=subscription_starts_on)
		clock.status.return_value = {"phase": phase, **status}
		with push_on(), self.send, self.token, patch.object(events, "current_clock", return_value=clock):
			events.notify_subscription_phase()
		return frappe.db.get_single_value(SETTINGS, "last_subscription_phase")

	def test_first_run_stores_the_phase_and_sends_nothing(self):  # covers: AC-7
		self.assertEqual(self.run_at("prompt", lock_starts_on="2031-01-26"), "prompt")
		self.assertEqual(self.sent, [])

	def test_each_phase_pushes_once(self):  # covers: AC-7
		self.run_at("trial")
		self.run_at("prompt", lock_starts_on="2031-01-26")
		self.run_at("prompt", lock_starts_on="2031-01-26")
		self.run_at("active")
		self.run_at("renew_soon", paid_until="2031-03-01")
		self.run_at("grace", grace_ends_on="2031-03-08")

		titles = [title for title, *_rest in self.sent]
		# Two Manager devices each time; the Cashier device gets none.
		self.assertEqual(
			titles,
			["Your books turn read only soon"] * 2 + ["Renewal due"] * 2 + ["Payment overdue"] * 2,
		)
		self.assertTrue(all(link == "/books/subscription" for _t, _b, link, _tag in self.sent))
		self.assertEqual(self.sent[0][3], "subscription:prompt")

	def test_locked_and_lapsed_share_one_push(self):  # covers: AC-7, AC-13
		self.run_at("prompt")
		self.run_at("locked")
		self.run_at("locked")
		self.run_at("lapsed")

		self.assertEqual({title for title, *_rest in self.sent}, {"RareBooks is now read only"})
		self.assertEqual(len(self.sent), 2)
		self.assertEqual(self.sent[0][3], "subscription:read-only")

	def test_a_switched_off_event_stores_the_phase_without_a_push(self):  # covers: AC-7, AC-8
		frappe.db.set_single_value(SETTINGS, "subscription", 0)
		self.run_at("trial")
		self.assertEqual(self.run_at("grace", grace_ends_on="2031-03-08"), "grace")
		self.assertEqual(self.sent, [])
		# Turning it back on resends nothing missed.
		frappe.db.set_single_value(SETTINGS, "subscription", 1)
		self.run_at("grace", grace_ends_on="2031-03-08")
		self.assertEqual(self.sent, [])

	def test_unmanaged_and_exempt_never_push(self):  # covers: AC-7
		self.run_at("unmanaged")
		self.run_at("prompt")
		self.run_at("exempt")
		self.run_at("grace")
		self.assertEqual(self.sent, [])

	def test_a_failed_send_stores_nothing_so_the_next_run_retries(self):  # covers: AC-7, AC-10
		self.run_at("trial")
		self.send = patch.object(fcm, "send", return_value=fcm.Outcome(fcm.FAILED, 503, "UNAVAILABLE"))
		self.assertEqual(self.run_at("prompt", lock_starts_on="2031-01-26"), "trial")

	def test_the_prompt_push_names_the_lock_date(self):  # covers: AC-7
		self.run_at("trial")
		# A first run that only sees `prompt` on day 25 still names day 26, never the past trial end.
		self.run_at("prompt", trial_ends_on="2031-01-21", lock_starts_on="2031-01-26")

		title, body, _link, _tag = self.sent[0]
		self.assertEqual(title, "Your books turn read only soon")
		self.assertIn(formatdate("2031-01-26"), body)
		self.assertNotIn(formatdate("2031-01-21"), body)
		self.assertTrue(body.startswith("Subscribe before "))

	def test_paypal_set_to_start_gets_no_prompt_push_ever(self):  # covers: AC-7
		self.run_at("trial")
		# Day 22: the PayPal charge is due today.
		stored = self.run_at("prompt", subscription_starts_on="2031-01-22", lock_starts_on="2031-01-26")
		self.assertEqual((stored, self.sent), ("prompt", []))
		# Day 23: the charge is overdue and the clock no longer says it starts; the phase is already stored.
		self.run_at("prompt", lock_starts_on="2031-01-26")
		self.assertEqual(self.sent, [])
		# The lock still pushes as usual.
		self.run_at("locked")
		self.assertEqual({title for title, *_rest in self.sent}, {"RareBooks is now read only"})


class IntegrationTestLowStockSummary(PushEventsBase):
	ZONE = ZoneInfo("Africa/Dar_es_Salaam")  # UTC+3, so 05:00 UTC is 08:00 at the site

	def setUp(self):
		super().setUp()
		from frappe_books.frappe_books.doctype.books_shipment.test_books_shipment import seed_stock

		self.seed_stock = seed_stock
		# Items other tests left with a level would join the summary.
		frappe.db.set_value("Books Item", {"reorder_level": [">", 0]}, "reorder_level", 0)
		self.income = make_account("Push Summary Income", root_type="Income").name
		self.expense = make_account("Push Summary Received", root_type="Liability").name
		self.sent = []
		self.outcome = fcm.SENT
		self.locked = False

	def item(self, stock, level, name=None):
		values = {"name": name} if name else {}
		item = make_item(self.income, self.expense, track_item=1, **values).name
		if stock:
			with push_off():
				self.seed_stock(item, stock, 10)
		frappe.db.set_value("Books Item", item, "reorder_level", level)
		return item

	def run_at(self, utc):
		def send(token, title, body, link, tag):
			self.sent.append((title, body, link, tag))
			return self.outcome() if callable(self.outcome) else self.outcome

		with (
			push_on(),
			patch.object(fcm, "send", side_effect=send),
			patch.object(fcm, "access_token", return_value="ya29.test"),
			patch.object(events, "utc_now", return_value=utc),
			patch.object(events, "site_zone", return_value=self.ZONE),
			patch.object(events, "is_locked", return_value=self.locked),
		):
			notifications.notify_low_stock_daily()
		sent, self.sent = self.sent, []
		return sent

	def stored_day(self):
		# The raw value: `get_single_value` reads an empty Date as 0001-01-01.
		return frappe.db.get_singles_dict(SETTINGS).get("last_low_stock_nudge_on")

	def test_one_summary_a_day_most_urgent_first(self):  # covers: AC-15
		low = self.item(2, 10)
		empty = self.item(0, 5)
		half = self.item(6, 10)
		near = self.item(4, 5)
		self.item(20, 10)  # restocked, so not listed

		self.assertEqual(self.run_at(datetime(2031, 5, 6, 4, 59)), [])  # 07:59 at the site
		sent = self.run_at(datetime(2031, 5, 6, 5, 0))
		# One push for each of the two Manager devices, none for the Cashier.
		self.assertEqual(len(sent), 2)
		title, body, link, tag = sent[0]
		self.assertEqual(title, "Low stock items: 4")
		self.assertEqual(body, f"{empty} 0 Unit, {low} 2 Unit, {half} 6 Unit, +1 more")
		self.assertNotIn(near, body)
		self.assertEqual((link, tag), ("/books/report/StockBalance", "low-stock:daily"))
		self.assertEqual(str(self.stored_day()), "2031-05-06")

		self.assertEqual(self.run_at(datetime(2031, 5, 6, 6, 0)), [])
		self.assertEqual(self.run_at(datetime(2031, 5, 7, 4, 0)), [])
		self.assertEqual(len(self.run_at(datetime(2031, 5, 7, 9, 30))), 2)
		self.assertEqual(str(self.stored_day()), "2031-05-07")

	def test_a_single_low_item_links_the_item(self):  # covers: AC-15
		item = self.item(2, 10)
		title, body, link, tag = self.run_at(datetime(2031, 5, 6, 5, 0))[0]
		self.assertEqual(title, f"Low stock: {item}")
		self.assertEqual(body, "2 Unit left (reorder level 10)")
		self.assertEqual((link, tag), (f"/books/edit/Item/{item}", "low-stock:daily"))

	def test_long_names_are_cut(self):  # covers: AC-15
		long_name = unique_name("A long item name " + "x" * 40)
		self.item(1, 10, name=long_name)
		other = self.item(3, 10)
		body = self.run_at(datetime(2031, 5, 6, 5, 0))[0][1]
		self.assertEqual(body, f"{long_name[:40]} 1 Unit, {other} 3 Unit")

	def test_a_cut_that_ends_on_a_space_leaves_no_double_space(self):  # covers: AC-15
		# The 40th character is a space, so the cut name would end in one.
		name = unique_name("Cement bag fifty kilograms grey portlan d")
		self.assertEqual(name[39], " ")
		self.item(1, 10, name=name)
		other = self.item(3, 10)
		body = self.run_at(datetime(2031, 5, 6, 5, 0))[0][1]
		self.assertEqual(body, f"{name[:39]} 1 Unit, {other} 3 Unit")
		self.assertNotIn("  ", body)

	def test_no_devices_skip_the_ledger_read(self):  # covers: AC-15
		self.item(2, 10)
		frappe.db.delete(DEVICE)
		with patch.object(events, "_low_items", wraps=events._low_items) as low_items:
			self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])
		low_items.assert_not_called()

	def test_an_item_that_dropped_while_push_was_off_is_listed(self):  # covers: AC-15
		item = self.item(2, 10)
		self.assertFalse(frappe.db.get_value("Books Item", item, "low_stock_notified"))
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0))[0][0], f"Low stock: {item}")

	def test_nothing_low_records_nothing(self):  # covers: AC-15
		self.item(20, 10)
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])
		self.assertIsNone(self.stored_day())

	def test_no_devices_then_a_device_sends_the_next_hour(self):  # covers: AC-15
		self.item(2, 10)
		frappe.db.delete(DEVICE)
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])
		self.assertIsNone(self.stored_day())
		add_device(MANAGER)
		self.assertEqual(len(self.run_at(datetime(2031, 5, 6, 6, 0))), 1)

	def test_every_send_refused_records_nothing(self):  # covers: AC-15
		self.item(2, 10)
		self.outcome = fcm.Outcome(fcm.FAILED, 503, "UNAVAILABLE")
		self.run_at(datetime(2031, 5, 6, 5, 0))
		self.assertIsNone(self.stored_day())
		self.outcome = fcm.SENT
		self.assertEqual(len(self.run_at(datetime(2031, 5, 6, 6, 0))), 2)
		self.assertEqual(str(self.stored_day()), "2031-05-06")

	def test_switch_lock_and_push_off_send_nothing(self):  # covers: AC-8, AC-15
		self.item(2, 10)
		frappe.db.set_single_value(SETTINGS, "low_stock_daily", 0)
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])
		frappe.db.set_single_value(SETTINGS, "low_stock_daily", 1)

		self.locked = True
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])
		self.locked = False

		with push_off(), patch.object(fcm, "send") as send:
			with patch.object(events, "utc_now", return_value=datetime(2031, 5, 6, 5, 0)):
				notifications.notify_low_stock_daily()
		send.assert_not_called()
		self.assertIsNone(self.stored_day())

	def test_a_migrated_site_gets_its_first_summary_next_morning(self):  # covers: AC-8, AC-15
		from frappe_books.patches import add_low_stock_daily_setting

		self.item(2, 10)
		frappe.db.delete("Singles", {"doctype": SETTINGS})
		with (
			patch.object(events, "utc_now", return_value=datetime(2031, 5, 6, 7, 0)),
			patch.object(events, "site_zone", return_value=self.ZONE),
		):
			add_low_stock_daily_setting.execute()
		stored = frappe.db.get_singles_dict(SETTINGS)
		self.assertEqual((stored.low_stock_daily, str(stored.last_low_stock_nudge_on)), ("1", "2031-05-06"))

		self.assertEqual(self.run_at(datetime(2031, 5, 6, 8, 0)), [])
		self.assertEqual(len(self.run_at(datetime(2031, 5, 7, 5, 0))), 2)

	def test_equal_urgency_falls_back_to_the_name(self):  # covers: AC-15
		second = self.item(2, 10, name=unique_name("Tie B"))
		first = self.item(1, 5, name=unique_name("Tie A"))
		body = self.run_at(datetime(2031, 5, 6, 5, 0))[0][1]
		self.assertEqual(body, f"{first} 1 Unit, {second} 2 Unit")

	def test_exactly_three_items_add_no_more_line(self):  # covers: AC-15
		for stock in (1, 2, 3):
			self.item(stock, 10)
		title, body, _link, _tag = self.run_at(datetime(2031, 5, 6, 5, 0))[0]
		self.assertEqual(title, "Low stock items: 3")
		self.assertNotIn("more", body)
		self.assertEqual(body.count(", "), 2)

	def test_stock_at_the_level_counts_as_low(self):  # covers: AC-15
		item = self.item(10, 10)
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0))[0][0], f"Low stock: {item}")

	def test_untracked_or_unleveled_items_are_left_out(self):  # covers: AC-15
		untracked = self.item(1, 10)
		frappe.db.set_value("Books Item", untracked, "track_item", 0)
		self.item(1, 0)
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])

	def test_the_flag_of_the_instant_push_is_ignored(self):  # covers: AC-6, AC-15
		item = self.item(2, 10)
		frappe.db.set_value("Books Item", item, "low_stock_notified", 1)
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0))[0][0], f"Low stock: {item}")
		# The summary reads only; the flag stays as the instant push left it.
		self.assertEqual(frappe.db.get_value("Books Item", item, "low_stock_notified"), 1)

	def test_a_partial_success_records_the_day(self):  # covers: AC-15
		self.item(2, 10)
		outcomes = iter([fcm.SENT, fcm.Outcome(fcm.FAILED, 503, "UNAVAILABLE")])
		self.outcome = lambda: next(outcomes)
		self.assertEqual(len(self.run_at(datetime(2031, 5, 6, 5, 0))), 2)
		self.assertEqual(str(self.stored_day()), "2031-05-06")

	def test_only_dead_devices_record_nothing_and_drop_the_rows(self):  # covers: AC-10, AC-15
		self.item(2, 10)
		self.outcome = fcm.Outcome(fcm.DEAD, 404, "UNREGISTERED")
		self.run_at(datetime(2031, 5, 6, 5, 0))
		self.assertIsNone(self.stored_day())
		self.assertFalse(frappe.db.exists(DEVICE, self.manager_device.name))

	def test_the_site_time_zone_sets_the_hour(self):  # covers: AC-15
		self.item(2, 10)
		self.ZONE = ZoneInfo("UTC")
		# 05:00 UTC is 08:00 in Dar es Salaam but still 05:00 on a UTC site.
		self.assertEqual(self.run_at(datetime(2031, 5, 6, 5, 0)), [])
		self.assertEqual(len(self.run_at(datetime(2031, 5, 6, 8, 0))), 2)

	def test_the_job_runs_hourly(self):  # covers: AC-15
		hourly = frappe.get_hooks("scheduler_events", app_name="frappe_books")["hourly"]
		self.assertIn("frappe_books.notifications.notify_low_stock_daily", hourly)
