"""The PostHog block in the /books boot (spec 0027).

Only a hosted site with the PostHog key and salt in its config, and analytics
left on in Books System Settings, sends anything. A person is a keyed hash of
the site and user, so no email ever reaches PostHog; the salt never leaves the server.
"""

import hashlib
import hmac

import frappe

from frappe_books.settings import regional_code

BOOKS_ROLES = ("Books Cashier", "Books Manager", "Books User")
SETTINGS = "Books System Settings"
# The first 32 hex characters (128 bits) of the HMAC are the person id (AC-2).
ID_LENGTH = 32


def boot_block() -> dict | None:
	"""The PostHog settings for the signed in user, or None when analytics is off (AC-1).

	Never raises: a failure logs a warning (not an Error Log, which a locked
	site's read only transaction can't write) and turns analytics off.
	"""
	try:
		return _build_block()
	except Exception:
		frappe.logger("frappe_books.analytics").warning(
			"Usage analytics is off: its boot block could not be built", exc_info=True
		)
		return None


def _build_block() -> dict | None:
	conf = frappe.conf
	# Self hosted sites have no control site and never send anything.
	if not conf.get("books_control_url"):
		return None
	key, salt = conf.get("books_posthog_key"), conf.get("books_posthog_salt")
	if not key or not salt:
		return None
	if not frappe.db.get_single_value(SETTINGS, "share_usage_analytics"):
		return None

	user = frappe.session.user
	if user in ("Administrator", "Guest"):
		return None
	roles = sorted(set(frappe.get_roles(user)) & set(BOOKS_ROLES))
	if not roles:
		return None

	return {
		"key": key,
		"distinct_id": person_id(salt, frappe.local.site, user),
		"site_key": frappe.local.site,
		"roles": roles,
		"country_code": regional_code(),
		"language": frappe.local.lang,
	}


def person_id(salt: str, site: str, user: str) -> str:
	"""The same user on the same site always gets the same id, and the id never shows the email (AC-2)."""
	digest = hmac.new(salt.encode(), f"{site}:{user}".encode(), hashlib.sha256).hexdigest()
	return digest[:ID_LENGTH]
