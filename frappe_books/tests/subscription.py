"""Helpers for the trial and read only lock tests (spec 0005)."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from unittest.mock import patch

import frappe
import requests
from frappe.auth import CookieManager, LoginManager
from frappe.installer import update_site_config
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client, get_url, set_request
from frappe.utils.background_jobs import execute_job
from frappe.utils.password import update_password

from frappe_books.subscription.clock import DOCTYPE, _local_date, site_zone, utc_now
from frappe_books.subscription.control import SIGNATURE_HEADER, is_valid_signature, sign
from frappe_books.subscription.state import save_facts

FACT_FIELDS = (
	"trial_started_on",
	"paid_until",
	"provider",
	"billing_period",
	"auto_renews",
	"provider_reference",
	"exempt",
	"checkout_started_on",
	"last_synced_on",
	"export_sent_on",
	"removal_hold_until",
)
LOCK_TYPES = ("SiteLockedError", "InReadOnlyMode")
TEST_SECRET = b"books-test-secret-0123456789abcdef0123"
CONTROL_URL = "https://control.example.com"
CHECKOUT_URL = "https://pay.example.com/checkout/abc"
PLANS = [
	{"provider": "PayPal", "billing_period": "Monthly", "amount": 9, "currency": "USD", "label": "Monthly"},
	{"provider": "PayPal", "billing_period": "Yearly", "amount": 90, "currency": "USD", "label": "Yearly"},
	{
		"provider": "ClickPesa",
		"billing_period": "Yearly",
		"amount": 200000,
		"currency": "TZS",
		"label": "Yearly",
	},
]
TEST_CLIENT = get_test_client()
# The cached plans and the last pull result; each control_site block starts with neither.
PULL_CACHE_KEYS = ["books_subscription_plans", "books_subscription_last_pull"]


def store_facts(**values):
	"""Save and commit the single, so the request and job threads see it."""
	facts = frappe.get_single(DOCTYPE)
	facts.update(values)
	save_facts(facts)
	frappe.db.commit()


def reset_last_synced(value=None):
	"""Set `last_synced_on` straight in the database, since the controller only lets it move forward."""
	frappe.db.set_single_value(DOCTYPE, "last_synced_on", value)
	frappe.db.commit()
	frappe.clear_document_cache(DOCTYPE, DOCTYPE)


def clear_trial_start():
	"""Empty `trial_started_on` straight in the database, since the field is mandatory and a save refuses it.

	For the no trial start lock: `bench --site <site> execute frappe_books.tests.subscription.clear_trial_start`,
	and put it back with `bench --site <site> execute frappe_books.subscription.start_trial`.
	"""
	frappe.db.set_single_value(DOCTYPE, {"trial_started_on": None, "paid_until": None, "exempt": 0})
	frappe.db.commit()
	frappe.clear_document_cache(DOCTYPE, DOCTYPE)


def lock_site():
	"""An unpaid managed site on day 41 of its clock."""
	store_facts(trial_started_on=utc_now() - timedelta(days=40), paid_until=None, exempt=0)


def unlock_site():
	store_facts(trial_started_on=utc_now(), paid_until=None, exempt=0, checkout_started_on=None)


def lock_hosted_site():
	"""For the browser tests: `bench execute` this to make the site hosted and lock it."""
	update_site_config("books_control_url", "https://control.example.com")
	lock_site()


def unlock_self_hosted_site():
	"""Undoes `lock_hosted_site`: a fresh clock and no control site URL."""
	unlock_site()
	update_site_config("books_control_url", "None")


def set_hosted_phase(phase: str):
	"""For the browser tests: `bench execute` this with `--kwargs '{"phase": "grace"}'` to show a phase.

	`waiting` is day 23 with a PayPal subscription that starts after the trial (spec 0008 AC-21).
	`pending` is the unpaid lock with a checkout started an hour ago (AC-15). `holding` is the unpaid lock after
	the export email went out an hour ago, held for 72 hours (spec 0007 AC-8).
	"""
	today = _local_date(utc_now(), site_zone())
	unpaid = {"paid_until": None, "provider": None, "billing_period": None, "auto_renews": 0}
	paid = {
		"trial_started_on": utc_now() - timedelta(days=60),
		"provider": "PayPal",
		"billing_period": "Yearly",
	}
	facts = {
		"trial": {**unpaid, "trial_started_on": utc_now()},
		"prompt": {**unpaid, "trial_started_on": utc_now() - timedelta(days=22)},
		# Day 23 with a PayPal subscription set to start after the trial (spec 0008 AC-21).
		"waiting": {
			**unpaid,
			"trial_started_on": utc_now() - timedelta(days=22),
			"provider": "PayPal",
			"auto_renews": 1,
		},
		"locked": {**unpaid, "trial_started_on": utc_now() - timedelta(days=27)},
		"active": {**paid, "paid_until": today + timedelta(days=200), "auto_renews": 1},
		"renew_soon": {**paid, "paid_until": today + timedelta(days=10), "auto_renews": 0},
		"grace": {**paid, "paid_until": today - timedelta(days=3), "auto_renews": 0},
		"lapsed": {**paid, "paid_until": today - timedelta(days=10), "auto_renews": 0},
	}
	if phase == "pending":
		values = {**facts["locked"], "checkout_started_on": utc_now() - timedelta(hours=1)}
	elif phase == "exempt":
		values = {**facts["locked"], "exempt": 1}
	elif phase == "holding":
		sent_on = utc_now() - timedelta(hours=1)
		values = {
			**facts["locked"],
			"export_sent_on": sent_on,
			"removal_hold_until": sent_on + timedelta(hours=72),
		}
	else:
		values = facts[phase]
	update_site_config("books_control_url", CONTROL_URL)
	no_hold = {"export_sent_on": None, "removal_hold_until": None}
	store_facts(**{"exempt": 0, "checkout_started_on": None, **no_hold, **values})


@contextmanager
def managed_site(managed=True):
	"""Patch the managed check, which every thread reads, instead of writing site_config.json."""
	with patch("frappe_books.subscription.clock.is_managed", return_value=managed):
		yield


class SubscriptionTestMixin:
	"""Saves the single's facts before each test and puts them back after."""

	def setUp(self):
		super().setUp()
		facts = frappe.get_single(DOCTYPE)
		self._saved_facts = {field: facts.get(field) for field in FACT_FIELDS}

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		store_facts(**self._saved_facts)
		reset_last_synced(self._saved_facts["last_synced_on"])
		super().tearDown()


