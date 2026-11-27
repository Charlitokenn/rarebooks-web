"""The site's side of bulk import from the control site: the read side and the CSV builder (spec 0025)."""

import csv
import io
import json
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.subscription import bulk_import
from frappe_books.subscription.clock import utc_now
from frappe_books.tests.accounting import make_account, make_item, unique_name
from frappe_books.tests.subscription import (
	TEST_SECRET,
	SubscriptionTestMixin,
	iso_ago,
	lock_site,
	managed_site,
	store_facts,
	unlock_site,
)
from frappe_books.tests.test_subscription_remote import signed_json, site_call

IMPORTER_TS = Path(frappe.get_app_path("frappe_books")).parent / "frontend" / "src" / "importer.ts"
STOCK_DOCTYPES = ["Books Stock Movement", "Books Shipment", "Books Purchase Receipt", "Books Location"]


def lapse_site():
	"""A paid site whose paid period ended 10 days ago, past its grace."""
	store_facts(
		trial_started_on=utc_now() - timedelta(days=90),
		paid_until=utc_now().date() - timedelta(days=10),
		provider="PayPal",
		billing_period="Yearly",
		auto_renews=0,
		exempt=0,
	)


def wizard_schema_names() -> tuple[list[str], list[str]]:
	"""The schema names `getImportableSchemaNames` lists, and the ones it adds with inventory on."""
	source = IMPORTER_TS.read_text()
	body = re.search(r"function getImportableSchemaNames.*?\n}\n", source, re.S).group(0)
	listed, stock = body.split("enable_inventory", 1)
	pick = lambda text: re.findall(r"ModelNameEnum\.(\w+)", text)  # noqa: E731
	return pick(listed), pick(stock)


def csv_rows(text: str) -> list[list[str]]:
	return list(csv.reader(io.StringIO(text)))


