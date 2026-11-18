"""Trial end export and removal, the customer site and runner side (spec 0007)."""

import csv
import gzip
import hashlib
import io
import os
import shutil
import tempfile
import zipfile
from collections import namedtuple
from datetime import timedelta
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_datetime, getdate

from frappe_books.subscription.clock import DOCTYPE, _local_date, current_clock, site_zone, utc_now
from frappe_books.subscription.removal import (
	PendingWritesError,
	build_export,
	clear_removal,
	mark_export_sent,
	removal_status,
)
from frappe_books.subscription.runner import run
from frappe_books.subscription.state import apply_state
from frappe_books.tests.accounting import insert_sales_invoice
from frappe_books.tests.removal import (
	ROOT_PASSWORD,
	RUNNER_NAME,
	RUNNER_SECRET,
	STORAGE,
	FakeStorage,
	RemovalControlStub,
	runner_bench,
	runner_secrets,
)
from frappe_books.tests.subscription import SubscriptionTestMixin, lock_site, managed_site, store_facts

SENT_ON = "2031-01-30T09:00:00+00:00"
HOLD_UNTIL = "2031-02-02T09:00:00+00:00"
CASE = "RC-00001"
DiskUsage = namedtuple("DiskUsage", "total used free")


def facts():
	return frappe.get_doc(DOCTYPE)


def site_today():
	return _local_date(utc_now(), site_zone())


class IntegrationTestRemovalSite(SubscriptionTestMixin, IntegrationTestCase):
	def test_a_locked_trial_reports_its_day_30_removal(self):
		# covers: AC-1
		store_facts(trial_started_on=utc_now() - timedelta(days=27), paid_until=None, exempt=0)
		with managed_site():
			status = removal_status()
		day_one = current_clock().day_one
		self.assertEqual(status["site"], frappe.local.site)
		self.assertEqual((status["phase"], status["kind"]), ("locked", "Trial"))
		self.assertEqual(status["removal_on"], (day_one + timedelta(days=29)).isoformat())
		self.assertEqual(status["today"], site_today().isoformat())
		self.assertFalse(status["exempt"])
		self.assertFalse(status["payment_pending"])
		self.assertEqual(
			status["company_name"], frappe.db.get_single_value("Books Accounting Settings", "company_name")
		)
		self.assertTrue(status["site_url"].startswith("http"))
		self.assertIsNone(status["export_sent_on"])

	def test_a_lapsed_site_reports_paid_until_plus_67_days(self):
		# covers: AC-1, AC-2
		paid_until = add_days(site_today(), -10)
		store_facts(
			paid_until=paid_until, provider="PayPal", billing_period="Yearly", auto_renews=0, exempt=0
		)
		with managed_site():
			status = removal_status()
		self.assertEqual((status["phase"], status["kind"]), ("lapsed", "Lapsed"))
		self.assertEqual(status["removal_on"], add_days(paid_until, 67).isoformat())
		self.assertEqual(status["paid_until"], getdate(paid_until).isoformat())

	def test_an_unmanaged_or_exempt_site_has_no_removal(self):
		# covers: AC-1
		lock_site()
		with managed_site(False):
			self.assertIsNone(removal_status()["removal_on"])
		store_facts(exempt=1)
		with managed_site():
			status = removal_status()
		self.assertEqual(status["phase"], "exempt")
		self.assertIsNone(status["removal_on"])
		self.assertTrue(status["exempt"])

	def test_mark_export_sent_writes_both_fields_on_a_locked_site(self):
		# covers: AC-8, AC-18
		lock_site()
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		self.assertEqual(get_datetime(facts().export_sent_on), get_datetime("2031-01-30 09:00:00"))
		self.assertEqual(get_datetime(facts().removal_hold_until), get_datetime("2031-02-02 09:00:00"))
		with managed_site():
			status = removal_status()
		self.assertEqual(status["export_sent_on"], SENT_ON)
		self.assertEqual(status["removal_hold_until"], HOLD_UNTIL)

	def test_mark_export_sent_is_safe_to_repeat(self):
		# covers: AC-8 (safe to repeat writes no new version)
		lock_site()
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		modified = facts().modified
		mark_export_sent("2031-01-30T12:00:00+03:00", HOLD_UNTIL)
		self.assertEqual(facts().modified, modified)

	def test_clear_removal_empties_both_fields_and_is_safe_when_empty(self):
		# covers: AC-11
		lock_site()
		clear_removal()
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		clear_removal()
		self.assertIsNone(facts().export_sent_on)
		self.assertIsNone(facts().removal_hold_until)

	def test_a_newer_paid_until_clears_the_hold(self):
		# covers: AC-11
		lock_site()
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		apply_state({"paid_until": add_days(site_today(), 365), "provider": "PayPal"})
		self.assertIsNone(facts().export_sent_on)
		self.assertIsNone(facts().removal_hold_until)

	def test_a_push_without_a_newer_paid_until_keeps_the_hold(self):
		# covers: AC-11 (only a newer paid_until clears it)
		lock_site()
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		apply_state({"provider": "PayPal"})
		self.assertIsNotNone(facts().removal_hold_until)

	def test_no_one_else_can_write_the_hold_fields(self):
		doc = facts()
		doc.removal_hold_until = utc_now()
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)


