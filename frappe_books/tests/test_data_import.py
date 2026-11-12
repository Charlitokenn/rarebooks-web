from unittest.mock import patch

import frappe
from frappe.core.doctype.data_import.data_import import form_start_import, get_import_status
from frappe.tests import IntegrationTestCase

from frappe_books.tests.accounting import make_account, make_item, make_party, unique_name
from frappe_books.tests.test_books_page import _make_user

MANAGER = "books-data-import-manager@example.com"


class IntegrationTestDataImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_make_user(MANAGER, "Books Manager")

	def test_wizard_file_makes_one_numbered_invoice_per_document(self):
		receivable = make_account("Import Receivable", account_type="Receivable")
		income = make_account("Import Income", root_type="Income", account_type="Income Account")
		expense = make_account("Import Expense", root_type="Expense", account_type="Expense Account")
		party = make_party(receivable.name)
		item = make_item(income.name, expense.name)
		rows = [
			"docstatus,party,account,date,items.item,items.quantity,items.rate",
			f"0,{party.name},{receivable.name},2031-01-05 10:00:00,{item.name},2,10",
			f",,,,{item.name},1,5",
		]

		with self.set_user(MANAGER):
			data_import = _run_import("Books Sales Invoice", "\r\n".join(rows))

		self.assertEqual(get_import_status(data_import)["status"], "Success")
		invoice = frappe.get_last_doc("Books Sales Invoice", filters={"party": party.name})
		self.assertTrue(invoice.name.startswith("SINV-"))
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual([row.quantity for row in invoice.items], [2, 1])

	def test_wizard_file_makes_draft_expenses_through_the_controller_rules(self):
		cash = make_account("Import Cash", account_type="Cash")
		rent = make_account("Import Rent", root_type="Expense")
		fuel = make_account("Import Fuel", root_type="Expense")
		reference, refused = unique_name("IMP").replace(" ", ""), unique_name("IMP").replace(" ", "")
		rows = [
			"docstatus,paid_from,date,reference_number,accounts.account,accounts.amount",
			f"0,{cash.name},2031-01-05,{reference},{rent.name},100",
			f",,,,{fuel.name},20",
			f"0,{cash.name},2031-01-06,{refused},{rent.name},0",
		]

		with self.set_user(MANAGER):
			data_import = _run_import("Books Expense", "\r\n".join(rows), submit=False)

		self.assertEqual(get_import_status(data_import)["status"], "Partial Success")
		expense = frappe.get_last_doc("Books Expense", filters={"reference_number": reference})
		self.assertTrue(expense.name.startswith("EXP-"))
		self.assertEqual(expense.docstatus, 0)
		self.assertEqual(expense.status, "Saved")
		self.assertEqual([row.account for row in expense.accounts], [rent.name, fuel.name])
		self.assertEqual(expense.total, 120)
		self.assertFalse(frappe.db.exists("Books Expense", {"reference_number": refused}))


def _run_import(doctype, csv, submit=True):
	"""Import `csv` as the Import Wizard does, submitting what it inserts unless `submit` is off.

	MariaDB keeps Data Import Logs (MyISAM) past the test's rollback, so each run names its own
	import: one reusing a rolled-back name would read the old logs as rows already imported.
	"""
	data_import = frappe.get_doc(
		{
			"doctype": "Data Import",
			"reference_doctype": doctype,
			"import_type": "Insert New Records",
			"submit_after_import": int(submit),
		}
	).insert(set_name=unique_name(f"{doctype} Import"))
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": "import.csv",
			"attached_to_doctype": "Data Import",
			"attached_to_name": data_import.name,
			"is_private": 1,
			"content": csv,
		}
	).insert()
	data_import.import_file = file.file_url
	data_import.save()
	# Tests run the import in the request; Frappe commits each row, so keep it in the test's transaction.
	with patch.object(frappe.db, "commit"):
		form_start_import(data_import.name)
	return data_import.name
