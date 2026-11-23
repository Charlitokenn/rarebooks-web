"""The control site's signed calls that hand a pool site to its owner (spec 0014 AC-22 to AC-24).

A pool site is built before anyone signs up. When a sign up claims it, the control site calls `claim_site`
to make the owner and restart the trial clock, then `owner_link` for the first sign in link once the site's
subdomain address is primary. Before it ever discards a site it reads `claim_report`, so a site whose owner
has logged in is never thrown away (AC-19). Every call is signed like the other control site calls in
`remote.py`, and every answer, a 401 included, is signed and echoes the request's `issued_at`.
"""

from urllib.parse import urlsplit

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address
from frappe.utils.momentjs import get_all_timezones
from werkzeug.wrappers import Response

from frappe_books.subscription import state
from frappe_books.subscription.remote import BAD_REQUEST, CALLS_PER_MINUTE, _verified

CONFLICT = 409
OWNER_ROLES = ("Books Manager", "System Manager")
# Stored as global defaults, so the session boot carries the company to the setup wizard (AC-24).
COMPANY_DEFAULT = "books_signup_company"
OWNER_DEFAULT = "books_signup_owner"
COMPANY_NAME_MAX = 140
NAME_MAX = 140
DEFAULT_ZONE = "UTC"


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def claim_site() -> Response:
	"""Make the owner, set the site's time zone and company, and start the trial today (AC-22).

	Safe to repeat with the same email; refuses once anyone else owns the site, so a replay can't add a second
	owner.
	"""
	call = _verified()
	if isinstance(call, Response):
		return call
	claim = _claim_values(call.body)
	if claim is None:
		return call.answer({"status": "bad_request"}, BAD_REQUEST)

	others = [user for user in _system_users() if user != claim["owner_email"]]
	if others:
		return call.answer({"status": "owned"}, CONFLICT)
	if frappe.db.exists("User", claim["owner_email"]):
		return call.answer({"status": "claimed"})

	_set_time_zone(claim["time_zone"])
	_make_owner(claim)
	frappe.db.set_default(COMPANY_DEFAULT, claim["company_name"])
	frappe.db.set_default(OWNER_DEFAULT, claim["owner_email"])
	# After the time zone, so day 1 is the claim date in the owner's zone (AC-22, AC-24).
	state.restart_trial_at_claim()
	return call.answer({"status": "claimed"})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def owner_link() -> Response:
	"""The owner's first sign in link: a fresh password set link until they have one, then `/login` (AC-23).

	The link is never logged: it travels only in this signed answer and the marketing site's redirect.
	"""
	call = _verified()
	if isinstance(call, Response):
		return call
	owner = _owner()
	host = _primary_host()
	if not owner or not host:
		return call.answer({"status": "not_ready"}, CONFLICT)

	user = frappe.get_doc("User", owner)
	if not user.last_password_reset_date and not user.last_login:
		# Each call makes a new key, so an older link stops working.
		return call.answer({"url": user._reset_password(send_email=False), "password_set": False})
	return call.answer({"url": f"{host}/login", "password_set": True})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def claim_report() -> Response:
	"""Who owns this site and whether they ever logged in, read before any discard (AC-19, AC-23). Read only."""
	call = _verified()
	if isinstance(call, Response):
		return call
	owner = _owner()
	logged_in = bool(owner and frappe.db.get_value("User", owner, "last_login"))
	return call.answer({"owner_email": owner, "owner_logged_in": logged_in})


def _claim_values(body: dict) -> dict | None:
	"""The claim's values, trimmed, or None when one is missing or wrong. An unknown zone becomes UTC."""
	email, first_name = body.get("owner_email"), body.get("first_name")
	last_name, company, zone = body.get("last_name") or "", body.get("company_name"), body.get("time_zone")
	if not all(isinstance(value, str) for value in (email, first_name, last_name, company)):
		return None
	email, first_name, last_name, company = (v.strip() for v in (email, first_name, last_name, company))
	if not validate_email_address(email):
		return None
	if not (0 < len(first_name) <= NAME_MAX and len(last_name) <= NAME_MAX):
		return None
	if not 0 < len(company) <= COMPANY_NAME_MAX:
		return None
	return {
		"owner_email": email.lower(),
		"first_name": first_name,
		"last_name": last_name,
		"company_name": company,
		"time_zone": zone if isinstance(zone, str) and zone in get_all_timezones() else DEFAULT_ZONE,
	}


def _system_users() -> list[str]:
	"""Enabled System Users other than Administrator: anyone here means the site has an owner already."""
	return frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ("not in", ("Administrator", "Guest"))},
		pluck="name",
	)


def _set_time_zone(zone: str):
	"""Written as one field, not through `System Settings.save()`: a pool site claims before its setup wizard,
	while `language` and `time_zone` are still empty, and a save refuses them as mandatory (a 417 the control
	site counted as a failed owner step, found in the spec 0014 staging sign up). The rarebooks_control install
	does the same for two factor auth."""
	from frappe.core.doctype.system_settings.system_settings import clear_system_settings_cache

	frappe.db.set_single_value("System Settings", "time_zone", zone)
	clear_system_settings_cache()
	# The request keeps its own copy of System Settings; drop it so the trial reads the new zone.
	frappe.local.system_settings = None


def _make_owner(claim: dict):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": claim["owner_email"],
			"first_name": claim["first_name"],
			"last_name": claim["last_name"],
			"enabled": 1,
			"user_type": "System User",
			"send_welcome_email": 0,
			"time_zone": claim["time_zone"],
			"roles": [{"role": role} for role in OWNER_ROLES],
		}
	)
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)


def _owner() -> str | None:
	owner = frappe.db.get_default(OWNER_DEFAULT)
	return owner if owner and frappe.db.exists("User", owner) else None


def _primary_host() -> str | None:
	"""`https://` plus the site's `host_name`, once it is an address other than the pool site's own name.

	The control site sets `host_name` to the subdomain address in the Primary step (spec 0012 AC-8); before
	that the site answers on its Frappe Cloud name only, and a link there would be the wrong address.
	"""
	host_name = frappe.conf.get("host_name") or ""
	host = urlsplit(host_name if "://" in host_name else f"https://{host_name}").hostname
	if not host or host == frappe.local.site:
		return None
	return f"https://{host}"
