"""Whitelisted methods for the subscription: the status, checkout, and the control site's push (spec 0005)."""

import json
from typing import Literal

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url

from frappe_books.subscription import clock
from frappe_books.subscription.clock import DOCTYPE, SUBSCRIBER_ROLES, current_clock, offered_plan
from frappe_books.subscription.control import (
	CREATE_CHECKOUT,
	GET_STATE,
	SIGNATURE_HEADER,
	ControlSiteUnreachable,
	call_control,
	is_fresh,
	is_valid_signature,
	parse_issued_at,
	site_secret,
	unreachable_message,
)
from frappe_books.subscription.state import apply_synced_state, mark_checkout_started

PLANS_CACHE_KEY = "books_subscription_plans"
PLANS_CACHE_SECONDS = 60 * 60
RETURN_PATH = "/books/subscription?checkout=returned"
UNSUBSCRIBABLE_PHASES = ("unmanaged", "exempt")


class InvalidPushError(frappe.ValidationError):
	http_status_code = 400


# POST too: /books calls every method with a POST, and a POST commits what the pull applied.
@frappe.whitelist(methods=["GET", "POST"])
def get_subscription(refresh: bool = False) -> dict:
	"""The status dict, plus the plans for those who can subscribe. Allowed on a locked site.

	`refresh` pulls fresh state from the control site first, as on the return from checkout (AC-12).
	"""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	pull_error = None
	if refresh and clock.is_managed():
		pull_error = _pull_and_report()

	status = current_clock().status()
	if not status["can_subscribe"] or status["phase"] in UNSUBSCRIBABLE_PHASES:
		return status

	plans = frappe.cache.get_value(PLANS_CACHE_KEY)
	if plans is None and not pull_error:
		pull_error = _pull_and_report()
		status = current_clock().status()
		plans = frappe.cache.get_value(PLANS_CACHE_KEY)
	return {**status, "plans": _offered(plans or []), "plans_error": pull_error}


@frappe.whitelist(methods=["POST"])
def start_checkout(billing_period: Literal["Monthly", "Yearly"]) -> dict:
	"""Ask the control site for a checkout link for this site's provider and the chosen period (AC-10)."""
	frappe.only_for(list(SUBSCRIBER_ROLES))
	phase = current_clock().phase
	if phase in UNSUBSCRIBABLE_PHASES:
		frappe.throw(_("This site is not on a hosted plan."))
	if phase == "active":
		frappe.throw(_("Your subscription is active. Change your plan from your PayPal account."))

	provider, periods = offered_plan()
	if not provider:
		frappe.throw(_("Finish setup first."))
	if billing_period not in periods:
		frappe.throw(_("{0} billing isn't offered for this site.").format(_(billing_period)))

	response = call_control(
		CREATE_CHECKOUT,
		{"provider": provider, "billing_period": billing_period, "return_url": get_url(RETURN_PATH)},
	)
	checkout_url = response.get("checkout_url")
	if not isinstance(checkout_url, str) or not checkout_url.startswith(("https://", "http://")):
		raise ControlSiteUnreachable(unreachable_message())

	mark_checkout_started()
	return {"checkout_url": checkout_url}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60)
def receive_state() -> dict:
	"""The control site's signed push (AC-11). Every failure before the signature checks out answers 401."""
	body = frappe.request.get_data()
	if not clock.is_managed() or not is_valid_signature(
		body, frappe.get_request_header(SIGNATURE_HEADER), site_secret()
	):
		_refuse()

	try:
		state = json.loads(body)
	except ValueError:
		state = None
	if not isinstance(state, dict):
		_reject_push(_("The push body is not a JSON object."))

	issued_at = parse_issued_at(state.get("issued_at"))
	if state.get("site") != frappe.local.site or not issued_at or not is_fresh(issued_at):
		_refuse()

	try:
		applied = apply_synced_state(state, issued_at)
	except frappe.ValidationError as error:
		_reject_push(str(error))
	return {"result": "applied" if applied else "ignored"}


def pull_state():
	"""Fetch this site's state and plans from the control site, and apply the state like a push.

	Raises `ControlSiteUnreachable` when the control site can't be reached or answers badly.
	"""
	response = call_control(GET_STATE, {})
	state, plans = response.get("state"), response.get("plans")
	issued_at = parse_issued_at(state.get("issued_at")) if isinstance(state, dict) else None
	if not issued_at or not isinstance(plans, list):
		raise ControlSiteUnreachable(unreachable_message())

	try:
		applied = apply_synced_state(state, issued_at)
	except frappe.ValidationError:
		frappe.log_error("Books billing: get_state sent a bad value", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message()) from None

	frappe.cache.set_value(PLANS_CACHE_KEY, _valid_plans(plans), expires_in_sec=PLANS_CACHE_SECONDS)
	if applied:
		# A GET doesn't commit by itself.
		frappe.local.flags.commit = True


def _pull_and_report() -> str | None:
	"""Pull, and return the Retry message instead of raising, so the stored state still shows (AC-16)."""
	try:
		pull_state()
	except ControlSiteUnreachable:
		frappe.clear_messages()
		return unreachable_message()
	return None


def _valid_plans(plans: list) -> list[dict]:
	keys = ("provider", "billing_period", "amount", "currency", "label")
	return [
		{key: plan.get(key) for key in keys}
		for plan in plans
		if isinstance(plan, dict) and plan.get("provider") and plan.get("billing_period")
	]


def _offered(plans: list[dict]) -> list[dict]:
	"""Only the provider and periods this site's country is offered, whatever the control site lists."""
	provider, periods = offered_plan()
	return [plan for plan in plans if plan["provider"] == provider and plan["billing_period"] in periods]


def _refuse():
	raise frappe.AuthenticationError


def _reject_push(reason: str):
	frappe.log_error("Books billing: receive_state refused a bad value", reason, defer_insert=True)
	frappe.clear_messages()
	raise InvalidPushError(_("The push carried a bad value."))
