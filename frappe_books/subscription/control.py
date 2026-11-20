"""The signed contract with the control site (specs 0005 and 0008): signing, the `issued_at` window and
outgoing calls.

Every body is signed as `sha256=` + hex HMAC SHA256 of its exact bytes under `books_control_secret`,
sent in the `X-Books-Signature` header both ways. The control site signs its refusals and auth failures
too, so the signature is checked before the status (spec 0008 AC-5, AC-21).
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import frappe
import requests
from frappe import _

from frappe_books.settings import company_name
from frappe_books.subscription.clock import current_clock, utc_now

SIGNATURE_HEADER = "X-Books-Signature"
SIGNATURE_PREFIX = "sha256="
ISSUED_AT_WINDOW = timedelta(minutes=5)
TIMEOUT_SECONDS = 10
GET_STATE = "rarebooks_control.api.get_state"
CREATE_CHECKOUT = "rarebooks_control.api.create_checkout"
REFUSAL_STATUS = 409


class ControlSiteUnreachable(frappe.ValidationError):
	"""The control site timed out, failed, or answered without a valid signature (AC-16)."""


class ControlRefusal(Exception):
	"""A signed 409 from the control site: it heard the call and said no, with a `refusal` code (spec 0008 AC-5)."""

	def __init__(self, code: str):
		super().__init__(code)
		self.code = code


def unreachable_message() -> str:
	return _("Couldn't reach billing. Try again.")


def site_secret() -> bytes | None:
	secret = frappe.conf.get("books_control_secret")
	return secret.encode() if secret else None


def sign(body: bytes, secret: bytes) -> str:
	return SIGNATURE_PREFIX + hmac.new(secret, body, hashlib.sha256).hexdigest()


def is_valid_signature(body: bytes, signature: str | None, secret: bytes | None) -> bool:
	if not secret or not isinstance(signature, str) or not signature:
		return False
	# Compare bytes: compare_digest raises TypeError on a str holding non ASCII characters, and the header
	# is the caller's, so a forged one must answer 401, not 500 (spec 0005 AC-11, spec 0008 AC-5).
	return hmac.compare_digest(sign(body, secret).encode(), signature.encode("utf-8", "surrogatepass"))


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
	"""POST a signed body to the control site and return its verified answer.

	`payload` may carry its own `issued_at`, so the caller can check the answer echoes it. Raises
	`ControlRefusal` on a signed 409 that carries a `refusal` code, and `ControlSiteUnreachable` on a
	connection error, a timeout, a bad signature, or any other status.
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
	except requests.RequestException:
		frappe.log_error(f"Books billing: {method} failed", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message()) from None

	# Before the status: an unsigned 409 is no refusal, just a failure.
	if not is_valid_signature(response.content, response.headers.get(SIGNATURE_HEADER), secret):
		frappe.log_error(f"Books billing: {method} answered without a valid signature", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message())

	message = _answer(response.content)
	if response.status_code == REFUSAL_STATUS and message and isinstance(message.get("refusal"), str):
		raise ControlRefusal(message["refusal"])
	if response.status_code != 200 or message is None:
		frappe.log_error(f"Books billing: {method} answered {response.status_code}", defer_insert=True)
		raise ControlSiteUnreachable(unreachable_message())
	return message


def site_facts() -> dict:
	"""The four facts the control site keeps for its dates and emails (spec 0008 AC-21), in every pull and checkout."""
	return {
		"trial_ends_on": current_clock().status()["trial_ends_on"],
		"time_zone": frappe.get_system_settings("time_zone") or None,
		"language": frappe.get_system_settings("language") or None,
		"company_name": company_name(),
	}


def _answer(content: bytes) -> dict | None:
	"""The JSON object of a verified answer, or None when it isn't one."""
	try:
		data = json.loads(content)
	except ValueError:
		return None
	# A Frappe whitelisted method wraps its return value in `message`; spec 0008's signed answers don't.
	message = data.get("message", data) if isinstance(data, dict) else None
	return message if isinstance(message, dict) else None


def control_url() -> str | None:
	"""The control site's base URL. Only `https://` is trusted, unless developer mode is on."""
	url = (frappe.conf.get("books_control_url") or "").rstrip("/")
	if not url:
		return None
	return url if is_trusted_link(url) else None


def is_trusted_link(url) -> bool:
	"""`https://` always, `http://` only in developer mode. The control URL and checkout links share this rule."""
	if not isinstance(url, str):
		return False
	return url.startswith("https://") or (
		url.startswith("http://") and bool(frappe.conf.get("developer_mode"))
	)
