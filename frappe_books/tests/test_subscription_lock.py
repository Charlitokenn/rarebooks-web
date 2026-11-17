import json
from datetime import date, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.subscription import apply_state
from frappe_books.subscription.lock import ALLOWED_METHODS, is_allowed_path
from frappe_books.tests.accounting import make_account, make_invoice, make_item, make_party
from frappe_books.tests.subscription import (
	LOCK_TYPES,
	SubscriptionTestMixin,
	call,
	exc_type,
	lock_site,
	login_sid,
	make_user,
	managed_site,
)

MANAGER = "books-manager-lock@example.com"
PASSWORD = "Lock-Test-Password-31!"


class IntegrationTestReadOnlyLock(SubscriptionTestMixin, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(MANAGER, "Books Manager", PASSWORD)
		cls.sids = {"Administrator": login_sid("Administrator"), MANAGER: login_sid(MANAGER)}
		receivable = make_account("Lock Receivable", account_type="Receivable")
		income = make_account("Lock Income", root_type="Income", account_type="Income Account")
		expense = make_account("Lock Expense", root_type="Expense", account_type="Expense Account")
		cls.party = make_party(receivable.name)
		item = make_item(income.name, expense.name)
		cls.invoice = make_invoice(
			"Books Sales Invoice", cls.party.name, receivable.name, item.name, income.name
		)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		lock_site()

	def assert_locked(self, response):
		self.assertIn(exc_type(response), LOCK_TYPES, response.json)

	def test_spike_read_only_transaction_refuses_a_write_and_ends_cleanly(self):
		with managed_site():
			# set_print_formats writes with db.set_value, so only the read only transaction stops it.
			refused = self.post(
				"/api/v2/method/frappe_books.frappe_books.doctype.books_defaults.books_defaults.set_print_formats",
				{"print_formats": {"sales_invoice_print_template": None}},
			)
			# A POST that only reads still ends with Frappe's commit, on a read only transaction.
			read = self.post("/api/method/frappe.client.get_count", {"doctype": "ToDo"})
		self.assertEqual(exc_type(refused), "InReadOnlyMode", refused.json)
		self.assertEqual(read.status_code, 200, read.json)

	def test_every_write_path_is_refused_for_every_role(self):
		party, invoice = self.party.name, self.invoice
		for user in (MANAGER, "Administrator"):
			with self.subTest(user=user), managed_site():
				attempts = {
					"insert": self.post(
						"/api/v2/document/Books Party", {"party_name": "Locked", "role": "Customer"}, user
					),
					"set_value": self.post(
						"/api/method/frappe.client.set_value",
						{
							"doctype": "Books Party",
							"name": party,
							"fieldname": "email",
							"value": "x@example.com",
						},
						user,
					),
					"submit": self.post(
						"/api/method/frappe.client.submit",
						{"doc": json.loads(frappe.as_json(invoice.as_dict()))},
						user,
					),
					"delete": self.call("delete", f"/api/v2/document/Books Party/{party}", user=user),
					"rename": self.post(
						"/api/method/frappe.client.rename_doc",
						{"doctype": "Books Party", "old_name": party, "new_name": f"{party} renamed"},
						user,
					),
				}
				for action, response in attempts.items():
					with self.subTest(action=action):
						self.assert_locked(response)
				# An insert or rename meets the doc_events hook first: the clear message, as a 403.
				# Save, submit and delete take Frappe's row lock (SELECT ... FOR UPDATE) before any hook
				# runs, so the read only transaction refuses them first, as InReadOnlyMode (503).
				for action in ("insert", "rename"):
					self.assertEqual(exc_type(attempts[action]), "SiteLockedError")
					self.assertEqual(attempts[action].status_code, 403)
		frappe.db.rollback()
		self.assertFalse(frappe.db.exists("Books Party", "Locked"))
		self.assertTrue(frappe.db.exists("Books Party", party))
		self.assertIsNone(frappe.db.get_value("Books Party", party, "email"))
		self.assertEqual(frappe.db.get_value("Books Sales Invoice", invoice.name, "docstatus"), 0)

	def test_reads_and_exports_keep_working(self):
		party, invoice = self.party.name, self.invoice.name
		# Frappe writes access logs straight to the database only in tests; a live site defers them to Redis.
		with managed_site(), patch.object(frappe, "in_test", False):
			reads = {
				"list": self.call("get", "/api/v2/document/Books Party"),
				"form": self.call(
					"get",
					"/api/method/frappe.desk.form.load.getdoc",
					{"doctype": "Books Party", "name": party},
				),
				"report": self.post(
					"/api/method/frappe.desk.query_report.run",
					{"report_name": "Books General Ledger", "filters": {}},
				),
				"search": self.post(
					"/api/method/frappe_books.search.search",
					{"text": "Test Party", "doctypes": ["Books Party"]},
				),
				"pdf": self.call(
					"get",
					"/api/method/frappe.utils.print_format.download_pdf",
					{"doctype": "Books Sales Invoice", "name": invoice},
				),
				"csv": self.post(
					"/api/method/frappe.desk.reportview.export_query",
					{
						"doctype": "Books Party",
						"file_format_type": "CSV",
						"fields": json.dumps(["`tabBooks Party`.`name`"]),
						"title": "Books Party",
					},
				),
				"desk": self.call("get", "/desk"),
				"books": self.call("get", "/books"),
			}
		for action, response in reads.items():
			with self.subTest(action=action):
				self.assertEqual(response.status_code, 200, response.data[:500])
		self.assertEqual(reads["pdf"].headers["content-type"], "application/pdf")

	def test_login_logout_and_password_reset_still_run(self):
		with managed_site():
			login = call("post", "/api/method/login", "", {"usr": MANAGER, "pwd": PASSWORD})
			reset = call(
				"post", "/api/method/frappe.core.doctype.user.user.reset_password", "", {"user": MANAGER}
			)
			logout = self.post("/api/method/logout", {}, MANAGER)
		for action, response in {"login": login, "reset": reset, "logout": logout}.items():
			with self.subTest(action=action):
				self.assertEqual(response.status_code, 200, response.json)
		type(self).sids[MANAGER] = login_sid(MANAGER)

	def test_the_allowlist_matches_v1_and_v2_method_paths_only(self):
		for name in ALLOWED_METHODS | {"frappe.integrations.oauth2_logins.login_via_google"}:
			for prefix in ("/api/method/", "/api/v2/method/"):
				with self.subTest(path=prefix + name):
					self.assertTrue(is_allowed_path(prefix + name))
		for path in (
			"/api/method/frappe.client.set_value",
			"/api/v2/document/User",
			"/books",
			"/app/login",
			"/api/method/loginx",
		):
			with self.subTest(path=path):
				self.assertFalse(is_allowed_path(path))

	def test_setup_wizard_completion_is_not_locked(self):
		method = "/api/method/frappe_books.frappe_books.doctype.books_setup_wizard.books_setup_wizard.complete_setup"
		with managed_site():
			response = self.post(method, {})
		# This site is set up already, so the wizard may refuse; the lock must not be why.
		self.assertNotIn(exc_type(response), LOCK_TYPES, response.json)

	def test_paying_lifts_the_lock_on_the_next_request(self):
		insert = {"doctype": "ToDo", "description": "after payment"}
		with managed_site():
			self.assert_locked(self.post("/api/v2/document/ToDo", insert))
			apply_state({"paid_until": (date.today() + timedelta(days=365)).isoformat()})
			frappe.db.commit()
			response = self.post("/api/v2/document/ToDo", insert)
		self.assertEqual(response.status_code, 200, response.json)
		frappe.delete_doc("ToDo", response.json["data"]["name"])

	def test_an_unmanaged_site_on_day_41_is_not_locked(self):
		with managed_site(False):
			response = self.post("/api/v2/document/ToDo", {"description": "unmanaged"})
		self.assertEqual(response.status_code, 200, response.json)
		frappe.delete_doc("ToDo", response.json["data"]["name"])

	def post(self, path, data, user="Administrator"):
		return call("post", path, self.sids[user], data)

	def call(self, method, path, data=None, user="Administrator"):
		return call(method, path, self.sids[user], data)
