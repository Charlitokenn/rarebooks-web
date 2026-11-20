"""Whitelisted methods for the subscription: the status, checkout, and the control site's push (spec 0005)."""

import json
import pickle
from typing import Literal

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import formatdate, get_url

from frappe_books.subscription import clock
from frappe_books.subscription.clock import DOCTYPE, SUBSCRIBER_ROLES, current_clock, offered_plan
from frappe_books.subscription.control import (
	CREATE_CHECKOUT,
	GET_STATE,
	SIGNATURE_HEADER,
	ControlRefusal,
	ControlSiteUnreachable,
	call_control,
	is_fresh,
	is_trusted_link,
	is_valid_signature,
	issued_now,
	parse_issued_at,
	site_facts,
	site_secret,
	unreachable_message,
)
from frappe_books.subscription.state import InvalidPushError, apply_synced_state, mark_checkout_started

PLANS_CACHE_KEY = "books_subscription_plans"
PLANS_CACHE_SECONDS = 60 * 60
# One pull per site in this window: a loop of refreshes, or of page opens while billing is down,
# reuses the last result instead of tying up a worker for the 10 second timeout each time.
LAST_PULL_KEY = "books_subscription_last_pull"
PULL_INTERVAL_SECONDS = 10
PULL_PENDING = "pending"
RETURN_PATH = "/books/subscription?checkout=returned"
UNSUBSCRIBABLE_PHASES = ("unmanaged", "exempt")


# POST too: /books calls every method with a POST, and a POST commits what the pull applied.
@frappe.whitelist(methods=["GET", "POST"])
def get_subscription(refresh: bool = False, with_plans: bool = True) -> dict:
	"""The status dict, plus the plans for those who can subscribe. Allowed on a locked site.

	`refresh` pulls fresh state from the control site first, as on the return from checkout (AC-12).
	`with_plans=False` gives the status alone and never calls the control site, whatever `refresh` says
	(spec 0007 AC-7): /books asks for it before it words a lock notice.
	"""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	if not with_plans:
		return current_clock().status()

	pull_error = None
	if refresh and clock.is_managed() and clock.can_subscribe():
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
	subscription_clock = current_clock()
	phase = subscription_clock.phase
	if phase in UNSUBSCRIBABLE_PHASES:
		frappe.throw(_("This site is not on a hosted plan."))
	if phase == "active":
		frappe.throw(_("Your subscription is active. Change your plan from your PayPal account."))
	starts_on = subscription_clock.subscription_starts_on
	if starts_on:
		# A second checkout would make a second subscription (spec 0008 AC-21).
		frappe.throw(_("Your PayPal subscription starts on {0}.").format(formatdate(starts_on)))
	if subscription_clock.first_payment_overdue:
		frappe.throw(
			_("Your first PayPal payment hasn't arrived. Check the payment method in your PayPal account.")
		)

	provider, periods = offered_plan()
	if not provider:
		frappe.throw(_("Finish setup first."))
	if billing_period not in periods:
		frappe.throw(_("{0} billing isn't offered for this site.").format(_(billing_period)))

	checkout_url = _request_checkout(provider, billing_period)
	mark_checkout_started()
	return {"checkout_url": checkout_url}


def _refusal_message(code: str, billing_period: str) -> str:
	"""The message for each spec 0008 AC-5 refusal code. An unknown code is logged and reads as an outage."""
	if code == "plan_not_offered":
		return _("{0} billing isn't offered for this site.").format(_(billing_period))
	if code == "already_subscribed":
		return _("You already have an active PayPal subscription. Change your plan from your PayPal account.")
	if code == "being_removed":
		return _("This site is being removed, so it can't be paid for here. Contact support.")
	frappe.log_error("Books billing: create_checkout refused with an unknown code", code, defer_insert=True)
	return unreachable_message()


