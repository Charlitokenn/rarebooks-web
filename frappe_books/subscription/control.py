"""The signed contract with the control site (spec 0005): signing, the `issued_at` window and outgoing calls.

Every body is signed as `sha256=` + hex HMAC SHA256 of its exact bytes under `books_control_secret`,
sent in the `X-Books-Signature` header both ways.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import frappe
import requests
from frappe import _

from frappe_books.subscription.clock import utc_now

SIGNATURE_HEADER = "X-Books-Signature"
SIGNATURE_PREFIX = "sha256="
ISSUED_AT_WINDOW = timedelta(minutes=5)
TIMEOUT_SECONDS = 10
GET_STATE = "rarebooks_control.api.get_state"
CREATE_CHECKOUT = "rarebooks_control.api.create_checkout"


class ControlSiteUnreachable(frappe.ValidationError):
	"""The control site timed out, failed, or answered without a valid signature (AC-16)."""


def unreachable_message() -> str:
	return _("Couldn't reach billing. Try again.")


def site_secret() -> bytes | None:
	secret = frappe.conf.get("books_control_secret")
	return secret.encode() if secret else None


def sign(body: bytes, secret: bytes) -> str:
	return SIGNATURE_PREFIX + hmac.new(secret, body, hashlib.sha256).hexdigest()


def is_valid_signature(body: bytes, signature: str | None, secret: bytes | None) -> bool:
	if not secret or not signature:
		return False
	return hmac.compare_digest(sign(body, secret), signature)


def parse_issued_at(value) -> datetime | None:
	"""Naive UTC for an ISO 8601 timestamp that carries a time zone; None for a naive or bad one."""
	if not isinstance(value, str):
		return None
	try:
		issued = datetime.fromisoformat(value)
	except ValueError:
		return None
	if issued.tzinfo is None:
		return None
	return issued.astimezone(UTC).replace(tzinfo=None)


def is_fresh(issued_at: datetime) -> bool:
	return abs(utc_now() - issued_at) <= ISSUED_AT_WINDOW


def issued_now() -> str:
	return datetime.now(UTC).isoformat()


def call_control(method: str, payload: dict) -> dict:
	"""POST a signed body to the control site and return its verified response.

	Raises `ControlSiteUnreachable` on a connection error, a timeout, an error status or a bad signature.
	"""
	url, secret = control_url(), site_secret()
	if not url or not secret:
		raise ControlSiteUnreachable(unreachable_message())

	body = json.dumps({"site": frappe.local.site, "issued_at": issued_now(), **payload}).encode()
	try:
		response = requests.post(
			f"{url}/api/method/{method}",
			data=body,
			headers={"Content-Type": "application/json", SIGNATURE_HEADER: sign(body, secret)},
			timeout=TIMEOUT_SECONDS,
		)
		response.raise_for_status()
	except requests.RequestException:
		frappe.log_error(f"Books billing: {method} failed", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message()) from None

	if not is_valid_signature(response.content, response.headers.get(SIGNATURE_HEADER), secret):
		frappe.log_error(f"Books billing: {method} answered without a valid signature", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message())

	try:
		data = json.loads(response.content)
	except ValueError:
		raise ControlSiteUnreachable(unreachable_message()) from None
	# A Frappe whitelisted method wraps its return value in `message`.
	message = data.get("message", data) if isinstance(data, dict) else None
	if not isinstance(message, dict):
		raise ControlSiteUnreachable(unreachable_message())
	return message


def control_url() -> str | None:
	"""The control site's base URL. Only `https://` is trusted, unless developer mode is on."""
	url = (frappe.conf.get("books_control_url") or "").rstrip("/")
	if not url:
		return None
	if not url.startswith("https://") and not frappe.conf.get("developer_mode"):
		return None
	return url