class IntegrationTestRemovalExport(SubscriptionTestMixin, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.invoice = insert_sales_invoice(
			"2031-01-15 10:00:00", [{"item": "Export Test Item", "amount": 25}], party="Export Test Party"
		)
		cls.file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "export-test-receipt.txt",
				"content": b"receipt for the export test",
				"is_private": 1,
				"attached_to_doctype": "Books Sales Invoice",
				"attached_to_name": cls.invoice,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.delete_doc("File", cls.file.name, force=True, ignore_permissions=True)
		frappe.db.delete("Books Sales Invoice Item", {"parent": cls.invoice})
		frappe.db.delete("Books Sales Invoice", {"name": cls.invoice})
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.out = tempfile.mkdtemp(prefix="books-export-test-")
		self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

	def test_the_export_holds_the_readable_files_and_backup(self):
		# covers: AC-6, AC-18 (built on a locked site, and Password columns dropped)
		lock_site()
		hide = lambda meta: {"discount_after_tax"} if meta.name == "Books Sales Invoice" else set()  # noqa: E731
		with managed_site(), patch("frappe_books.subscription.removal.password_fields", hide):
			counts = build_export(self.out)

		readable = os.path.join(self.out, "readable")
		invoices = read_csv(os.path.join(readable, "Books Sales Invoice.csv"))
		self.assertIn("name", invoices[0])
		self.assertNotIn("discount_after_tax", invoices[0])
		self.assertIn(self.invoice, [row["name"] for row in invoices])

		items = read_csv(os.path.join(readable, "Books Sales Invoice Item.csv"))
		row = next(row for row in items if row["parent"] == self.invoice)
		self.assertEqual(
			(row["parenttype"], row["parentfield"], row["idx"]), ("Books Sales Invoice", "items", "1")
		)

		settings = read_csv(os.path.join(readable, "Books Accounting Settings.csv"))
		self.assertEqual(list(settings[0]), ["field", "value"])
		self.assertIn("company_name", [row["field"] for row in settings])
		self.assertFalse(os.path.exists(os.path.join(readable, "Books Subscription.csv")))

		files = read_csv(os.path.join(readable, "File.csv"))
		attached = next(row for row in files if row["name"] == self.file.name)
		self.assertEqual(
			(attached["attached_to_doctype"], attached["attached_to_name"]),
			("Books Sales Invoice", self.invoice),
		)
		self.assertEqual(attached["is_private"], "1")
		copied = os.path.join(self.out, "files", "private", os.path.basename(self.file.file_url))
		with open(copied, "rb") as handle:
			self.assertEqual(handle.read(), b"receipt for the export test")

		with gzip.open(os.path.join(self.out, "backup", "database.sql.gz"), "rt") as dump:
			self.assertIn("frappe metadata", dump.read(500))
		with open(os.path.join(self.out, "README.txt")) as handle:
			readme = handle.read()
		self.assertIn("Frappe version 16", readme)
		self.assertIn("Enter them again after you restore.", readme)

		every_name = [name for _root, _dirs, names in os.walk(self.out) for name in names]
		self.assertNotIn("site_config.json", every_name)
		self.assertEqual(set(counts), {"doctypes", "rows", "files", "bytes"})
		self.assertGreaterEqual(counts["files"], 1)
		self.assertGreater(counts["bytes"], 0)

	def test_every_csv_starts_with_a_byte_order_mark(self):
		# covers: AC-6
		with patch("frappe_books.subscription.removal._write_database_backup"):
			build_export(self.out)
		readable = os.path.join(self.out, "readable")
		for name in os.listdir(readable):
			with self.subTest(csv=name), open(os.path.join(readable, name), "rb") as handle:
				self.assertEqual(handle.read(3), b"\xef\xbb\xbf")

	def test_an_export_writes_nothing_to_the_database(self):
		# covers: AC-18
		before = facts().modified
		with patch("frappe_books.subscription.removal._write_database_backup"):
			build_export(self.out)
		self.assertEqual(frappe.db.transaction_writes, 0)
		self.assertEqual(facts().modified, before)

	def test_an_export_refuses_to_commit_pending_writes(self):
		frappe.db.set_single_value("Books Accounting Settings", "company_name", "Uncommitted Co")
		self.assertRaises(PendingWritesError, build_export, self.out)
		frappe.db.rollback()


class IntegrationTestRemovalRunner(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.lines = []
		lock_site()

	def run_bench(self, stub, **options):
		storage = options.pop("storage", None) or FakeStorage()
		with runner_bench(stub, storage=storage, **options) as bench:
			code = run(bench_path=bench, log=self.lines.append)
			work = os.path.join(bench, "books-removal")
			# Only the case folders; the deferred list lives beside them.
			leftovers = (
				[name for name in os.listdir(work) if name != "deferred.json"] if os.path.isdir(work) else []
			)
		return code, storage, leftovers

	def instruction(self, action, case=CASE, **values):
		return {"site": frappe.local.site, "case": case, "action": action, **values}

	def test_off_mode_does_nothing_but_log(self):
		# covers: AC-3
		for mode in (None, "off", "unknown"):
			with self.subTest(mode=mode):
				stub = RemovalControlStub()
				code, _storage, _left = self.run_bench(stub, mode=mode)
				self.assertEqual(code, 0)
				self.assertEqual(stub.calls, [])
		self.assertTrue(all("is off" in line for line in self.lines))

	def test_a_secrets_file_others_can_read_stops_the_run(self):
		# covers: AC-15
		stub = RemovalControlStub()
		code, _storage, _left = self.run_bench(stub, file_mode=0o644)
		self.assertEqual(code, 1)
		self.assertEqual(stub.calls, [])
		self.assertIn("mode 600", self.lines[-1])

	def test_an_http_control_url_or_a_short_secret_stops_the_run(self):
		# covers: AC-15
		for secrets in (
			runner_secrets(control_url="http://control.example.com"),
			runner_secrets(runner_secret="short"),
		):
			with self.subTest(secrets=secrets["control_url"]):
				stub = RemovalControlStub()
				code, _storage, _left = self.run_bench(stub, secrets=secrets)
				self.assertEqual(code, 1)
				self.assertEqual(stub.calls, [])

	def test_the_report_is_signed_and_carries_every_site_status(self):
		# covers: AC-3, AC-15
		stub = RemovalControlStub()
		code, _storage, _left = self.run_bench(stub)
		self.assertEqual(code, 0)
		(report,) = stub.bodies("report_sites")
		self.assertEqual((report["bench"], report["mode"]), (RUNNER_NAME, "live"))
		(status,) = report["sites"]
		self.assertEqual(
			(status["site"], status["phase"], status["kind"]), (frappe.local.site, "locked", "Trial")
		)
		self.assertTrue(status["removal_on"])

	def test_no_sites_still_reports_once(self):
		# covers: AC-3 (the control site hears from the bench every run)
		stub = RemovalControlStub()
		self.run_bench(stub, sites=[])
		self.assertEqual([body["sites"] for body in stub.bodies("report_sites")], [[]])

	def test_sites_are_reported_200_a_call(self):
		# covers: AC-3
		stub = RemovalControlStub()
		sites = [f"broken-{number}.example.com" for number in range(401)]
		self.run_bench(stub, sites=sites)
		self.assertEqual([len(body["sites"]) for body in stub.bodies("report_sites")], [200, 200, 1])

	def test_a_site_that_fails_to_open_is_reported_with_its_error_scrubbed(self):
		# covers: AC-3, AC-12 (no secret in the error text)
		stub = RemovalControlStub()
		self.run_bench(stub, sites=[frappe.local.site, "broken.example.com"])
		(report,) = stub.bodies("report_sites")
		broken = next(site for site in report["sites"] if site["site"] == "broken.example.com")
		self.assertIn("Access denied", broken["error"])
		self.assertNotIn("root-password", broken["error"])
		self.assertIn("***", broken["error"])
		self.assertEqual(len(report["sites"]), 2)

	def test_an_export_is_built_zipped_uploaded_and_reported(self):
		# covers: AC-6, AC-7
		stub = RemovalControlStub([self.instruction("export")])
		code, storage, leftovers = self.run_bench(stub)
		self.assertEqual(code, 0)
		(ready,) = stub.bodies("export_ready")
		(key,) = storage.objects
		data = storage.objects[key]
		self.assertTrue(key.startswith(f"exports/{CASE}/") and key.endswith(".zip"))
		self.assertEqual(ready["key"], key)
		self.assertEqual(
			(ready["case"], ready["site"], ready["bench"]), (CASE, frappe.local.site, RUNNER_NAME)
		)
		self.assertEqual(ready["bytes"], len(data))
		self.assertEqual(ready["sha256"], hashlib.sha256(data).hexdigest())

		names = zipfile.ZipFile(io.BytesIO(data)).namelist()
		for expected in (
			"README.txt",
			"backup/database.sql.gz",
			"readable/File.csv",
			"readable/Books Sales Invoice.csv",
		):
			self.assertIn(expected, names)
		self.assertFalse([name for name in names if name.endswith("site_config.json")])
		self.assertEqual(leftovers, [], "the local export folder is deleted")
		self.assertIn(f"export {CASE} uploaded", self.lines[-1])

	def test_mark_sent_writes_the_hold_in_live_mode(self):
		# covers: AC-8
		stub = RemovalControlStub(
			[self.instruction("mark_sent", export_sent_on=SENT_ON, removal_hold_until=HOLD_UNTIL)]
		)
		self.run_bench(stub)
		self.assertEqual(get_datetime(facts().removal_hold_until), get_datetime("2031-02-02 09:00:00"))
		self.assertEqual(get_datetime(facts().export_sent_on), get_datetime("2031-01-30 09:00:00"))

	def test_a_dry_run_exports_but_never_writes_the_site(self):
		# covers: AC-14
		stub = RemovalControlStub(
			[
				self.instruction("mark_sent", export_sent_on=SENT_ON, removal_hold_until=HOLD_UNTIL),
				self.instruction("export"),
			]
		)
		with patch("frappe_books.subscription.runner.build_export", fake_export):
			code, storage, _left = self.run_bench(stub, mode="dry_run")
		self.assertEqual(code, 0)
		self.assertIsNone(facts().removal_hold_until)
		self.assertEqual(len(storage.objects), 1)
		self.assertEqual(stub.bodies("report_sites")[0]["mode"], "dry_run")
		self.assertIn("skipped in dry_run", self.lines[-1])

	def test_an_answer_with_a_bad_signature_or_no_echo_stops_the_run(self):
		# covers: AC-15
		for stub in (
			RemovalControlStub([self.instruction("export")], sign_with=b"x" * 40),
			RemovalControlStub([self.instruction("export")], echo=False),
		):
			with self.subTest(echo=stub.echo):
				code, storage, _left = self.run_bench(stub)
				self.assertEqual(code, 1)
				self.assertEqual([name for name, _body in stub.calls], ["report_sites"])
				self.assertEqual(storage.objects, {})

	def test_a_control_site_that_is_down_stops_the_run(self):
		# covers: AC-3
		stub = RemovalControlStub(error=requests.ConnectionError("refused"))
		code, _storage, _left = self.run_bench(stub)
		self.assertEqual(code, 1)
		self.assertIn("nothing done", self.lines[-1])

	def test_unsafe_or_foreign_instructions_are_ignored(self):
		# covers: AC-15 (acts only on its own sites, with case names safe in a path)
		stub = RemovalControlStub(
			[
				self.instruction("export", case="../../etc"),
				self.instruction("export", case=""),
				self.instruction("format_disk"),
				{"site": "other-bench.example.com", "case": CASE, "action": "export"},
				"not a dict",
			]
		)
		code, storage, _left = self.run_bench(stub)
		self.assertEqual(code, 0)
		self.assertEqual(storage.objects, {})
		self.assertEqual(stub.bodies("export_ready"), [])
		self.assertEqual(sum("ignored an instruction" in line for line in self.lines), 5)

	def test_at_most_three_exports_a_run(self):
		# covers: AC-3 (the per run cap)
		stub = RemovalControlStub(
			[self.instruction("export", case=f"RC-0000{number}") for number in range(1, 5)]
		)
		with patch("frappe_books.subscription.runner.build_export", fake_export):
			_code, storage, _left = self.run_bench(stub)
		self.assertEqual(len(storage.objects), 3)
		self.assertEqual(len(stub.bodies("export_ready")), 3)
		self.assertIn("RC-00004 put off to the next run", self.lines[-1])

	def test_too_little_free_disk_skips_the_export(self):
		# covers: the disk check (Value sourcing)
		stub = RemovalControlStub([self.instruction("export")])
		with patch("frappe_books.subscription.runner.shutil.disk_usage", return_value=DiskUsage(1, 1, 0)):
			_code, storage, leftovers = self.run_bench(stub)
		self.assertEqual(storage.objects, {})
		self.assertEqual(leftovers, [])
		self.assertIn("DiskSpaceError", self.lines[-1])

	def test_a_failed_upload_keeps_no_local_copy_and_no_secret_in_the_log(self):
		# covers: AC-12 (scrubbed error text)
		storage = FakeStorage(error=RuntimeError(f"denied for {STORAGE['secret_access_key']}"))
		stub = RemovalControlStub([self.instruction("export")])
		with patch("frappe_books.subscription.runner.build_export", fake_export):
			_code, _storage, leftovers = self.run_bench(stub, storage=storage)
		self.assertEqual(leftovers, [])
		self.assertEqual(stub.bodies("export_ready"), [])
		self.assertNotIn(STORAGE["secret_access_key"], "\n".join(self.lines))
		self.assertNotIn(RUNNER_SECRET.decode(), "\n".join(self.lines))

	def test_clear_empties_the_hold_in_live_mode_only(self):
		# covers: AC-11, AC-14
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		frappe.db.commit()
		stub = RemovalControlStub([self.instruction("clear")])
		self.run_bench(stub, mode="dry_run")
		self.assertIsNotNone(facts().removal_hold_until)
		self.run_bench(stub)
		self.assertIsNone(facts().removal_hold_until)
		self.assertIsNone(facts().export_sent_on)

	def test_a_payment_while_holding_clears_the_hold_and_nothing_is_exported(self):
		# covers: AC-11 (the push clears the fields, then the next run clears again and never exports)
		mark_export_sent(SENT_ON, HOLD_UNTIL)
		apply_state({"paid_until": add_days(site_today(), 365), "provider": "PayPal"})
		frappe.db.commit()
		stub = RemovalControlStub([self.instruction("clear")])
		code, storage, _left = self.run_bench(stub)
		self.assertEqual(code, 0)
		(status,) = stub.bodies("report_sites")[0]["sites"]
		self.assertEqual(status["phase"], "active")
		self.assertIsNone(status["removal_on"])
		self.assertIsNone(status["removal_hold_until"])
		self.assertEqual(storage.objects, {})

	def test_a_clear_after_an_export_started_still_clears(self):
		# covers: AC-11 (a payment during Exporting)
		stub = RemovalControlStub([self.instruction("clear")])
		code, storage, _left = self.run_bench(stub)
		self.assertEqual(code, 0)
		self.assertEqual(storage.objects, {})
		self.assertIsNone(facts().removal_hold_until)
		self.assertIn(f"clear {CASE} done", self.lines[-1])

	def test_a_failed_export_reports_step_failed_with_the_secrets_removed(self):
		# covers: AC-12
		def broken(_out_dir):
			raise RuntimeError(f"mysqldump: login {ROOT_PASSWORD} refused " + "x" * 3000)

		stub = RemovalControlStub([self.instruction("export")])
		with patch("frappe_books.subscription.runner.build_export", broken):
			code, storage, leftovers = self.run_bench(stub)
		self.assertEqual(code, 0)
		(failed,) = stub.bodies("step_failed")
		self.assertEqual((failed["case"], failed["step"], failed["bench"]), (CASE, "export", RUNNER_NAME))
		self.assertNotIn(ROOT_PASSWORD, failed["error"])
		self.assertIn("login *** refused", failed["error"])
		self.assertEqual(len(failed["error"]), 2000)
		self.assertEqual((storage.objects, leftovers), ({}, []))
		self.assertEqual(stub.bodies("export_ready"), [])

	def test_a_failed_upload_reports_the_upload_step(self):
		# covers: AC-12
		storage = FakeStorage(error=RuntimeError(f"403 for {STORAGE['access_key_id']}"))
		stub = RemovalControlStub([self.instruction("export")])
		with patch("frappe_books.subscription.runner.build_export", fake_export):
			self.run_bench(stub, storage=storage)
		(failed,) = stub.bodies("step_failed")
		self.assertEqual(failed["step"], "upload")
		self.assertEqual(failed["error"], "RuntimeError: 403 for ***")

	def test_too_little_disk_is_a_failed_export_step(self):
		# covers: AC-12, the disk check
		stub = RemovalControlStub([self.instruction("export")])
		with patch("frappe_books.subscription.runner.shutil.disk_usage", return_value=DiskUsage(1, 1, 0)):
			self.run_bench(stub)
		(failed,) = stub.bodies("step_failed")
		self.assertEqual(failed["step"], "export")
		self.assertTrue(failed["error"].startswith("DiskSpaceError"))

	def test_a_failure_the_control_site_cannot_hear_is_logged(self):
		# covers: AC-12 (the run goes on; the control site times out the claim)
		stub = RemovalControlStub([self.instruction("export")])
		answer_signed = stub.post

		def answer(url, data, headers, timeout):
			if url.endswith("step_failed"):
				raise requests.Timeout("slow")
			return answer_signed(url, data, headers, timeout)

		stub.post = answer
		with patch("frappe_books.subscription.runner.build_export", side_effect=RuntimeError("boom")):
			code, _storage, _left = self.run_bench(stub)
		self.assertEqual(code, 0)
		self.assertIn("couldn't report the failure", self.lines[-1])

	def test_deferred_exports_go_with_the_next_report_and_count_no_attempt(self):
		# covers: AC-12
		bench = tempfile.mkdtemp(prefix="books-bench-")
		self.addCleanup(shutil.rmtree, bench, ignore_errors=True)
		four = [self.instruction("export", case=f"RC-0000{number}") for number in range(1, 5)]
		with patch("frappe_books.subscription.runner.build_export", fake_export):
			first = RemovalControlStub(four)
			self.run_bench(first, bench=bench)
			self.assertEqual(first.bodies("report_sites")[0]["deferred"], [])
			self.assertEqual(first.bodies("step_failed"), [])

			down = RemovalControlStub(error=requests.ConnectionError("refused"))
			self.run_bench(down, bench=bench)

			second = RemovalControlStub()
			self.run_bench(second, bench=bench)
			self.assertEqual(second.bodies("report_sites")[0]["deferred"], ["RC-00004"])

			third = RemovalControlStub()
			self.run_bench(third, bench=bench)
			self.assertEqual(third.bodies("report_sites")[0]["deferred"], [])

	def test_only_the_first_chunk_carries_the_deferred_cases(self):
		# covers: AC-3, AC-12 (a broken entry in the file is dropped)
		bench = tempfile.mkdtemp(prefix="books-bench-")
		self.addCleanup(shutil.rmtree, bench, ignore_errors=True)
		os.makedirs(os.path.join(bench, "books-removal"))
		with open(os.path.join(bench, "books-removal", "deferred.json"), "w") as handle:
			handle.write('["RC-00009", "../bad", 7]')
		stub = RemovalControlStub()
		self.run_bench(stub, bench=bench, sites=[f"broken-{number}.example.com" for number in range(201)])
		self.assertEqual([body["deferred"] for body in stub.bodies("report_sites")], [["RC-00009"], []])


PROCEED = {"drop_starting": {"proceed": True, "reason": None}}


class IntegrationTestRemovalDrop(SubscriptionTestMixin, IntegrationTestCase):
	"""The `drop` instruction (spec 0007 Milestone 3). Frappe's drop itself is mocked; the rest is real."""

	def setUp(self):
		super().setUp()
		self.lines = []
		self.archives = []
		# Day 41 of an unpaid trial: locked, and past its removal date.
		store_facts(
			trial_started_on=utc_now() - timedelta(days=40),
			paid_until=None,
			exempt=0,
			checkout_started_on=None,
		)

	def run_drop(self, stub, state=(True, True), mode="live", drop=None, **options):
		"""One run with the site's folder and database `state` as given, and Frappe's drop mocked."""
		with (
			runner_bench(stub, mode=mode, **options) as bench,
			patch("frappe_books.subscription.runner.site_state", return_value=state) as site_state,
			patch(
				"frappe_books.subscription.runner.drop_site", side_effect=drop or self.fake_drop
			) as drop_site,
			patch("frappe_books.subscription.runner.finish_drop", side_effect=self.fake_drop) as finish_drop,
		):
			code = run(bench_path=bench, log=self.lines.append)
			self.archive_left = [path for path in self.archives if os.path.lexists(path)]
		self.assertEqual(code, 0)
		return site_state, drop_site, finish_drop

	def fake_drop(self, site, _config, archive):
		"""What Frappe's drop leaves: the site folder moved under the case's archived path."""
		os.makedirs(os.path.join(archive, site))
		self.archives.append(archive)

	def drop(self, site=None, case=CASE):
		return {"site": site or frappe.local.site, "case": case, "action": "drop"}

	def test_a_due_drop_waits_for_the_go_ahead_then_drops_and_reports_done(self):
		# covers: AC-9, AC-10
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		_state, drop_site, finish_drop = self.run_drop(stub)
		self.assertEqual(stub.methods(), ["report_sites", "drop_starting", "drop_done"])
		(starting,) = stub.bodies("drop_starting")
		self.assertEqual((starting["case"], starting["site"]), (CASE, frappe.local.site))
		(site, config, archive) = drop_site.call_args.args
		self.assertEqual(site, frappe.local.site)
		self.assertEqual(config.root_password, ROOT_PASSWORD)
		self.assertEqual(archive, os.path.join(config.bench_path, "books-removal", "archived", CASE))
		finish_drop.assert_not_called()
		self.assertEqual(self.archive_left, [], "the case's archived folder is deleted")
		self.assertIn(f"drop {CASE} dropped", self.lines[-1])

	def test_the_control_site_saying_no_drops_nothing(self):
		# covers: AC-9 (any failed check on the control site means no drop)
		stub = RemovalControlStub(
			[self.drop()], answers={"drop_starting": {"proceed": False, "reason": "not approved"}}
		)
		_state, drop_site, _finish = self.run_drop(stub)
		drop_site.assert_not_called()
		self.assertEqual(stub.methods(), ["report_sites", "drop_starting"])
		self.assertIn("the control site said no: not approved", self.lines[-1])

	def test_a_go_ahead_without_a_valid_signature_drops_nothing(self):
		# covers: AC-9, AC-15
		stub = RemovalControlStub([self.drop()], answers=PROCEED, badly_signed=("drop_starting",))
		_state, drop_site, _finish = self.run_drop(stub)
		drop_site.assert_not_called()
		self.assertEqual(stub.bodies("drop_done"), [])
		self.assertEqual(stub.bodies("step_failed"), [])

	def test_a_go_ahead_that_isnt_exactly_true_drops_nothing(self):
		# covers: AC-9
		for proceed in ("yes", 1, None):
			with self.subTest(proceed=proceed):
				stub = RemovalControlStub([self.drop()], answers={"drop_starting": {"proceed": proceed}})
				_state, drop_site, _finish = self.run_drop(stub)
				drop_site.assert_not_called()

	def test_a_site_that_paid_or_has_a_payment_pending_is_never_dropped(self):
		# covers: AC-9 (the runner's own fresh read), AC-11
		cases = {
			"phase is active": {"paid_until": add_days(site_today(), 365), "provider": "PayPal"},
			"a payment is pending": {"checkout_started_on": utc_now() - timedelta(hours=1)},
		}
		for reason, values in cases.items():
			with self.subTest(reason=reason):
				store_facts(**values)
				stub = RemovalControlStub([self.drop()], answers=PROCEED)
				_state, drop_site, _finish = self.run_drop(stub)
				drop_site.assert_not_called()
				self.assertEqual(stub.methods(), ["report_sites"], "drop_starting is never asked")
				self.assertIn(reason, self.lines[-1])
				store_facts(paid_until=None, provider=None, checkout_started_on=None)

	def test_a_site_before_its_removal_date_is_never_dropped(self):
		# covers: AC-9
		store_facts(trial_started_on=utc_now() - timedelta(days=27))
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		_state, drop_site, _finish = self.run_drop(stub)
		drop_site.assert_not_called()
		self.assertIn("removal date hasn't come", self.lines[-1])

	def test_switching_the_mode_off_mid_run_stops_the_drop(self):
		# covers: AC-9 (`books_removal_mode` is `live` at that moment)
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		with patch("frappe_books.subscription.runner.read_mode", side_effect=["live", "off"]):
			_state, drop_site, _finish = self.run_drop(stub)
		drop_site.assert_not_called()
		self.assertEqual(stub.bodies("drop_starting"), [])
		self.assertIn("books_removal_mode is now off", self.lines[-1])

	def test_a_dry_run_only_logs_would_drop(self):
		# covers: AC-14
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		site_state, drop_site, finish_drop = self.run_drop(stub, mode="dry_run")
		site_state.assert_not_called()
		drop_site.assert_not_called()
		finish_drop.assert_not_called()
		self.assertEqual(stub.methods(), ["report_sites"])
		self.assertIn(f"would drop {frappe.local.site}", self.lines[-1])

	def test_a_site_already_gone_is_reported_done(self):
		# covers: AC-10 (safe to repeat, also for a site this run can't read)
		gone = "gone.example.com"
		stub = RemovalControlStub([self.drop(gone)])
		with runner_bench(stub, sites=[]) as bench:
			archive = os.path.join(bench, "books-removal", "archived", CASE)
			os.makedirs(os.path.join(archive, gone))
			with (
				patch("frappe_books.subscription.runner.site_state", return_value=(False, False)),
				patch("frappe_books.subscription.runner.drop_site") as drop_site,
			):
				self.assertEqual(run(bench_path=bench, log=self.lines.append), 0)
			self.assertFalse(os.path.lexists(archive), "a leftover archived folder is deleted")
		drop_site.assert_not_called()
		self.assertEqual(stub.methods(), ["report_sites", "drop_done"])
		self.assertEqual(stub.bodies("drop_done")[0]["site"], gone)
		self.assertIn(f"drop {CASE} already gone", self.lines[-1])

	def test_a_drop_cut_short_after_the_database_is_finished(self):
		# covers: AC-10 (the database is gone but the folder remains)
		half = "half.example.com"
		stub = RemovalControlStub([self.drop(half)])
		_state, drop_site, finish_drop = self.run_drop(stub, state=(True, False), sites=[half])
		drop_site.assert_not_called()
		self.assertEqual(finish_drop.call_args.args[0], half)
		self.assertEqual(stub.methods(), ["report_sites", "drop_done"])
		self.assertEqual(self.archive_left, [])
		self.assertIn(f"drop {CASE} finished an earlier drop", self.lines[-1])

	def test_a_failed_drop_is_reported_with_the_secrets_removed(self):
		# covers: AC-12
		def broken(_site, _config, _archive):
			raise RuntimeError(f"Access denied for root using {ROOT_PASSWORD}")

		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		self.run_drop(stub, drop=broken)
		(failed,) = stub.bodies("step_failed")
		self.assertEqual((failed["case"], failed["step"]), (CASE, "drop"))
		self.assertEqual(failed["error"], "RuntimeError: Access denied for root using ***")
		self.assertEqual(stub.bodies("drop_done"), [])

	def test_no_root_login_is_a_failed_drop_step(self):
		# covers: AC-10 (root credentials only from the secrets file), AC-12
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		site_state, drop_site, _finish = self.run_drop(stub, secrets=runner_secrets(root_password=None))
		site_state.assert_not_called()
		drop_site.assert_not_called()
		(failed,) = stub.bodies("step_failed")
		self.assertIn("root_login and root_password are needed", failed["error"])

	def test_a_site_whose_state_cant_be_told_is_a_failed_drop_step(self):
		# covers: AC-9 (any doubt means no drop)
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		with patch(
			"frappe_books.subscription.runner.site_state",
			side_effect=RuntimeError("Can't connect to MySQL server"),
		):
			with runner_bench(stub) as bench, patch("frappe_books.subscription.runner.drop_site") as drop:
				run(bench_path=bench, log=self.lines.append)
		drop.assert_not_called()
		self.assertEqual(stub.bodies("step_failed")[0]["step"], "drop")
		self.assertEqual(stub.bodies("drop_starting"), [])

	def test_a_drop_done_the_control_site_cannot_hear_is_logged(self):
		# covers: AC-10 (the next run's `drop` finds the site gone and reports it again)
		stub = RemovalControlStub([self.drop()], answers=PROCEED)
		answer_signed = stub.post

		def answer(url, data, headers, timeout):
			if url.endswith("drop_done"):
				raise requests.Timeout("slow")
			return answer_signed(url, data, headers, timeout)

		stub.post = answer
		self.run_drop(stub)
		self.assertIn("drop_done wasn't heard", self.lines[-1])
		self.assertEqual(stub.bodies("step_failed"), [])

	def test_unsafe_site_or_case_names_in_a_drop_are_ignored(self):
		# covers: AC-15 (a name from the control site never leaves the sites folder)
		bad = [
			self.drop("../frappe-bench"),
			self.drop(".hidden"),
			self.drop("a/b.example.com"),
			self.drop("double..dot.com"),
			self.drop(case="archived"),
		]
		stub = RemovalControlStub(bad, answers=PROCEED)
		site_state, drop_site, _finish = self.run_drop(stub)
		site_state.assert_not_called()
		drop_site.assert_not_called()
		self.assertEqual(sum("ignored an instruction" in line for line in self.lines), 5)


def fake_export(out_dir):
	"""A tiny export, for runner tests about anything but the export's content."""
	os.makedirs(out_dir, exist_ok=True)
	with open(os.path.join(out_dir, "README.txt"), "w") as handle:
		handle.write("test")
	return {"doctypes": 0, "rows": 0, "files": 0, "bytes": 4}


def read_csv(path):
	with open(path, encoding="utf-8-sig", newline="") as handle:
		return list(csv.DictReader(handle))