def _request_checkout(provider: str, billing_period: str) -> str:
	"""The control site's checkout link. Its failure is thrown with a message the user sees (AC-16)."""
	payload = {"provider": provider, "billing_period": billing_period, "return_url": get_url(RETURN_PATH)}
	try:
		response = call_control(CREATE_CHECKOUT, {**payload, **site_facts()})
	except ControlRefusal as refusal:
		frappe.throw(_refusal_message(refusal.code, billing_period))
	except ControlSiteUnreachable:
		response = None

	checkout_url = response.get("checkout_url") if response is not None else None
	if not is_trusted_link(checkout_url):
		# When the control site answered, its answer is wrong: log why, then treat it like an outage.
		if isinstance(checkout_url, str) and checkout_url:
			frappe.log_error("Books billing: create_checkout sent a link that isn't https", defer_insert=True)
		elif response is not None:
			frappe.log_error("Books billing: create_checkout sent no checkout link", defer_insert=True)
		# A plain raise sends no message, so /books would show a generic server error.
		frappe.throw(unreachable_message(), ControlSiteUnreachable)
	return checkout_url


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

	# Only a bad value answers 400. Any other failure propagates, so Frappe rolls back and answers 500,
	# and the control site retries it (spec 0007 AC-2).
	try:
		applied = apply_synced_state(state, issued_at)
	except InvalidPushError as error:
		_reject_push(str(error))
	if applied:
		# The next page open pulls fresh, rather than showing a Retry from before this push.
		frappe.cache.delete_value(LAST_PULL_KEY)
	return {"result": "applied" if applied else "ignored"}


def pull_state():
	"""Fetch this site's state and plans from the control site, and apply the state like a push.

	Raises `ControlSiteUnreachable` when the control site can't be reached or answers badly.
	"""
	sent = issued_now()
	try:
		response = call_control(GET_STATE, {"issued_at": sent, **site_facts()})
	except ControlRefusal as refusal:
		# `config_pending` means the control site hasn't confirmed this site's config yet (spec 0011 AC-5): no
		# state change, as if unreachable. Any other refusal is a broken answer (spec 0008 AC-2).
		if refusal.code != "config_pending":
			frappe.log_error("Books billing: get_state answered with a refusal", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message()) from None
	state, plans = response.get("state"), response.get("plans")
	# The answer must echo this request's own `issued_at` (spec 0008 AC-21), so a replayed or older signed
	# answer can't be applied. The echo is this site's own clock, so it is always inside the 5 minute window.
	echoed = state.get("issued_at") if isinstance(state, dict) else None
	if echoed != sent or not isinstance(plans, list):
		raise ControlSiteUnreachable(unreachable_message())
	issued_at = parse_issued_at(sent)

	try:
		applied = apply_synced_state(state, issued_at)
	except InvalidPushError:
		frappe.log_error("Books billing: get_state sent a bad value", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message()) from None

	frappe.cache.set_value(PLANS_CACHE_KEY, _valid_plans(plans), expires_in_sec=PLANS_CACHE_SECONDS)
	if applied:
		# A GET doesn't commit by itself.
		frappe.local.flags.commit = True


def _pull_and_report() -> str | None:
	"""Pull, and return the Retry message instead of raising, so the stored state still shows (AC-16).

	One pull per site per `PULL_INTERVAL_SECONDS`: the caller claims the window atomically first, so calls
	that arrive together, or while that pull waits on a slow control site, never call billing again.
	They get the last result, or the Retry message while the pull is still pending.
	"""
	if not _claim_pull_window():
		last = frappe.cache.get_value(LAST_PULL_KEY, expires=True, use_local_cache=False)
		if last is None or last == PULL_PENDING:
			return unreachable_message()
		return last or None

	error = None
	try:
		pull_state()
	except ControlSiteUnreachable:
		frappe.clear_messages()
		error = unreachable_message()
	except BaseException:
		# Any other failure (a lock wait timeout, a deadlock) propagates as a 500. Free the window first,
		# so the next refresh pulls again instead of reading `pending` until the window ends.
		frappe.cache.delete_value(LAST_PULL_KEY)
		raise
	frappe.cache.set_value(LAST_PULL_KEY, error or "", expires_in_sec=PULL_INTERVAL_SECONDS)
	return error


def _claim_pull_window() -> bool:
	"""Set the last pull key to pending only if it is absent (Redis SET NX), so one caller wins the window."""
	key = frappe.cache.make_key(LAST_PULL_KEY)
	value = pickle.dumps(PULL_PENDING)
	return bool(frappe.cache.set(key, value, ex=PULL_INTERVAL_SECONDS, nx=True))


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
