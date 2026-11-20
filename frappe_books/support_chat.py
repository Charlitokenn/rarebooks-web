"""The tawk.to support chat block in the /books boot (spec 0009).

The server signs the visitor with the tawk.to Secure Mode API key, so a user
can't chat as someone else. The key is read only here and never leaves it.
"""

import hashlib
import hmac

import frappe

import frappe_books

CONFIG_KEYS = ("books_tawk_property_id", "books_tawk_widget_id", "books_tawk_api_key")
BOOKS_ROLES = ("Books Manager", "Books User", "Books Cashier")
EXCLUDED_USERS = ("Administrator", "Guest")
PLACEHOLDER_DOMAIN = "@example.com"
# tawk.to cuts custom attribute values at 255 characters.
ATTRIBUTE_LIMIT = 255


def boot_block() -> dict | None:
	"""The chat settings for the signed in user, or None when the chat is off.

	Never raises: a failure logs a warning (not an Error Log, which a locked
	site's read only transaction can't write) and turns the chat off.
	"""
	try:
		return _build_block()
	except Exception:
		frappe.logger("frappe_books.support_chat").warning(
			"Support chat is off: its boot block could not be built", exc_info=True
		)
		return None


def _build_block() -> dict | None:
	conf = frappe.conf
	if not all(conf.get(key) for key in CONFIG_KEYS):
		return None

	user = frappe.session.user
	if user in EXCLUDED_USERS:
		return None

	email, full_name = frappe.db.get_value("User", user, ["email", "full_name"]) or (None, None)
	if not has_real_email(email):
		return None

	block = {
		"property_id": conf.books_tawk_property_id,
		"widget_id": conf.books_tawk_widget_id,
		"visitor": {
			"name": full_name or email,
			"email": email,
			"hash": sign_email(conf.books_tawk_api_key, email),
		},
		"attributes": get_attributes(),
	}
	if conf.get("books_support_email"):
		block["support_email"] = conf.books_support_email
	return block


def has_real_email(email: str | None) -> bool:
	"""A placeholder address (empty, or at example.com) is no one support can answer."""
	normalized = (email or "").strip().lower()
	return bool(normalized) and not normalized.endswith(PLACEHOLDER_DOMAIN)


def sign_email(api_key: str, email: str) -> str:
	"""The tawk.to Secure Mode hash: lowercase hex HMAC SHA256 of the email."""
	return hmac.new(api_key.encode(), email.encode(), hashlib.sha256).hexdigest()


def get_attributes() -> dict:
	"""The custom attributes the server knows; the client adds `phase` and `screen`."""
	user_roles = set(frappe.get_roles())
	values = {
		"company": frappe.db.get_single_value("Books Accounting Settings", "company_name"),
		"site": frappe.local.site,
		"roles": ", ".join(role for role in BOOKS_ROLES if role in user_roles),
		"app-version": frappe_books.__version__,
	}
	return {key: str(value)[:ATTRIBUTE_LIMIT] for key, value in values.items() if value}
