"""The control site's signed calls into a hosted site, and the export job they start (spec 0010, Milestone 1)."""

import hashlib
import io
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_url

from frappe_books.subscription import lock, removal
from frappe_books.subscription.clock import DOCTYPE
from frappe_books.subscription.control import SIGNATURE_HEADER, is_valid_signature, sign
from frappe_books.tests.subscription import (
	CONTROL_URL,
	TEST_CLIENT,
	TEST_SECRET,
	SubscriptionTestMixin,
	iso_ago,
	lock_site,
	managed_site,
	store_facts,
)

CASE = "RC-00042"
ATTEMPT = "0b7c1f3e-8d2a-4c5b-9e6f-1a2b3c4d5e6f"
UPLOAD_URL = (
	"https://acct.r2.cloudflarestorage.com/books-exports/exports/RC-00042/"
	f"{ATTEMPT}.zip?X-Amz-Signature=deadbeefsignature&X-Amz-Credential=never-shown"
)
EXPORT_JOB = "frappe_books.subscription.removal.export_job"


def in_hours(hours: float) -> str:
	return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def site_call(method: str, values: dict | None = None, secret: bytes = TEST_SECRET, **overrides):
	"""POST to `frappe_books.subscription.<method>` over the test client, as the control site would."""
	body = {"site": frappe.local.site, "issued_at": iso_ago(seconds=1), **(values or {}), **overrides}
	raw = json.dumps(body).encode()
	return body, make_request(
		target=TEST_CLIENT.post,
		args=(get_url(f"/api/method/frappe_books.subscription.{method}"),),
		kwargs={
			"data": raw,
			"headers": {SIGNATURE_HEADER: sign(raw, secret)},
			"content_type": "application/json",
		},
	)


def signed_json(response, secret: bytes = TEST_SECRET) -> dict:
	"""The answer's JSON, after checking it is signed with `secret` and has no `message` wrapper."""
	data = response.get_data()
	assert is_valid_signature(data, response.headers.get(SIGNATURE_HEADER), secret), "answer not signed"
	answer = json.loads(data)
	assert "message" not in answer, "a signed answer must not be wrapped"
	return answer


