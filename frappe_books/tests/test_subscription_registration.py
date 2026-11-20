"""`bench books-register-site` (spec 0008 AC-1), against a signed control site stub."""

import json
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from frappe_books.subscription.control import SIGNATURE_HEADER, is_valid_signature, sign
from frappe_books.subscription.registration import register
from frappe_books.tests.removal import RUNNER_NAME, RUNNER_SECRET, runner_bench, runner_secrets
from frappe_books.tests.subscription import CONTROL_URL, iso_ago

SITE_SECRET = "0123456789abcdef" * 4
OWNER = "owner@example.com"
SITE_URL = "https://acme.example.com"


class RegisterStub:
	"""Stands in for the control site's `register_site`: checks the runner signature and answers signed.

	`status` answers with that status (a 409 or 401 is signed too, as spec 0008 AC-5 says); `echo=False`
	answers with another `issued_at`; `answer` overrides fields of the answer.
	"""

	def __init__(self, status=200, echo=True, sign_with=RUNNER_SECRET, answer=None, error=None):
		self.status = status
		self.echo = echo
		self.sign_with = sign_with
		self.answer = answer or {}
		self.error = error
		self.calls = []

	def post(self, url, data, headers, timeout):
		assert is_valid_signature(data, headers.get(SIGNATURE_HEADER), RUNNER_SECRET), "unsigned request"
		body = json.loads(data)
		self.calls.append((url.rsplit("/", 1)[-1], body))
		if self.error:
			raise self.error
		message = {
			"issued_at": body["issued_at"] if self.echo else iso_ago(seconds=5),
			"site": body["site"],
			"secret": SITE_SECRET,
			**self.answer,
		}
		response = requests.Response()
		response.status_code = self.status
		response._content = json.dumps(message if self.status == 200 else {}).encode()
		response.headers[SIGNATURE_HEADER] = sign(response._content, self.sign_with)
		return response


class IntegrationTestRegisterSite(IntegrationTestCase):
	def run_register(self, stub, site=None, owner_email=OWNER, site_url=SITE_URL, secrets=None, stored=None):
		"""Run the command in a throwaway bench. Returns the exit code, the log lines and the config writes."""
		lines, writes = [], []
		with (
			runner_bench(stub, secrets=secrets) as bench,
			patch.dict(frappe.conf, {"books_control_secret": stored or ""}),
			patch(
				"frappe_books.subscription.registration.update_site_config",
				lambda key, value: writes.append((key, value)),
			),
		):
			code = register(
				site or frappe.local.site, owner_email, site_url, bench_path=bench, log=lines.append
			)
		return code, lines, writes

	def test_a_new_site_gets_its_secret_written(self):
		# covers: AC-1
		stub = RegisterStub()
		code, lines, writes = self.run_register(stub)
		self.assertEqual(code, 0)
		method, body = stub.calls[0]
		self.assertEqual(method, "rarebooks_control.api.register_site")
		self.assertEqual(body["bench"], RUNNER_NAME)
		self.assertEqual(
			(body["site"], body["site_url"], body["owner_email"]), (frappe.local.site, SITE_URL, OWNER)
		)
		self.assertEqual(writes, [("books_control_url", CONTROL_URL), ("books_control_secret", SITE_SECRET)])
		self.assertNotIn(SITE_SECRET, "\n".join(lines))

	def test_a_rerun_with_the_same_secret_says_nothing_changed(self):
		# covers: AC-1
		code, lines, _writes = self.run_register(RegisterStub(), stored=SITE_SECRET)
		self.assertEqual(code, 0)
		self.assertIn("already registered", lines[-1])

	def test_bad_arguments_stop_before_any_call(self):
		# covers: AC-1
		for kwargs in (
			{"site_url": "http://acme.example.com"},
			{"site_url": "acme.example.com"},
			{"owner_email": "not-an-email"},
			{"site": "not-on-this-bench.localhost"},
		):
			with self.subTest(**kwargs):
				stub = RegisterStub()
				code, lines, writes = self.run_register(stub, **kwargs)
				self.assertEqual((code, stub.calls, writes), (1, [], []))
				self.assertTrue(lines[-1].startswith("stopped:"))

	def test_a_refusal_or_a_bad_answer_writes_nothing(self):
		# covers: AC-1 (409 on another bench or Removed, 401 bad signature), AC-15 of spec 0007 (the echo)
		for name, stub, expected in (
			("409", RegisterStub(status=409), "answered HTTP 409"),
			("401", RegisterStub(status=401), "answered HTTP 401"),
			("no echo", RegisterStub(echo=False), "doesn't echo"),
			("bad signature", RegisterStub(sign_with=b"x" * 40), "without a valid signature"),
			("timeout", RegisterStub(error=requests.Timeout()), "failed: Timeout"),
			("another site", RegisterStub(answer={"site": "other.localhost"}), "without this site's secret"),
			("short secret", RegisterStub(answer={"secret": "abc"}), "without this site's secret"),
		):
			with self.subTest(name):
				code, lines, writes = self.run_register(stub)
				self.assertEqual((code, writes), (1, []))
				self.assertIn(expected, lines[-1])

	def test_a_bench_without_export_storage_can_still_register(self):
		# The register command uploads nothing, so it doesn't need the R2 keys the removal runner needs.
		secrets = runner_secrets(export_storage={})
		code, _lines, writes = self.run_register(RegisterStub(), secrets=secrets)
		self.assertEqual(code, 0)
		self.assertEqual(len(writes), 2)

	def test_a_missing_secrets_file_value_stops(self):
		code, lines, writes = self.run_register(RegisterStub(), secrets=runner_secrets(runner_name=""))
		self.assertEqual((code, writes), (1, []))
		self.assertIn("runner_name is missing", lines[-1])