def login_sid(user: str) -> str:
	"""A session id for `user`, made in this thread and committed for the request thread."""
	set_request(path="/")
	frappe.local.cookie_manager = CookieManager()
	frappe.local.login_manager = LoginManager()
	frappe.local.login_manager.login_as(user)
	sid = frappe.session.sid
	frappe.db.commit()
	frappe.set_user("Administrator")
	return sid


def call(method: str, path: str, sid: str, data: dict | None = None):
	"""A real HTTP request through Frappe's WSGI app, in its own thread like a web worker."""
	target = getattr(TEST_CLIENT, method)
	if method == "get":
		kwargs = {"query_string": {**(data or {}), "sid": sid}}
	else:
		kwargs = {"json": {**(data or {}), "sid": sid}}
	return make_request(target=target, args=(get_url(path),), kwargs=kwargs)


def exc_type(response) -> str | None:
	body = response.json or {}
	if body.get("exc_type"):
		return body["exc_type"]
	errors = body.get("errors") or [{}]
	return errors[0].get("type")


def make_user(email: str, role: str, password: str | None = None) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
	if password:
		update_password(email, password)
	frappe.db.commit()
	return email


def run_jobs(*jobs: tuple[str, dict, bool]) -> list:
	"""Run (method, kwargs, managed) jobs one after another in one thread, like one worker.

	Returns each job's error, or None.
	"""
	site, errors = frappe.local.site, []
	state = {"managed": False}

	def worker():
		with patch("frappe_books.subscription.clock.is_managed", side_effect=lambda: state["managed"]):
			for method, kwargs, managed in jobs:
				state["managed"] = managed
				try:
					execute_job(site, method, None, "books-lock-test", kwargs, user="Administrator")
					errors.append(None)
				except Exception as error:
					errors.append(error)

	thread = Thread(target=worker)
	thread.start()
	thread.join()
	return errors


def write_after_commit_job(todo: str):
	"""A job that commits, then writes straight to the database."""
	frappe.db.commit()
	frappe.db.sql("update `tabToDo` set description = 'job wrote' where name = %s", todo)


def scheduled_write_job():
	frappe.db.sql("update `tabToDo` set description = 'job wrote' where description = 'scheduled marker'")


def iso_ago(**delta) -> str:
	"""An aware ISO 8601 timestamp, `delta` before now."""
	return (datetime.now(UTC) - timedelta(**delta)).isoformat()