class IntegrationTestRemoteCalls(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for patcher in (
			managed_site(),
			patch("frappe_books.subscription.remote.site_secret", return_value=TEST_SECRET),
		):
			patcher.__enter__()
			self.addCleanup(patcher.__exit__, None, None, None)
		frappe.cache.delete_keys("rl:")

	def test_a_signed_ping_gets_a_signed_answer_that_echoes_issued_at(self):
		# covers: AC-2, AC-11
		body, response = site_call("control_ping")
		self.assertEqual(response.status_code, 200)
		answer = signed_json(response)
		self.assertEqual(answer, {"site": frappe.local.site, "status": "ok", "issued_at": body["issued_at"]})

	def test_a_bad_signature_a_stale_call_or_another_site_gets_a_signed_401(self):
		# covers: AC-2
		cases = {
			"bad signature": {"secret": b"not-the-secret-0123456789abcdef0123456789"},
			"stale": {"issued_at": iso_ago(minutes=6)},
			"naive time": {"issued_at": datetime.now(UTC).replace(tzinfo=None).isoformat()},
			"another site": {"site": "other.example.com"},
		}
		for label, overrides in cases.items():
			with self.subTest(label):
				body, response = site_call("removal_report", **overrides)
				self.assertEqual(response.status_code, 401)
				self.assertEqual(signed_json(response), {"issued_at": body["issued_at"]})

	def test_a_site_that_is_not_hosted_refuses_every_call(self):
		# covers: AC-2
		with managed_site(False):
			_body, response = site_call("control_ping")
		self.assertEqual(response.status_code, 401)

	def test_the_report_is_the_removal_status_plus_the_echo(self):
		# covers: AC-1, AC-2
		lock_site()
		body, response = site_call("removal_report")
		answer = signed_json(response)
		self.assertEqual(answer["issued_at"], body["issued_at"])
		self.assertEqual(answer["site"], frappe.local.site)
		self.assertEqual(answer["phase"], "locked")
		self.assertIn("removal_on", answer)

	def test_every_call_still_works_on_a_locked_site(self):
		# covers: AC-5
		lock_site()
		sent, hold = "2031-01-30T09:00:00+00:00", "2031-02-02T09:00:00+00:00"
		with patch("frappe.enqueue") as enqueue:
			calls = {
				"removal_report": {},
				"control_ping": {},
				"start_export": {
					"case": CASE,
					"attempt_id": ATTEMPT,
					"upload_url": UPLOAD_URL,
					"expires_at": in_hours(6),
				},
				"mark_export_sent": {"export_sent_on": sent, "removal_hold_until": hold},
			}
			for method, values in calls.items():
				with self.subTest(method):
					_body, response = site_call(method, values)
					self.assertEqual(response.status_code, 200, response.get_data()[:300])
			enqueue.assert_called_once()

		# The request thread committed; start a new snapshot to see it.
		frappe.db.rollback()
		facts = frappe.get_doc(DOCTYPE)
		self.assertEqual(str(facts.export_sent_on), "2031-01-30 09:00:00")
		self.assertEqual(str(facts.removal_hold_until), "2031-02-02 09:00:00")

		_body, response = site_call("clear_removal")
		self.assertEqual(response.status_code, 200)
		# The request thread committed; start a new snapshot to see it.
		frappe.db.rollback()
		facts = frappe.get_doc(DOCTYPE)
		self.assertIsNone(facts.export_sent_on)
		self.assertIsNone(facts.removal_hold_until)

	def test_start_export_queues_one_deduplicated_job_on_the_long_queue(self):
		# covers: AC-3
		expires = in_hours(6)
		with patch("frappe.enqueue") as enqueue:
			_body, response = site_call(
				"start_export",
				{"case": CASE, "attempt_id": ATTEMPT, "upload_url": UPLOAD_URL, "expires_at": expires},
			)
		self.assertEqual(signed_json(response)["status"], "queued")
		args, kwargs = enqueue.call_args
		self.assertEqual(args, (EXPORT_JOB,))
		self.assertEqual(kwargs["queue"], "long")
		self.assertEqual(kwargs["timeout"], 2 * 60 * 60)
		self.assertEqual(kwargs["job_id"], f"books-export:{CASE}:{ATTEMPT}")
		self.assertTrue(kwargs["deduplicate"])
		self.assertEqual(
			(kwargs["case"], kwargs["attempt_id"], kwargs["upload_url"], kwargs["expires_at"]),
			(CASE, ATTEMPT, UPLOAD_URL, expires),
		)

	def test_start_export_refuses_a_link_off_r2_or_a_bad_case(self):
		# covers: AC-3 (the upload host must be R2)
		good = {"case": CASE, "attempt_id": ATTEMPT, "upload_url": UPLOAD_URL, "expires_at": in_hours(6)}
		bad = {
			"http": {"upload_url": UPLOAD_URL.replace("https://", "http://")},
			"other host": {"upload_url": "https://evil.example.com/x.zip"},
			"lookalike host": {"upload_url": "https://r2.cloudflarestorage.com.evil.com/x.zip"},
			"user info": {"upload_url": UPLOAD_URL.replace("https://", "https://me@")},
			"case path": {"case": "../etc"},
			"attempt": {"attempt_id": "not-a-uuid"},
			"expiry": {"expires_at": "tomorrow"},
		}
		with patch("frappe.enqueue") as enqueue:
			for label, change in bad.items():
				with self.subTest(label):
					_body, response = site_call("start_export", {**good, **change})
					self.assertEqual(response.status_code, 400)
					self.assertEqual(signed_json(response)["status"], "bad_request")
		enqueue.assert_not_called()

	def test_mark_export_sent_refuses_a_bad_time(self):
		_body, response = site_call(
			"mark_export_sent", {"export_sent_on": "soon", "removal_hold_until": "2031-02-02T09:00:00+00:00"}
		)
		self.assertEqual(response.status_code, 400)


class ControlForJob:
	"""Stands in for the control site's `export_ready` and `step_failed`: checks each request's signature and
	answers signed, echoing its `issued_at`. `statuses` are the answers to `export_ready`, in turn."""

	def __init__(self, statuses=(200,)):
		self.statuses = list(statuses)
		self.calls = []

	def post(self, url, data, headers, timeout):
		assert is_valid_signature(data, headers.get(SIGNATURE_HEADER), TEST_SECRET), "unsigned request"
		body = json.loads(data)
		method = url.rsplit(".", 1)[-1]
		self.calls.append((method, body))
		status = self.statuses.pop(0) if method == "export_ready" and self.statuses else 200
		response = requests.Response()
		response.status_code = status
		response._content = json.dumps({"issued_at": body["issued_at"], "status": "ok"}).encode()
		response.headers[SIGNATURE_HEADER] = sign(response._content, TEST_SECRET)
		return response

	def bodies(self, method: str) -> list[dict]:
		return [body for name, body in self.calls if name == method]


class FakeR2:
	"""Records each PUT and keeps the uploaded bytes."""

	def __init__(self, status=200, error=None):
		self.status, self.error = status, error
		self.puts = []

	def put(self, url, data, headers, timeout, allow_redirects):
		assert allow_redirects is False
		if self.error:
			raise self.error
		self.puts.append((url, data.read(), headers))
		response = requests.Response()
		response.status_code = self.status
		return response


class IntegrationTestExportJob(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		lock_site()
		self.folder = os.path.abspath(frappe.get_site_path(removal.EXPORT_FOLDER, CASE))

	def run_job(self, control=None, r2=None, expires_at=None):
		control, r2 = control or ControlForJob(), r2 or FakeR2()
		conf = {"books_control_url": CONTROL_URL, "books_control_secret": TEST_SECRET.decode()}
		with (
			managed_site(),
			patch.dict(frappe.conf, conf),
			patch("frappe_books.subscription.control.requests.post", control.post),
			patch("frappe_books.subscription.removal.requests.put", r2.put),
			patch("frappe_books.subscription.removal.time.sleep") as sleep,
		):
			removal.export_job(CASE, ATTEMPT, UPLOAD_URL, expires_at or in_hours(6))
		self.sleeps = [call.args[0] for call in sleep.call_args_list]
		return control, r2

	def test_the_job_builds_uploads_and_reports_the_export(self):
		# covers: AC-4, AC-5 (on a locked site, and the job writes nothing to the database)
		before = frappe.db.get_value(DOCTYPE, DOCTYPE, "modified")
		control, r2 = self.run_job()

		self.assertEqual(len(r2.puts), 1)
		url, content, headers = r2.puts[0]
		self.assertEqual(url, UPLOAD_URL)
		self.assertEqual(headers["Content-Length"], str(len(content)))
		names = zipfile.ZipFile(io.BytesIO(content)).namelist()
		self.assertIn("README.txt", names)
		self.assertIn("backup/database.sql.gz", names)

		(ready,) = control.bodies("export_ready")
		self.assertEqual((ready["case"], ready["attempt_id"], ready["bytes"]), (CASE, ATTEMPT, len(content)))
		self.assertEqual(ready["sha256"], hashlib.sha256(content).hexdigest())
		self.assertEqual(ready["site"], frappe.local.site)
		self.assertFalse(control.bodies("step_failed"))
		self.assertFalse(os.path.exists(self.folder))
		self.assertEqual(frappe.db.get_value(DOCTYPE, DOCTYPE, "modified"), before)

	def test_the_locked_site_lets_the_export_job_past_the_read_only_lock(self):
		# covers: AC-5
		with managed_site():
			frappe.flags.read_only = False
			lock.lock_job(EXPORT_JOB)
			self.assertFalse(frappe.flags.read_only)
			lock.lock_job("frappe_books.some.other_job")
			self.assertTrue(frappe.flags.read_only)
		frappe.flags.read_only = False
		frappe.flags.books_site_locked = False
		frappe.db.rollback()

	def test_a_link_with_under_two_hours_left_is_refused_before_building(self):
		# covers: AC-4
		control, r2 = self.run_job(expires_at=in_hours(1.5))
		self.assertFalse(r2.puts)
		(failed,) = control.bodies("step_failed")
		self.assertEqual((failed["case"], failed["step"], failed["error"]), (CASE, "export", "link_expiring"))
		self.assertFalse(control.bodies("export_ready"))

	def test_a_zip_over_the_cap_is_not_uploaded(self):
		# covers: AC-4
		with patch("frappe_books.subscription.removal.MAX_UPLOAD_BYTES", 10):
			control, r2 = self.run_job()
		self.assertFalse(r2.puts)
		(failed,) = control.bodies("step_failed")
		self.assertEqual((failed["step"], failed["error"]), ("upload", "too_large"))
		self.assertFalse(os.path.exists(self.folder))

	def test_a_failed_upload_reports_text_with_no_url_or_secret(self):
		# covers: AC-4, AC-13
		error = requests.ConnectionError(f"failed {UPLOAD_URL} with {TEST_SECRET.decode()}")
		control, _r2 = self.run_job(r2=FakeR2(error=error))
		(failed,) = control.bodies("step_failed")
		self.assertEqual(failed["step"], "upload")
		self.assertIn("ConnectionError", failed["error"])
		for secret in ("deadbeefsignature", "never-shown", TEST_SECRET.decode(), "cloudflarestorage"):
			self.assertNotIn(secret, failed["error"])
		self.assertFalse(os.path.exists(self.folder))

	def test_a_503_from_export_ready_is_tried_again_after_one_minute(self):
		# covers: AC-4
		control, _r2 = self.run_job(control=ControlForJob(statuses=(503, 200)))
		self.assertEqual(len(control.bodies("export_ready")), 2)
		self.assertEqual(self.sleeps, [60])

	def test_export_ready_is_tried_four_times_at_most(self):
		# covers: AC-4
		control, _r2 = self.run_job(control=ControlForJob(statuses=(503, 503, 503, 503, 200)))
		self.assertEqual(len(control.bodies("export_ready")), 4)
		self.assertEqual(self.sleeps, [60, 300, 900])

	def test_a_409_from_export_ready_stops_the_job(self):
		# covers: AC-4
		control, _r2 = self.run_job(control=ControlForJob(statuses=(409,)))
		self.assertEqual(len(control.bodies("export_ready")), 1)
		self.assertEqual(self.sleeps, [])
		self.assertFalse(control.bodies("step_failed"))

	def tearDown(self):
		store_facts(export_sent_on=None, removal_hold_until=None)
		super().tearDown()
