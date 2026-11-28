"""The devices a user turned push notifications on for (spec 0026 AC-2, AC-3, AC-4, AC-13, AC-14)."""

import hashlib
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import now_datetime

from frappe_books.notifications import fcm
from frappe_books.subscription.lock import SiteLockedError
from frappe_books.support_chat import EXCLUDED_USERS, has_real_email

DOCTYPE = "Books Push Device"
DEVICE_ROLES = ("Books Manager", "Books User", "Books Cashier", "System Manager")
MAX_DEVICES = 10
# A start up register within this long of the last one writes nothing (AC-3).
SEEN_SKIP = timedelta(hours=1)
STALE_AFTER = timedelta(days=90)
LABEL_LIMIT = 140
# FCM tokens are about 160 characters; anything far longer is not one.
TOKEN_LIMIT = 4096


@frappe.whitelist(methods=["POST"])
def register_device(token: str, previous_token: str | None = None, device_label: str | None = None) -> dict:
	"""Store this browser's FCM token for the session user (AC-3)."""
	_check_push_on()
	user = frappe.session.user
	if not can_use_push(user):
		frappe.throw(_("Notifications are not available for this user."), frappe.PermissionError)
	if frappe.flags.books_site_locked:
		frappe.throw(_("This site is read only. Subscribe to make changes again."), SiteLockedError)

	token = _clean_token(token)
	label = (device_label or "").strip()[:LABEL_LIMIT]
	token_hash = hash_token(token)
	now = now_datetime()

	# FCM rotated the token: the old one's row goes, so the device is not sent to twice.
	if previous_token and previous_token != token:
		frappe.db.delete(DOCTYPE, {"token_hash": hash_token(previous_token), "user": user})

	row = frappe.db.get_value(
		DOCTYPE, {"token_hash": token_hash}, ["name", "user", "device_label", "last_seen"], as_dict=True
	)
	if row and row.user == user and row.device_label == label and now - row.last_seen < SEEN_SKIP:
		return {"name": row.name}

	if row:
		# A token belongs to one user: whoever registers it last on this browser gets its pushes.
		frappe.db.set_value(
			DOCTYPE, row.name, {"user": user, "device_label": label, "last_seen": now}, update_modified=False
		)
		name = row.name
	else:
		device = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"user": user,
				"token": token,
				"token_hash": token_hash,
				"device_label": label,
				"last_seen": now,
			}
		)
		device.insert(ignore_permissions=True)
		name = device.name

	_keep_newest_devices(user)
	return {"name": name}


@frappe.whitelist(methods=["POST"])
def unregister_device(token: str) -> dict:
	"""Delete this browser's row, only when it is the caller's (AC-4)."""
	_check_push_on()
	# A locked site can't write; the browser has dropped its subscription, and FCM's
	# UNREGISTERED answer deletes the row later (AC-13).
	if frappe.flags.books_site_locked or not token:
		return {"deleted": False}

	filters = {"token_hash": hash_token(token), "user": frappe.session.user}
	if not frappe.db.exists(DOCTYPE, filters):
		return {"deleted": False}
	frappe.db.delete(DOCTYPE, filters)
	return {"deleted": True}


def boot_block() -> dict | None:
	"""`books.push` in the boot: the public Firebase config, or None when push is off (AC-1, AC-12).

	Never raises. The service account key is never read here.
	"""
	try:
		if not fcm.is_configured() or not can_use_push(frappe.session.user):
			return None
		config = fcm.web_config()
		vapid_key = fcm.vapid_key()
		if not config or not vapid_key:
			return None
		return {"web_config": config, "vapid_key": vapid_key}
	except Exception:
		frappe.logger("frappe_books.notifications").warning(
			"Push is off: its boot block failed", exc_info=True
		)
		return None


def can_use_push(user: str) -> bool:
	"""A real person with a Books role (AC-2): the same email rule as the support chat (spec 0009 AC-2)."""
	if not user or user in EXCLUDED_USERS:
		return False
	if not has_real_email(frappe.db.get_value("User", user, "email")):
		return False
	return bool(set(frappe.get_roles(user)) & set(DEVICE_ROLES))


def hash_token(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def delete_stale_devices():
	"""Daily job: a device not seen for 90 days is gone (AC-14)."""
	frappe.db.delete(DOCTYPE, {"last_seen": ["<", now_datetime() - STALE_AFTER]})


def get_permission_query_conditions(user: str | None = None) -> str:
	"""A user lists only their own devices, whatever their role (security model)."""
	user = user or frappe.session.user
	return f"`tab{DOCTYPE}`.`user` = {frappe.db.escape(user)}"


def has_permission(doc, ptype: str | None = None, user: str | None = None, debug=False) -> bool:
	# Follows `user`, not `owner`: a reassigned row keeps its old owner.
	return doc.user == (user or frappe.session.user)


def _check_push_on():
	if not fcm.is_configured():
		frappe.throw(_("Notifications are not set up on this site."), frappe.PermissionError)


def _clean_token(token: str) -> str:
	token = (token or "").strip()
	if not token or len(token) > TOKEN_LIMIT:
		frappe.throw(_("This device could not be registered for notifications."))
	return token


def _keep_newest_devices(user: str):
	"""At most 10 devices a user: an eleventh replaces the one seen longest ago (AC-3)."""
	names = frappe.get_all(
		DOCTYPE, filters={"user": user}, order_by="last_seen desc, creation desc", pluck="name"
	)
	extra = names[MAX_DEVICES:]
	if extra:
		frappe.db.delete(DOCTYPE, {"name": ["in", extra]})