class IntegrationTestBulkImportColumns(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for patcher in (
			managed_site(),
			patch("frappe_books.subscription.remote.site_secret", return_value=TEST_SECRET),
		):
			patcher.__enter__()
			self.addCleanup(patcher.__exit__, None, None, None)
		frappe.cache.delete_keys("rl:")
		unlock_site()

	def set_inventory(self, enabled: int):
		saved = frappe.db.get_single_value(bulk_import.INVENTORY_SETTINGS, "enable_inventory")
		frappe.db.set_single_value(bulk_import.INVENTORY_SETTINGS, "enable_inventory", enabled)
		frappe.db.commit()

		def restore():
			frappe.db.set_single_value(bulk_import.INVENTORY_SETTINGS, "enable_inventory", saved)
			frappe.db.commit()

		self.addCleanup(restore)

	def test_import_columns_lists_the_wizard_types_with_their_columns(self):
		# covers: AC-3
		self.set_inventory(0)
		body, response = site_call("import_columns")
		self.assertEqual(response.status_code, 200)
		answer = signed_json(response)
		self.assertEqual(answer["issued_at"], body["issued_at"])
		self.assertIn("date_format", answer)
		self.assertIn("number_format", answer)
		doctypes = [kind["doctype"] for kind in answer["types"]]
		self.assertEqual(doctypes[:2], ["Books Sales Invoice", "Books Purchase Invoice"])
		self.assertFalse(set(STOCK_DOCTYPES) & set(doctypes))

		item = next(kind for kind in answer["types"] if kind["doctype"] == "Books Item")
		self.assertEqual(item["schema_name"], "Item")
		self.assertFalse(item["submittable"])
		name = item["columns"][0]
		self.assertEqual((name["key"], name["label"], name["required"]), ("name", "Item Name", True))
		usage = next(column for column in item["columns"] if column["key"] == "item_usage")
		self.assertEqual(usage["fieldtype"], "Select")
		self.assertTrue(usage["options"])
		uom = next(column for column in item["columns"] if column["key"] == "uom_conversions.uom")
		self.assertEqual(
			(uom["label"], uom["table_label"], uom["required"]),
			("UOM (UOM Conversions)", "UOM Conversions", False),
		)

		invoice = next(kind for kind in answer["types"] if kind["doctype"] == "Books Sales Invoice")
		self.assertTrue(invoice["submittable"])

	def test_the_stock_types_show_only_with_inventory_on(self):
		# covers: AC-3
		self.set_inventory(1)
		_body, response = site_call("import_columns")
		doctypes = [kind["doctype"] for kind in signed_json(response)["types"]]
		self.assertEqual(doctypes[-4:], STOCK_DOCTYPES)

	def test_a_locked_or_lapsed_site_answers_site_locked(self):
		# covers: AC-11
		for label, setup in {"locked": lock_site, "lapsed": lapse_site}.items():
			with self.subTest(label):
				setup()
				body, response = site_call("import_columns")
				self.assertEqual(response.status_code, 409)
				self.assertEqual(
					signed_json(response), {"status": "site_locked", "issued_at": body["issued_at"]}
				)

	def test_a_bad_signature_a_stale_call_or_another_site_gets_a_signed_401(self):
		# covers: AC-11
		cases = {
			"bad signature": {"secret": b"not-the-secret-0123456789abcdef0123456789"},
			"stale": {"issued_at": iso_ago(minutes=6)},
			"another site": {"site": "other.example.com"},
		}
		for label, overrides in cases.items():
			with self.subTest(label):
				body, response = site_call("import_columns", **overrides)
				self.assertEqual(response.status_code, 401)
				self.assertEqual(signed_json(response), {"issued_at": body["issued_at"]})
		with managed_site(False):
			_body, response = site_call("import_columns")
		self.assertEqual(response.status_code, 401)


class IntegrationTestBulkImportRules(IntegrationTestCase):
	def test_the_type_list_matches_the_wizard(self):
		# covers: AC-15
		listed, stock = wizard_schema_names()
		self.assertEqual(list(bulk_import.IMPORTABLE), listed)
		self.assertEqual(list(bulk_import.STOCK_IMPORTABLE), stock)
		templates = [template["schema_name"] for template in bulk_import._templates()]
		self.assertEqual(templates, listed + stock)

	def test_every_listed_doctype_allows_import(self):
		# covers: AC-15
		for template in bulk_import._templates():
			with self.subTest(template["doctype"]):
				self.assertTrue(frappe.get_meta(template["doctype"]).allow_import)

	def test_the_columns_are_the_wizard_template_keys(self):
		# covers: AC-15
		with patch.object(bulk_import.frappe.db, "get_single_value", return_value=1):
			doctypes = bulk_import.importable_doctypes()
		for template in bulk_import._templates():
			with self.subTest(template["doctype"]):
				self.assertIn(template["doctype"], doctypes)
				keys = [column["key"] for column in bulk_import.type_columns(template["doctype"])]
				self.assertEqual(keys, [column["key"] for column in template["columns"]])

	def test_only_the_site_list_is_importable(self):
		# covers: AC-13
		self.assertTrue(bulk_import.is_importable("Books Item"))
		for doctype in ("User", "Role", "Data Import", "Books Subscription", None, ["Books Item"]):
			with self.subTest(doctype):
				self.assertFalse(bulk_import.is_importable(doctype))

	def test_rows_must_carry_unique_ids_and_known_keys(self):
		# covers: AC-13
		good = [{"id": "a1", "cells": {"name": "Pen"}}]
		self.assertTrue(bulk_import.valid_rows(good, "Books Item"))
		bad = {
			"empty": [],
			"unknown key": [{"id": "a1", "cells": {"owner": "x"}}],
			"duplicate id": [*good, *good],
			"bad id": [{"id": "a b", "cells": {}}],
			"not text": [{"id": "a1", "cells": {"rate": 3}}],
		}
		for label, rows in bad.items():
			with self.subTest(label):
				self.assertFalse(bulk_import.valid_rows(rows, "Books Item"))


class IntegrationTestBulkImportCsv(IntegrationTestCase):
	def build(self, rows, date_format="dd-mm-yyyy", number_format="#,###.##"):
		with patch.object(
			bulk_import, "formats", return_value={"date_format": date_format, "number_format": number_format}
		):
			text, row_ids = bulk_import.build_import_csv("Books Item", rows)
		return csv_rows(text), row_ids

	def test_an_item_file_has_docstatus_and_the_name_and_drops_blank_rows(self):
		# covers: AC-17
		matrix, row_ids = self.build(
			[
				{"id": "r1", "cells": {"name": "Pen", "rate": "1,250.50", "item_usage": "Sales"}},
				{"id": "r2", "cells": {"name": "", "rate": ""}},
				{"id": "r3", "cells": {"name": "Ink", "rate": "7"}},
			]
		)
		header = matrix[0]
		self.assertEqual(header[:2], ["docstatus", "name"])
		self.assertNotIn("uom_conversions.name", header)
		rate = header.index("rate")
		self.assertEqual([row[0] for row in matrix[1:]], ["0", "0"])
		self.assertEqual([row[1] for row in matrix[1:]], ["Pen", "Ink"])
		self.assertEqual([row[rate] for row in matrix[1:]], ["1250.50", "7"])
		self.assertEqual(row_ids, ["r1", "r3"])

	def test_a_document_rows_come_together_with_parent_values_on_the_first(self):
		# covers: AC-17
		matrix, row_ids = self.build(
			[
				{"id": "r1", "cells": {"name": "Pen", "uom_conversions.uom": "Box", "rate": "2"}},
				{"id": "r2", "cells": {"name": "Ink", "rate": "3"}},
				{"id": "r3", "cells": {"name": "Pen", "uom_conversions.uom": "Pack", "rate": "5"}},
			]
		)
		header = matrix[0]
		rate, uom = header.index("rate"), header.index("uom_conversions.uom")
		self.assertEqual(row_ids, ["r1", "r3", "r2"])
		self.assertEqual(
			[(row[0], row[1], row[rate], row[uom]) for row in matrix[1:]],
			[
				("0", "Pen", "5", "Box"),
				("", "", "", "Pack"),
				("0", "Ink", "3", ""),
			],
		)

	def test_numbers_are_written_in_the_site_format_and_an_ambiguous_one_as_typed(self):
		# covers: AC-17
		matrix, _row_ids = self.build(
			[
				{"id": "r1", "cells": {"name": "Pen", "rate": "1.234,5"}},
				{"id": "r2", "cells": {"name": "Ink", "rate": "1234.5"}},
				{"id": "r3", "cells": {"name": "Pad", "rate": "1.234"}},
			],
			number_format="#.###,##",
		)
		rate = matrix[0].index("rate")
		self.assertEqual([row[rate] for row in matrix[1:]], ["1234,5", "1234,5", "1.234"])

	def test_dates_in_the_site_format_or_iso_are_written_as_iso(self):
		# covers: AC-17
		cell_format = bulk_import._CellFormat({"date_format": "dd-mm-yyyy", "number_format": "#,###.##"})
		date, stamp = {"fieldtype": "Date"}, {"fieldtype": "Datetime"}
		self.assertEqual(cell_format.text("31-01-2031", date), "2031-01-31")
		self.assertEqual(cell_format.text("2031-01-31", date), "2031-01-31")
		self.assertEqual(cell_format.text("31/01/2031", date), "31/01/2031")
		self.assertEqual(cell_format.text("31-01-2031 09:30", stamp), "2031-01-31 09:30:00")
		self.assertEqual(cell_format.text("2031-01-31T09:30:15", stamp), "2031-01-31 09:30:15")

	def test_the_templates_file_is_valid_json_with_a_name_column_first(self):
		# covers: AC-3
		for template in json.loads(bulk_import.TEMPLATES_FILE.read_text()):
			with self.subTest(template["doctype"]):
				self.assertEqual(template["columns"][0]["key"], template["name_key"])


def new_ref() -> str:
	return f"BIMP-{frappe.generate_hash(length=10).translate(str.maketrans('abcdef', '123456'))}-1"


def item_rows(income: str, expense: str, *names: str, **cells) -> list[dict]:
	return [
		{
			"id": f"row-{index}",
			"cells": {
				"name": name,
				"item_usage": "Both",
				"income_account": income,
				"expense_account": expense,
				"rate": "12.50",
				**cells,
			},
		}
		for index, name in enumerate(names)
	]


def counts() -> tuple[int, int]:
	return frappe.db.count("Data Import"), frappe.db.count("File")


class IntegrationTestBulkImportCalls(SubscriptionTestMixin, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.income = make_account("Bulk Income", root_type="Income", account_type="Income Account").name
		cls.expense = make_account("Bulk Expense", root_type="Expense", account_type="Expense Account").name
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		for patcher in (
			managed_site(),
			patch("frappe_books.subscription.remote.site_secret", return_value=TEST_SECRET),
		):
			patcher.__enter__()
			self.addCleanup(patcher.__exit__, None, None, None)
		frappe.cache.delete_keys("rl:")
		unlock_site()

	def rows(self, *names, **cells):
		return item_rows(self.income, self.expense, *names, **cells)

	def start(self, ref, rows, submit=0):
		return site_call(
			"start_import", {"import_ref": ref, "import_type": "Books Item", "submit": submit, "rows": rows}
		)

	def test_the_dry_run_marks_each_bad_cell_and_saves_nothing(self):
		# covers: AC-5, AC-6
		rows = self.rows(unique_name("Pen"), unique_name("Ink"), unique_name("Pad"))
		rows[0]["cells"]["rate"] = "twelve"
		rows[1]["cells"]["item_usage"] = "Everything"
		rows[2]["cells"]["income_account"] = "No Such Account"
		before = counts()
		folder = Path(frappe.get_site_path("private", "files"))
		files_before = set(folder.glob("books-bulk-preview-*"))

		_body, response = site_call("preview_import", {"import_type": "Books Item", "rows": rows})

		self.assertEqual(response.status_code, 200)
		warnings = signed_json(response)["warnings"]
		by_column = {warning["column_key"]: warning for warning in warnings}
		self.assertEqual(by_column["rate"]["row_ids"], ["row-0"])
		self.assertEqual(by_column["item_usage"]["row_ids"], ["row-1"])
		self.assertEqual(by_column["income_account"]["row_ids"], ["row-2"])
		self.assertTrue(all(by_column[key]["blocking"] for key in ("rate", "item_usage", "income_account")))
		self.assertFalse(any("<" in warning["message"] for warning in warnings))
		self.assertEqual(counts(), before)
		self.assertEqual(set(folder.glob("books-bulk-preview-*")), files_before)

	def test_good_rows_pass_the_dry_run(self):
		# covers: AC-5, AC-6
		_body, response = site_call(
			"preview_import", {"import_type": "Books Item", "rows": self.rows(unique_name("Pen"))}
		)
		warnings = signed_json(response)["warnings"]
		self.assertFalse([warning for warning in warnings if warning["blocking"]])

	def test_a_start_imports_once_as_administrator_and_reports_each_row(self):
		# covers: AC-7, AC-8, AC-9, AC-16
		ref, names = new_ref(), [unique_name("Pen"), unique_name("Ink")]
		rows = self.rows(*names)

		_body, response = self.start(ref, rows)
		self.assertEqual(response.status_code, 200)
		answer = signed_json(response)
		name = f"CTRL-{ref}"
		self.assertEqual((answer["data_import"], answer["started"]), (name, True))
		data_import = frappe.get_doc("Data Import", name)
		self.assertEqual((data_import.import_type, data_import.mute_emails), ("Insert New Records", 1))
		self.assertEqual(data_import.status, "Success")
		self.assertEqual(frappe.db.get_value("Books Item", names[0], "owner"), "Administrator")
		# The private CSV is gone once it finished; its logs stay.
		self.assertFalse(frappe.db.exists("File", {"attached_to_name": name}))

		_body, again = self.start(ref, rows)
		self.assertEqual(signed_json(again)["started"], False)
		self.assertEqual(frappe.db.count("Data Import", {"name": ("like", f"CTRL-{ref}%")}), 1)

		_body, conflict = self.start(ref, self.rows(unique_name("Other")))
		self.assertEqual(conflict.status_code, 409)
		self.assertEqual(signed_json(conflict)["status"], "ref_conflict")

		_body, report = site_call("import_report", {"data_import": name})
		report = signed_json(report)
		self.assertEqual((report["status"], report["total"], report["processed"]), ("Success", 2, 2))
		self.assertEqual([log["row_ids"] for log in report["logs"]], [["row-0"], ["row-1"]])
		self.assertEqual([log["docname"] for log in report["logs"]], names)
		self.assertFalse(report["more"])

	def test_a_row_naming_an_existing_record_fails_and_the_record_stays(self):
		# covers: AC-13
		existing = make_item(self.income, self.expense, rate=3)
		frappe.db.commit()
		ref = new_ref()
		_body, response = self.start(ref, self.rows(existing.name, rate="99"))
		self.assertEqual(response.status_code, 200)
		_body, report = site_call("import_report", {"data_import": f"CTRL-{ref}"})
		[log] = signed_json(report)["logs"]
		self.assertFalse(log["success"])
		self.assertTrue(log["message"])
		self.assertEqual(frappe.db.get_value("Books Item", existing.name, "rate"), 3)

	def test_a_type_outside_the_list_or_bad_rows_is_refused(self):
		# covers: AC-13
		before = counts()
		for doctype in ("User", "Role"):
			with self.subTest(doctype):
				_body, response = site_call(
					"start_import",
					{
						"import_ref": new_ref(),
						"import_type": doctype,
						"submit": 0,
						"rows": [{"id": "a", "cells": {}}],
					},
				)
				self.assertEqual(response.status_code, 400)
		_body, response = self.start("not-a-ref", self.rows(unique_name("Pen")))
		self.assertEqual(response.status_code, 400)
		self.assertEqual(counts(), before)

	def test_a_locked_site_refuses_writes_but_still_reports(self):
		# covers: AC-11
		ref = new_ref()
		self.start(ref, self.rows(unique_name("Pen")))
		for setup in (lock_site, lapse_site):
			with self.subTest(setup.__name__):
				setup()
				before = counts()
				for method, values in {
					"preview_import": {"import_type": "Books Item", "rows": self.rows(unique_name("Pen"))},
					"start_import": {
						"import_ref": new_ref(),
						"import_type": "Books Item",
						"submit": 0,
						"rows": self.rows(unique_name("Pen")),
					},
				}.items():
					_body, response = site_call(method, values)
					self.assertEqual(response.status_code, 409, method)
					self.assertEqual(signed_json(response)["status"], "site_locked")
				self.assertEqual(counts(), before)
				_body, report = site_call("import_report", {"data_import": f"CTRL-{ref}"})
				self.assertEqual(report.status_code, 200)

	def test_the_scheduler_off_answers_503_and_creates_nothing(self):
		# covers: AC-11
		before = counts()
		with patch("frappe_books.subscription.bulk_import._scheduler_off", return_value=True):
			_body, response = self.start(new_ref(), self.rows(unique_name("Pen")))
		self.assertEqual(response.status_code, 503)
		self.assertEqual(signed_json(response)["status"], "scheduler_inactive")
		self.assertEqual(counts(), before)

	def test_a_body_over_2_mb_is_refused(self):
		# covers: AC-12
		rows = self.rows(unique_name("Pen"), description="x" * 9000)
		rows = [{**rows[0], "id": f"r{index}"} for index in range(240)]
		_body, response = site_call("preview_import", {"import_type": "Books Item", "rows": rows})
		self.assertEqual(response.status_code, 413)

	def test_the_report_refuses_a_name_that_is_not_a_control_import(self):
		# covers: AC-9
		_body, response = site_call("import_report", {"data_import": "Books Item Import on 2031"})
		self.assertEqual(response.status_code, 400)
		_body, response = site_call("import_report", {"data_import": "CTRL-BIMP-99999-1"})
		self.assertEqual(response.status_code, 404)
