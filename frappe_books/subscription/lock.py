"""The read only lock: a locked site opens every request and job in a read only database transaction."""

import frappe
from frappe import _

from frappe_books.subscription.clock import is_locked

RUN_SCHEDULED_JOB = "frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job"
METHOD_PREFIXES = ("/api/method/", "/api/v2/method/")
# The requests a locked site still runs normally (AC-7). The legacy `cmd=` route is not matched, so it fails closed.
ALLOWED_METHODS = frozenset(
	{
		"login",
		"logout",
		"frappe.sessions.clear",
		"frappe.www.login.send_login_link",
		"frappe.www.login.login_via_key",
		"frappe.www.login.login_via_token",
		"frappe.core.doctype.user.user.reset_password",
		"frappe.core.doctype.user.user.update_password",
		"frappe_books.frappe_books.doctype.books_setup_wizard.books_setup_wizard.complete_setup",
		"frappe_books.subscription.get_subscription",
		"frappe_books.subscription.start_checkout",
		"frappe_books.subscription.receive_state",
	}
)
ALLOWED_METHOD_PREFIXES = ("frappe.integrations.oauth2_logins.",)
# Logs and housekeeping keep working so error handling can't loop; they still meet the read only transaction.
UNGUARDED_DOCTYPES = frozenset(
	{
		"Error Log",
		"Version",
		"Comment",
		"Activity Log",
		"Access Log",
		"View Log",
		"Scheduled Job Log",
		"Route History",
		"Deleted Document",
	}
)


class SiteLockedError(frappe.ValidationError):
	http_status_code = 403


def lock_request():
	"""`before_request` hook. Runs before Frappe authenticates the caller, so it must not depend on the user."""
	if is_allowed_path(frappe.request.path) or not is_locked():
		return
	_begin_read_only()


def lock_job(method: str, kwargs: dict | None = None, transaction_type: str | None = None, **_kwargs):
	"""`before_job` hook. Scheduled jobs keep running; any other job can't write."""
	if method == RUN_SCHEDULED_JOB or not is_locked():
		return
	_begin_read_only()


def refuse_when_locked(doc, method: str | None = None, *args, **kwargs):
	"""Wildcard `doc_events` hook: a clear message before the database refuses the write."""
	if frappe.flags.books_site_locked and doc.doctype not in UNGUARDED_DOCTYPES:
		frappe.throw(_("This site is read only. Subscribe to make changes again."), SiteLockedError)


def is_allowed_path(path: str) -> bool:
	for prefix in METHOD_PREFIXES:
		if path.startswith(prefix):
			name = path.removeprefix(prefix).strip("/")
			return name in ALLOWED_METHODS or name.startswith(ALLOWED_METHOD_PREFIXES)
	return False


def _begin_read_only():
	# The same pair Frappe's maintenance mode sets, so view and access logs defer to Redis.
	# `frappe.db.commit()` begins again read only while `frappe.flags.read_only` is set.
	frappe.flags.read_only = True
	frappe.flags.books_site_locked = True
	frappe.db.begin(read_only=True)