def signed_push(state: dict, secret: bytes = TEST_SECRET) -> tuple[bytes, str]:
	"""A push body for this site and its signature header value."""
	body = json.dumps({"site": frappe.local.site, "issued_at": iso_ago(seconds=1), **state}).encode()
	return body, sign(body, secret)


def push(body: bytes, signature: str | None):
	"""POST a push to `receive_state` over real HTTP, as the control site would, with no session."""
	with pushing():
		return post_push(push_url(), body, signature)


def push_together(*pushes: tuple[bytes, str]) -> list:
	"""Send signed pushes from separate threads, released at the same moment by a barrier.

	The patches are entered once here, since `patch` is not safe to enter from two threads at a time.
	"""
	barrier = Barrier(len(pushes))
	responses = [None] * len(pushes)
	url = push_url()

	def send(index, body, signature):
		barrier.wait()
		responses[index] = post_push(url, body, signature)

	with pushing():
		threads = [Thread(target=send, args=(index, *each)) for index, each in enumerate(pushes)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join()
	return responses


@contextmanager
def pushing():
	"""The managed site and the test secret for `post_push`, entered once from the test's own thread."""
	with (
		managed_site(),
		patch("frappe_books.subscription.api.site_secret", return_value=TEST_SECRET),
	):
		yield


def push_url() -> str:
	return get_url("/api/method/frappe_books.subscription.receive_state")


def post_push(url: str, body: bytes, signature: str | None):
	"""Safe from a thread with no Frappe context: `make_request` starts its own site thread."""
	headers = {SIGNATURE_HEADER: signature} if signature else {}
	return make_request(
		target=TEST_CLIENT.post,
		args=(url,),
		kwargs={"data": body, "headers": headers, "content_type": "application/json"},
	)


def error_log_count(title: str) -> int:
	"""Error Log rows titled `title`, after flushing the deferred rows queued in Redis.

	The flush inserts as the session user, as the scheduler's Administrator would, or the rows are dropped.
	"""
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		frappe.deferred_insert.save_to_db()
	finally:
		frappe.set_user(user)
	return frappe.db.count("Error Log", {"method": title})


class ControlStub:
	"""Stands in for the control site: checks each request's signature and signs its answers.

	`get_state` echoes the request's `issued_at`, as spec 0008 AC-2 says, unless `state` sets its own.
	`error` is raised instead of answering (a timeout, a refused connection); `sign_with` signs the answer,
	so a wrong secret gives a bad response signature. `refusal` answers `create_checkout` with a 409 carrying
	that code, in spec 0008's unwrapped signed body; `status` answers with another status instead.
	"""

	def __init__(
		self,
		state=None,
		plans=None,
		checkout_url=CHECKOUT_URL,
		error=None,
		sign_with=TEST_SECRET,
		refusal=None,
		status=200,
	):
		self.state = state or {}
		self.plans = PLANS if plans is None else plans
		self.checkout_url = checkout_url
		self.error = error
		self.sign_with = sign_with
		self.refusal = refusal
		self.status = status
		self.calls = []

	def post(self, url, data, headers, timeout):
		assert is_valid_signature(data, headers.get(SIGNATURE_HEADER), TEST_SECRET), "unsigned request"
		assert timeout == 10
		body = json.loads(data)
		self.calls.append((url.rsplit("/", 1)[-1], body))
		if self.error:
			raise self.error
		status = self.status
		if url.endswith("get_state"):
			content = {
				"message": {"state": {"issued_at": body["issued_at"], **self.state}, "plans": self.plans}
			}
		elif self.refusal:
			status, content = 409, {"refusal": self.refusal}
		else:
			content = {"message": {"checkout_url": self.checkout_url}}
		response = requests.Response()
		response.status_code = status
		response._content = json.dumps(content).encode()
		response.headers[SIGNATURE_HEADER] = sign(response._content, self.sign_with)
		return response


@contextmanager
def control_site(stub: ControlStub, country: str | None = "Kenya"):
	"""A managed site that talks to `stub`, for a company in `country`."""
	conf = {"books_control_url": CONTROL_URL, "books_control_secret": TEST_SECRET.decode()}
	with (
		patch.dict(frappe.conf, conf),
		patch("frappe_books.subscription.control.requests.post", stub.post),
		patch("frappe_books.subscription.clock.company_country", return_value=country),
	):
		frappe.cache.delete_value(PULL_CACHE_KEYS)
		yield stub
		frappe.cache.delete_value(PULL_CACHE_KEYS)
