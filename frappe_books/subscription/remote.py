"""The control site's signed calls into this site (spec 0010 AC-2, AC-5, AC-17).

The control site drives removal over HTTPS: it reads this site's removal status, asks it to build and upload
its export, and writes or clears the two hold fields. Every call is a guest POST signed with
`books_control_secret` over the raw body, with an `issued_at` inside the 5 minute window. Every answer, a 401
included, is signed with the same secret and echoes the request's `issued_at`, so the control site can tell a
fresh answer from a replayed one. These run on a locked site too: the two writers are in `ALLOWED_METHODS`.
"""

import json
import re
from urllib.parse import urlsplit
from uuid import UUID

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from frappe_books.subscription import clock
from frappe_books.subscription.control import (
	SIGNATURE_HEADER,
	is_fresh,
	is_valid_signature,
	parse_issued_at,
	sign,
	site_secret,
)

UNAUTHORIZED, BAD_REQUEST = 401, 400
# Only Cloudflare R2's S3 endpoint may receive this site's export (spec 0010, value sourcing).
R2_HOST_SUFFIX = ".r2.cloudflarestorage.com"
# Case names go into a folder path and the job id, so only the control site's autoname shape is accepted.
CASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")
EXPORT_JOB = "frappe_books.subscription.removal.export_job"
EXPORT_JOB_TIMEOUT = 2 * 60 * 60
CALLS_PER_MINUTE = 60


class SignedCall:
	"""A verified call from the control site: its body, and the `issued_at` every answer echoes."""

	def __init__(self, body: dict):
		self.body = body
		self.issued_at = body["issued_at"]

	def answer(self, values: dict, status: int = 200) -> Response:
		return signed_answer({**values, "issued_at": self.issued_at}, status)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def removal_report() -> Response:
	"""This site's removal status, read fresh (spec 0007 AC-1). Read only."""
	from frappe_books.subscription.removal import removal_status

	call = _verified()
	if isinstance(call, Response):
		return call
	return call.answer(removal_status())


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def start_export() -> Response:
	"""Queue the export job for one upload attempt (AC-3). Safe to repeat: the job id is deduplicated."""
	call = _verified()
	if isinstance(call, Response):
		return call
	body = call.body
	case, attempt_id, upload_url = body.get("case"), body.get("attempt_id"), body.get("upload_url")
	expires_at = parse_issued_at(body.get("expires_at"))
	if not (_is_case(case) and _is_uuid(attempt_id) and is_upload_url(upload_url) and expires_at):
		return call.answer({"status": "bad_request"}, BAD_REQUEST)

	frappe.enqueue(
		EXPORT_JOB,
		queue="long",
		timeout=EXPORT_JOB_TIMEOUT,
		job_id=f"books-export:{case}:{attempt_id}",
		deduplicate=True,
		case=case,
		attempt_id=attempt_id,
		upload_url=upload_url,
		expires_at=body["expires_at"],
	)
	return call.answer({"status": "queued"})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def mark_export_sent() -> Response:
	"""Write the two hold fields (spec 0007 AC-8). Allowed on a locked site."""
	from frappe_books.subscription import removal

	call = _verified()
	if isinstance(call, Response):
		return call
	sent_on, hold_until = call.body.get("export_sent_on"), call.body.get("removal_hold_until")
	if not (parse_issued_at(sent_on) and parse_issued_at(hold_until)):
		return call.answer({"status": "bad_request"}, BAD_REQUEST)
	removal.mark_export_sent(sent_on, hold_until)
	return call.answer({"status": "marked"})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def clear_removal() -> Response:
	"""Empty both hold fields (spec 0007 AC-11). Safe when already empty. Allowed on a locked site."""
	from frappe_books.subscription import removal

	call = _verified()
	if isinstance(call, Response):
		return call
	removal.clear_removal()
	return call.answer({"status": "cleared"})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def control_ping() -> Response:
	"""Proves this site holds the secret the control site just wrote to its config (AC-11, AC-12)."""
	call = _verified()
	if isinstance(call, Response):
		return call
	return call.answer({"site": frappe.local.site, "status": "ok"})


def signed_answer(values: dict, status: int) -> Response:
	"""Serialize once and sign those exact bytes, so Frappe adds no `message` wrapper. Unsigned only when this
	site has no secret, which the control site treats as a failure."""
	data = json.dumps(values, separators=(",", ":"), default=str).encode()
	response = Response(data, status=status, content_type="application/json")
	secret = site_secret()
	if secret:
		response.headers[SIGNATURE_HEADER] = sign(data, secret)
	return response


def is_upload_url(value) -> bool:
	"""A presigned `https://` URL on R2's S3 endpoint, with no user info or port other than 443."""
	if not isinstance(value, str):
		return False
	try:
		parts = urlsplit(value)
		port = parts.port
	except ValueError:
		return False
	host = parts.hostname or ""
	return (
		parts.scheme == "https"
		and host.endswith(R2_HOST_SUFFIX)
		and parts.username is None
		and port in (None, 443)
	)


def _verified() -> SignedCall | Response:
	"""The call, when this site is hosted and the body is signed with its secret, names this site and is fresh.
	Anything else answers a signed 401 with no detail (AC-2)."""
	raw = frappe.request.get_data()
	try:
		body = json.loads(raw)
	except ValueError:
		body = None
	echo = body.get("issued_at") if isinstance(body, dict) else None
	refused = signed_answer({"issued_at": echo if isinstance(echo, str) else None}, UNAUTHORIZED)

	secret = site_secret()
	if not clock.is_managed() or not secret:
		return refused
	if not is_valid_signature(raw, frappe.get_request_header(SIGNATURE_HEADER), secret):
		return refused
	if not isinstance(body, dict) or body.get("site") != frappe.local.site:
		return refused
	issued_at = parse_issued_at(echo)
	if not issued_at or not is_fresh(issued_at):
		return refused
	return SignedCall(body)


def _is_case(value) -> bool:
	return isinstance(value, str) and bool(CASE_NAME.match(value))


def _is_uuid(value) -> bool:
	if not isinstance(value, str):
		return False
	try:
		return str(UUID(value)) == value
	except ValueError:
		return False
