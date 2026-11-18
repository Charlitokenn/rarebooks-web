"""Helpers for the trial end export and removal tests (spec 0007): a signed control site stub for the runner,
a fake export storage, and a throwaway bench folder with its mode switch and secrets file."""

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

import frappe
import requests

from frappe_books.subscription.control import SIGNATURE_HEADER, is_valid_signature, sign
from frappe_books.tests.subscription import CONTROL_URL, iso_ago

RUNNER_SECRET = b"books-runner-secret-0123456789abcdef0123"
RUNNER_NAME = "bench-test-1"
ROOT_PASSWORD = "root-password-never-logged"
STORAGE = {
	"endpoint_url": "https://r2.example.com",
	"bucket": "books-exports",
	"access_key_id": "test-access-key-id",
	"secret_access_key": "test-secret-access-key",
}


class RemovalControlStub:
	"""Stands in for the control site's removal endpoints. Checks each request's signature, records it, and
	answers signed, echoing its `issued_at`.

	`instructions` are what `report_sites` answers, and `answers` adds values to a method's answer (such as
	`{"drop_starting": {"proceed": True}}`). `sign_with` and `echo` break every answer on purpose,
	`badly_signed` only the answers of the methods it names.
	"""

	def __init__(
		self,
		instructions=None,
		sign_with=RUNNER_SECRET,
		echo=True,
		error=None,
		answers=None,
		badly_signed=(),
	):
		self.instructions = instructions or []
		self.sign_with = sign_with
		self.echo = echo
		self.error = error
		self.answers = answers or {}
		self.badly_signed = badly_signed
		self.calls = []

	def post(self, url, data, headers, timeout):
		assert is_valid_signature(data, headers.get(SIGNATURE_HEADER), RUNNER_SECRET), "unsigned request"
		body = json.loads(data)
		method = url.rsplit(".", 1)[-1]
		self.calls.append((method, body))
		if self.error:
			raise self.error
		message = {"issued_at": body["issued_at"] if self.echo else iso_ago(seconds=5), "status": "ok"}
		if method == "report_sites":
			message["instructions"] = self.instructions
		message.update(self.answers.get(method, {}))
		response = requests.Response()
		response.status_code = 200
		response._content = json.dumps({"message": message}).encode()
		secret = b"not-the-runner-secret" * 2 if method in self.badly_signed else self.sign_with
		response.headers[SIGNATURE_HEADER] = sign(response._content, secret)
		return response

	def methods(self) -> list[str]:
		return [name for name, _body in self.calls]

	def bodies(self, method: str) -> list[dict]:
		return [body for name, body in self.calls if name == method]


class FakeStorage:
	"""Keeps each uploaded object's bytes in memory, by key."""

	def __init__(self, error=None):
		self.objects = {}
		self.error = error

	def upload(self, path: str, key: str):
		if self.error:
			raise self.error
		with open(path, "rb") as handle:
			self.objects[key] = handle.read()


def runner_secrets(**overrides) -> dict:
	return {
		"runner_name": RUNNER_NAME,
		"runner_secret": RUNNER_SECRET.decode(),
		"control_url": CONTROL_URL,
		"export_storage": STORAGE,
		"root_login": "root",
		"root_password": ROOT_PASSWORD,
		**overrides,
	}


@contextmanager
def runner_bench(stub, storage=None, mode="live", secrets=None, file_mode=0o600, sites=None, bench=None):
	"""A bench folder in a temp dir whose only site is this test site (unless `sites` says otherwise).

	Opening a site is a no op here, since the test already runs inside it. Yields the bench path. Pass `bench`
	to run again in a folder an earlier run used; the caller then deletes it.
	"""
	keep = bench is not None
	bench = bench or tempfile.mkdtemp(prefix="books-bench-")
	os.makedirs(os.path.join(bench, "sites"), exist_ok=True)
	os.makedirs(os.path.join(bench, "config"), exist_ok=True)
	if mode is not None:
		with open(os.path.join(bench, "sites", "common_site_config.json"), "w") as handle:
			json.dump({"books_removal_mode": mode}, handle)
	secrets_path = os.path.join(bench, "config", "books-runner.json")
	with open(secrets_path, "w") as handle:
		json.dump(runner_secrets() if secrets is None else secrets, handle)
	os.chmod(secrets_path, file_mode)

	storage = storage or FakeStorage()
	with (
		patch.dict(frappe.conf, {"books_control_url": CONTROL_URL}),
		patch("frappe_books.subscription.runner.requests.post", stub.post),
		patch("frappe_books.subscription.runner.make_storage", return_value=storage),
		patch(
			"frappe_books.subscription.runner.bench_sites",
			return_value=[frappe.local.site] if sites is None else sites,
		),
		patch("frappe_books.subscription.runner.open_site", this_site_only),
	):
		try:
			yield bench
		finally:
			if not keep:
				shutil.rmtree(bench, ignore_errors=True)


@contextmanager
def this_site_only(site: str):
	"""The test's own site opens; any other fails to open, as a broken site would."""
	if site != frappe.local.site:
		raise RuntimeError(f"can't open {site}: Access denied for {ROOT_PASSWORD}")
	yield
