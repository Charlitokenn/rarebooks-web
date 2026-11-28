"""Who gets a push, in which language, and the job that sends it (spec 0026 AC-5, AC-9, AC-10)."""

from collections.abc import Callable

import frappe
from frappe.exceptions import InReadOnlyMode

from frappe_books.notifications import fcm
from frappe_books.notifications.devices import DOCTYPE as DEVICE_DOCTYPE

SETTINGS = "Books Notification Settings"
RECIPIENT_ROLES = ("Books Manager", "System Manager")
JOB = "frappe_books.notifications.send_job"
JOB_TIMEOUT = 120

# A message builder takes the recipient's language and returns its title, body, link and tag.
MessageBuilder = Callable[[str], dict]


EVENTS = ("payment_received", "low_stock", "subscription")


def store_default_events():
	"""Store every event switch as on, keeping any value already set (spec 0026 AC-8).

	Frappe fills a single's defaults only while none of its values is stored, and the hourly job stores
	`last_subscription_phase` on every site. Without this, the Settings tab would show unset switches off
	(and a save would turn them off) while the server still sends.
	"""
	stored = frappe.db.get_singles_dict(SETTINGS)
	for fieldname in EVENTS:
		if stored.get(fieldname) is None:
			frappe.db.set_single_value(SETTINGS, fieldname, 1)


def event_enabled(fieldname: str) -> bool:
	"""A Books Notification Settings checkbox; an unset value counts as on (AC-8)."""
	value = frappe.db.get_singles_dict(SETTINGS).get(fieldname)
	return value is None or str(value) not in ("0", "")


def recipients(exclude_user: str | None = None) -> dict[str, list[str]]:
	"""Device names by language for the enabled Managers and System Managers (AC-5)."""
	users = set(
		frappe.get_all(
			"Has Role",
			filters={"role": ["in", RECIPIENT_ROLES], "parenttype": "User"},
			pluck="parent",
		)
	)
	users.discard(exclude_user)
	if not users:
		return {}

	devices = frappe.get_all(
		DEVICE_DOCTYPE, filters={"user": ["in", sorted(users)]}, fields=["name", "user"], order_by="name"
	)
	if not devices:
		return {}

	enabled = frappe.get_all(
		"User",
		filters={"name": ["in", sorted({device.user for device in devices})], "enabled": 1},
		fields=["name", "language"],
	)
	site_language = frappe.db.get_single_value("System Settings", "language") or "en"
	languages = {user.name: user.language or site_language for user in enabled}

	by_language: dict[str, list[str]] = {}
	for device in devices:
		if device.user in languages:
			by_language.setdefault(languages[device.user], []).append(device.name)
	return by_language


def build_messages(build: MessageBuilder, exclude_user: str | None = None) -> list[dict]:
	"""One message per device, each written once per language (AC-9)."""
	messages = []
	for language, devices in recipients(exclude_user).items():
		message = build(language)
		messages.extend({"device": device, **message} for device in devices)
	return messages


def notify(build: MessageBuilder, exclude_user: str | None = None):
	"""Queue the push for after the commit, so a rolled back submit sends nothing (AC-10)."""
	if not fcm.is_configured():
		return
	messages = build_messages(build, exclude_user)
	if messages:
		frappe.enqueue(
			JOB,
			queue="short",
			timeout=JOB_TIMEOUT,
			enqueue_after_commit=True,
			messages=messages,
		)


def send_now(build: MessageBuilder) -> bool:
	"""Send inside the current job, for the scheduled subscription push (AC-7, AC-10).

	Returns False when Google refused every send, so the caller can try again next run.
	"""
	if not fcm.is_configured():
		return True
	messages = build_messages(build)
	if not messages:
		return True
	return send_job(messages)


def send_job(messages: list[dict]) -> bool:
	"""Send each message to its device, delete the dead ones and log any failure once (AC-10).

	Nothing is retried. Returns whether at least one push went out (or none was needed).
	"""
	if not messages or not fcm.is_configured():
		return True
	try:
		# One exchange up front: a bad key fails the job once, not once per device.
		fcm.access_token()
	except fcm.FcmError as error:
		_log_failures([error], len(messages))
		return False

	tokens = dict(
		frappe.get_all(
			DEVICE_DOCTYPE,
			filters={"name": ["in", sorted({message["device"] for message in messages})]},
			fields=["name", "token"],
			as_list=True,
		)
	)
	dead, failures, sent = [], [], 0
	for message in messages:
		token = tokens.get(message["device"])
		if not token:
			continue
		outcome = fcm.send(token, message["title"], message["body"], message["link"], message["tag"])
		if outcome == fcm.SENT:
			sent += 1
		elif outcome == fcm.DEAD:
			dead.append(message["device"])
		else:
			failures.append(outcome)

	_delete_dead(dead)
	if failures:
		_log_failures(failures, len(messages))
	return sent > 0 or not failures


def _delete_dead(names: list[str]):
	if not names:
		return
	try:
		frappe.db.delete(DEVICE_DOCTYPE, {"name": ["in", names]})
	except InReadOnlyMode:
		# A locked site's job can't write; the next send tries the delete again.
		pass


def _log_failures(failures: list, total: int):
	"""Only the HTTP status and FCM's error code: never a token, a request or a key (AC-10, AC-12)."""
	lines = [
		f"status {getattr(outcome, 'status', None)}, code {getattr(outcome, 'code', None)}"
		for outcome in failures
	]
	try:
		frappe.log_error(
			title=f"Books push: {len(failures)} of {total} sends failed",
			message="\n".join(sorted(set(lines))),
		)
	except InReadOnlyMode:
		frappe.logger("frappe_books.notifications").warning("Books push failed: %s", "; ".join(lines))
