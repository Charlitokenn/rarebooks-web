"""Trial end export and removal, the customer site side (spec 0007): its removal status, the hold fields and the
export layout. The signed endpoints and the export job are in `test_subscription_remote.py` (spec 0010)."""

import csv
import gzip
import os
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_datetime, getdate

from frappe_books.subscription.clock import DOCTYPE, _local_date, current_clock, site_zone, utc_now
from frappe_books.subscription.removal import (
	PendingWritesError,
	_session_isolation_level,
	build_export,
	clear_removal,
	mark_export_sent,
	removal_status,
)
from frappe_books.subscription.state import apply_state
from frappe_books.tests.accounting import insert_sales_invoice
from frappe_books.tests.subscription import SubscriptionTestMixin, lock_site, managed_site, store_facts

SENT_ON = "2031-01-30T09:00:00+00:00"
HOLD_UNTIL = "2031-02-02T09:00:00+00:00"


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
		# Spec 0010 AC-8: Frappe Cloud keeps backups of an archived site, so no "no other copy" promise.
		self.assertIn("the hosting provider may keep backups of the site", readme)
		self.assertNotIn("no other copy", readme.lower())

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

	def test_an_export_puts_the_session_isolation_level_back(self):
		# covers: AC-6 (one REPEATABLE READ snapshot), on MariaDB below 11.1 too, which has only `tx_isolation`
		frappe.db.rollback()
		frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
		self.addCleanup(frappe.db.sql, "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
		with patch("frappe_books.subscription.removal._write_database_backup"):
			build_export(self.out)
		self.assertEqual(_session_isolation_level(), "READ COMMITTED")

	def test_an_export_refuses_to_commit_pending_writes(self):
		frappe.db.set_single_value("Books Accounting Settings", "company_name", "Uncommitted Co")
		self.assertRaises(PendingWritesError, build_export, self.out)
		frappe.db.rollback()


def read_csv(path):
	with open(path, encoding="utf-8-sig", newline="") as handle:
		return list(csv.DictReader(handle))
