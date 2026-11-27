import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.website.path_resolver import PathResolver
from frappe.website.serve import get_response_without_exception_handling

from frappe_books.pwa import ServiceWorkerPage


class IntegrationTestPWA(IntegrationTestCase):
	def test_service_worker_is_a_script_under_the_app_scope(self):
		set_request(method="GET", path="/books/sw.js")
		response = get_response_without_exception_handling()
		script = response.get_data(as_text=True)

		self.assertEqual(response.mimetype, "text/javascript")
		self.assertNotIn("__BUILD__", script)
		self.assertIn("<svg", script)

	def test_other_app_routes_still_open_books(self):
		set_request(method="GET", path="/books/list/SalesInvoice")
		endpoint, renderer = PathResolver("books/list/SalesInvoice").resolve()

		self.assertEqual(endpoint, "books")
		self.assertNotIsInstance(renderer, ServiceWorkerPage)

	def test_manifest_scope_covers_the_app_without_a_trailing_slash(self):
		# Chrome shows its out of scope bar on /books when the scope is /books/.
		manifest = json.loads(
			Path(frappe.get_app_path("frappe_books", "public", "pwa", "manifest.json")).read_text()
		)

		for path in ("/books", "/books/", manifest["start_url"]):
			self.assertTrue(path.startswith(manifest["scope"]), path)
