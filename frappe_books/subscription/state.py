"""The only writers of Books Subscription: install, the patch, `apply_state` and (later) the control site sync."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import getdate

from frappe_books.subscription.clock import DOCTYPE, utc_now

PROVIDERS = ("ClickPesa", "PayPal")
BILLING_PERIODS = ("Monthly", "Yearly")


def start_trial():
	"""Start the 30 day clock now, once. Install and the patch call this."""
	facts = frappe.get_single(DOCTYPE)
	if facts.trial_started_on:
		return
	facts.trial_started_on = utc_now()
	save_facts(facts)


def apply_state(state: dict):
	"""Apply the push fields by hand: `bench --site <site> execute frappe_books.subscription.apply_state --kwargs ...`.

	Lifts or sets the lock before the control site exists. Keys left out stay as they are; unknown keys are ignored.
	"""
	facts = frappe.get_single(DOCTYPE)
	set_facts(facts, state)
	save_facts(facts)


def set_facts(facts, state: dict):
	"""Copy validated push fields onto the single. A newer `paid_until` clears the pending checkout."""
	values = _validated(state)
	if "paid_until" in values and _is_newer(values["paid_until"], facts.paid_until):
		facts.checkout_started_on = None
	facts.update(values)


def save_facts(facts):
	with syncing():
		facts.save(ignore_permissions=True)


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
		frappe.throw(_("{0} is not a valid date.").format(frappe.bold(value)))


def _choice(value, options: tuple[str, ...], field: str) -> str:
	if not value:
		return ""
	if value not in options:
		frappe.throw(_("{0} is not a valid {1}.").format(frappe.bold(value), field))
	return value


def _check(value, field: str) -> int:
	if value not in (0, 1, True, False):
		frappe.throw(_("{0} is not a valid {1}.").format(frappe.bold(value), field))
	return int(value)


def _is_newer(new_paid_until, old_paid_until) -> bool:
	return bool(new_paid_until) and (not old_paid_until or new_paid_until > getdate(old_paid_until))
