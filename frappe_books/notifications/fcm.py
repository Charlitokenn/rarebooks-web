"""Firebase Cloud Messaging HTTP v1 (spec 0026). The only module that talks to Google.

The service account key holds a private key: it is read here only and never logged, returned or put in
the boot (AC-12). Errors carry only the HTTP status and FCM's error code, never a token or the request.
"""

import json
import time

import frappe
import jwt
import requests

CONFIG_KEYS = ("books_fcm_service_account", "books_fcm_web_config", "books_fcm_vapid_key")
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
TOKEN_CACHE_KEY = "books_fcm_access_token"
# A cached token is dropped this long before Google expires it, so a send never carries a stale one.
TOKEN_MARGIN_SECONDS = 300
TIMEOUT_SECONDS = 10
# A shown notification may wait a day for a phone that is off; later it is no news.
TTL_SECONDS = 86400

SENT = "sent"
DEAD = "dead"
FAILED = "failed"


class FcmError(Exception):
	"""A call to Google that failed, with only what may be logged."""

	def __init__(self, status: int | None, code: str | None):
		super().__init__(f"status {status}, code {code}")
		self.status = status
		self.code = code


class Outcome(str):
	"""`sent`, `dead` or `failed`, with the HTTP status and FCM error code of a failure for the log."""

	status: int | None = None
	code: str | None = None

	def __new__(cls, value: str, status: int | None = None, code: str | None = None):
		outcome = super().__new__(cls, value)
		outcome.status = status
		outcome.code = code
		return outcome


def is_configured() -> bool:
	"""Push is on only when all three keys are in the site config (AC-1)."""
	return all(frappe.conf.get(key) for key in CONFIG_KEYS)


def web_config() -> dict:
	"""The public Firebase web app config. A JSON string or an object in site config."""
	return _as_dict(frappe.conf.get("books_fcm_web_config"))


def vapid_key() -> str:
	return str(frappe.conf.get("books_fcm_vapid_key") or "")


def access_token() -> str:
	"""A Google OAuth access token for FCM, minted from the service account and cached per site.

	Raises FcmError on any failure. Two jobs that miss the cache at once both exchange, which is harmless.
	"""
	cached = frappe.cache.get_value(TOKEN_CACHE_KEY, expires=True)
	if cached:
		return cached

	account = _service_account()
	now = int(time.time())
	assertion = jwt.encode(
		{
			"iss": account["client_email"],
			"scope": SCOPE,
			"aud": TOKEN_URL,
			"iat": now,
			"exp": now + 3600,
		},
		account["private_key"],
		algorithm="RS256",
	)
	try:
		response = requests.post(
			TOKEN_URL,
			data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
			timeout=TIMEOUT_SECONDS,
		)
	except requests.RequestException:
		raise FcmError(None, "timeout") from None

	if response.status_code != 200:
		raise FcmError(response.status_code, _oauth_error_code(response))

	body = _json(response)
	token = body.get("access_token")
	if not token:
		raise FcmError(response.status_code, "no_access_token")
	expires_in = int(body.get("expires_in") or 3600)
	frappe.cache.set_value(TOKEN_CACHE_KEY, token, expires_in_sec=max(expires_in - TOKEN_MARGIN_SECONDS, 60))
	return token


def send(token: str, title: str, body: str, link: str, tag: str) -> Outcome:
	"""Send one push to one device: `sent`, `dead` (the token is gone, delete its row) or `failed`.

	A data only message: the /books service worker shows it, so the page never doubles it (AC-11).
	"""
	try:
		bearer = access_token()
	except FcmError as error:
		return Outcome(FAILED, error.status, error.code)

	message = {
		"message": {
			"token": token,
			"data": {"title": title, "body": body, "link": link, "tag": tag},
			"webpush": {"headers": {"Urgency": "high", "TTL": str(TTL_SECONDS)}},
		}
	}
	try:
		response = requests.post(
			SEND_URL.format(project_id=_service_account()["project_id"]),
			json=message,
			headers={"Authorization": f"Bearer {bearer}"},
			timeout=TIMEOUT_SECONDS,
			allow_redirects=False,
		)
	except requests.RequestException:
		return Outcome(FAILED, None, "timeout")

	return _outcome(response)


def _outcome(response) -> Outcome:
	status = response.status_code
	if status == 200:
		return Outcome(SENT, status)

	error = _json(response).get("error") or {}
	details = error.get("details") or []
	code = _fcm_error_code(details) or error.get("status")
	if status == 404 and code == "UNREGISTERED":
		return Outcome(DEAD, status, code)
	if status == 400 and error.get("status") == "INVALID_ARGUMENT" and _names_token(details):
		return Outcome(DEAD, status, code)
	return Outcome(FAILED, status, code)


def _fcm_error_code(details: list) -> str | None:
	for detail in details:
		if isinstance(detail, dict) and detail.get("errorCode"):
			return str(detail["errorCode"])
	return None


def _names_token(details: list) -> bool:
	for detail in details:
		if not isinstance(detail, dict):
			continue
		for violation in detail.get("fieldViolations") or []:
			if isinstance(violation, dict) and violation.get("field") == "message.token":
				return True
	return False


def _oauth_error_code(response) -> str | None:
	# OAuth answers {"error": "invalid_grant", ...}: a code only, safe to log.
	error = _json(response).get("error")
	return error if isinstance(error, str) else None


def _service_account() -> dict:
	account = _as_dict(frappe.conf.get("books_fcm_service_account"))
	if not all(account.get(key) for key in ("project_id", "client_email", "private_key")):
		raise FcmError(None, "bad_service_account")
	return account


def _as_dict(value) -> dict:
	if isinstance(value, dict):
		return value
	try:
		parsed = json.loads(value or "{}")
	except (TypeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def _json(response) -> dict:
	try:
		body = response.json()
	except ValueError:
		return {}
	return body if isinstance(body, dict) else {}
