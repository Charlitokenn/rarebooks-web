"""The only writers of Books Subscription: install, the patch, `apply_state` and the control site sync."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate

from frappe_books.subscription.clock import DOCTYPE, utc_now

PROVIDERS = ("ClickPesa", "PayPal")
BILLING_PERIODS = ("Monthly", "Yearly")


class InvalidPushError(frappe.ValidationError):
	"""A push or pull value that fails the checks below. Only this answers 400; anything else is a 500 (spec 0007)."""

	http_status_code = 400


def start_trial():
	"""Start the 30 day clock now, once. Install and the patch call this."""
	facts = _locked_facts()
	if facts.trial_started_on:
		return
	facts.trial_started_on = utc_now()
	save_facts(facts)


def apply_state(state: dict):
	"""Apply the push fields by hand: `bench --site <site> execute frappe_books.subscription.apply_state --kwargs ...`.

	Lifts or sets the lock before the control site exists. Keys left out stay as they are; unknown keys are ignored.
	Takes the row lock like every other writer, so it can't collide with a push on a live site (spec 0007).
	"""
	facts = _locked_facts()
	set_facts(facts, state)
	save_facts(facts)


def apply_synced_state(state: dict, issued_at) -> bool:
	"""Apply a verified push or pull. One not strictly newer than the last applied one is ignored (AC-11).

	Returns whether it was applied. Raises `InvalidPushError` on a bad value, before anything changes.
	"""
	facts = _locked_facts()
	if facts.last_synced_on and issued_at <= get_datetime(facts.last_synced_on):
		return False
	set_facts(facts, state)
	facts.last_synced_on = issued_at
	save_facts(facts)
	return True


def mark_checkout_started():
	"""Drives the payment pending note (AC-15) until a newer `paid_until` arrives."""
	facts = _locked_facts()
	facts.checkout_started_on = utc_now()
	save_facts(facts)


def set_removal_hold(export_sent_on, removal_hold_until):
	"""Write, or with both None clear, the two removal hold fields (spec 0007 AC-8, AC-11). Safe to repeat."""
	facts = _locked_facts()
	stored = (_datetime_or_none(facts.export_sent_on), _datetime_or_none(facts.removal_hold_until))
	if stored == (_datetime_or_none(export_sent_on), _datetime_or_none(removal_hold_until)):
		return
	facts.export_sent_on = export_sent_on
	facts.removal_hold_until = removal_hold_until
	save_facts(facts)


def set_facts(facts, state: dict):
	"""Copy validated push fields onto the single.

	A newer `paid_until` clears the pending checkout and any removal hold (spec 0007 AC-11).
	"""
	values = _validated(state)
	if "paid_until" in values and _is_newer(values["paid_until"], facts.paid_until):
		facts.checkout_started_on = None
		facts.export_sent_on = None
		facts.removal_hold_until = None
	facts.update(values)


def save_facts(facts):
	with syncing():
		facts.save(ignore_permissions=True)


def _locked_facts():
	"""The single read with a row lock (SELECT ... FOR UPDATE), held until this transaction ends.

	A locking read sees the latest committed rows, not the cache or this transaction's older snapshot,
	so a second push, pull or checkout waits here for the first to commit and then builds on its result.
	Take it only after any control site call has returned, so the lock is never held across a network wait.
	"""
	return frappe.get_doc(DOCTYPE, DOCTYPE, for_update=True)


@contextmanager
def syncing():
	"""The controller guard lets a save through only inside this block, never from request input."""
	frappe.flags.books_subscription_sync = True
	try:
		yield
	finally:
		frappe.flags.books_subscription_sync = False


def _validated(state: dict) -> dict:
	values = {}
	if "paid_until" in state:
		values["paid_until"] = _date_or_none(state["paid_until"])
	if "provider" in state:
		values["provider"] = _choice(state["provider"], PROVIDERS, "provider")
	if "billing_period" in state:
		values["billing_period"] = _choice(state["billing_period"], BILLING_PERIODS, "billing_period")
	for flag in ("auto_renews", "exempt"):
		if flag in state:
			values[flag] = _check(state[flag], flag)
	if "provider_reference" in state:
		values["provider_reference"] = str(state["provider_reference"] or "") or None
	return values


def _date_or_none(value):
	if not value:
		return None
	try:
		return getdate(value)
	except Exception:
		frappe.throw(_("{0} is not a valid date.").format(frappe.bold(value)), InvalidPushError)


def _choice(value, options: tuple[str, ...], field: str) -> str:
	if not value:
		return ""
	if value not in options:
		frappe.throw(_("{0} is not a valid {1}.").format(frappe.bold(value), field), InvalidPushError)
	return value


def _check(value, field: str) -> int:
	if value not in (0, 1, True, False):
		frappe.throw(_("{0} is not a valid {1}.").format(frappe.bold(value), field), InvalidPushError)
	return int(value)


def _datetime_or_none(value):
	return get_datetime(value) if value else None


def _is_newer(new_paid_until, old_paid_until) -> bool:
	return bool(new_paid_until) and (not old_paid_until or new_paid_until > getdate(old_paid_until))
