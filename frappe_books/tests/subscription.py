"""Helpers for the trial and read only lock tests (spec 0005)."""

from contextlib import contextmanager
from datetime import timedelta
from threading import Thread
from unittest.mock import patch

import frappe
from frappe.auth import CookieManager, LoginManager
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client, get_url, set_request
from frappe.utils.background_jobs import execute_job
from frappe.utils.password import update_password

from frappe_books.subscription.clock import DOCTYPE, utc_now
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
)
LOCK_TYPES = ("SiteLockedError", "InReadOnlyMode")
TEST_CLIENT = get_test_client()


def store_facts(**values):
	"""Save and commit the single, so the request and job threads see it."""
	facts = frappe.get_single(DOCTYPE)
	facts.update(values)
	save_facts(facts)
	frappe.db.commit()


def lock_site():
	"""An unpaid managed site on day 41 of its clock."""
	store_facts(trial_started_on=utc_now() - timedelta(days=40), paid_until=None, exempt=0)


def unlock_site():
	store_facts(trial_started_on=utc_now(), paid_until=None, exempt=0, checkout_started_on=None)


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
