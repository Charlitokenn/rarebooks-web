app_name = "frappe_books"
app_title = "RareBooks"
app_publisher = "Frappe Technologies Pvt. Ltd."
app_description = "RareBooks for Frappe Framework"
app_email = "hello@frappe.io"
app_license = "agpl-3.0"
app_logo_url = "/assets/frappe_books/books-icon.png"
app_icon_url = app_logo_url
app_icon_title = app_title
app_icon_route = "/books"

# Send non-GET requests for this app's endpoints as native `application/json`
# bodies instead of form-encoded, per-key JSON-stringified values.
use_json_request_body = True

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": app_icon_url,
		"title": app_icon_title,
		"route": app_icon_route,
		"has_permission": "frappe_books.permissions.has_app_permission",
		"sequence_id": 10,
	}
]

website_route_rules = [
	{"from_route": "/books/sw.js", "to_route": "books-service-worker"},
	{"from_route": "/books/manifest.webmanifest", "to_route": "books-manifest"},
	{"from_route": "/books/<path:app_path>", "to_route": "books"},
]

page_renderer = ["frappe_books.pwa.ServiceWorkerPage", "frappe_books.pwa.ManifestPage"]
extend_bootinfo = "frappe_books.boot.extend_bootinfo"

jinja = {
	"methods": [
		"frappe_books.printing.get_print_settings",
		"frappe_books.printing.get_print_totals",
		"frappe_books.printing.books_format",
	]
}

# The search palette's index; a new site builds it now, not at Frappe's next three-hourly check.
sqlite_search = ["frappe_books.search.BooksSearch"]
after_install = ["frappe_books.setup.bootstrap", "frappe_books.search.build_search_index"]
before_tests = [
	"frappe_books.setup.before_tests",
	"frappe_books.tests.accounting.enable_features",
	"frappe_books.tests.accounting.set_default_inventory_accounts",
]

# Trial and read only lock (spec 0005): a locked site opens requests and jobs read only.
before_request = ["frappe_books.subscription.lock_request"]
before_job = ["frappe_books.subscription.lock_job"]
on_session_creation = ["frappe_books.subscription.save_known_versions"]
_refuse_when_locked = "frappe_books.subscription.refuse_when_locked"
doc_events = {
	"*": {
		event: _refuse_when_locked
		for event in (
			"before_insert",
			"validate",
			"before_submit",
			"before_cancel",
			"before_update_after_submit",
			"on_trash",
			"before_rename",
		)
	},
	# Bulk import (spec 0025 AC-16): a control site import's private CSV goes once its Data Import finishes.
	"Data Import": {"on_change": "frappe_books.subscription.delete_finished_import_file"},
}

scheduler_events = {
	# Push notifications (spec 0026 AC-7, AC-15): hourly, so a phase change pushes the same morning and the
	# daily low stock summary goes out at the first run at or after 08:00 site time.
	"hourly": [
		"frappe_books.notifications.notify_subscription_phase",
		"frappe_books.notifications.notify_low_stock_daily",
	],
	"daily": [
		"frappe_books.commerce.loyalty.expire_programs_and_points",
		"frappe_books.notifications.delete_stale_devices",
	],
}

# A user reads and deletes only their own push devices, whatever their role (spec 0026 AC-3).
permission_query_conditions = {
	"Books Push Device": "frappe_books.notifications.get_permission_query_conditions",
}
has_permission = {
	"Books Push Device": "frappe_books.notifications.has_permission",
}

export_python_type_annotations = True
require_type_annotated_api_methods = True
