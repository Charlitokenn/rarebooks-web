import frappe

from frappe_books.hooks import app_name, app_title

OLD_TITLE = "Books"


def execute():
	"""Rename the desk's Books app icon, seeded under the old app_title, to the app's current title."""
	icon = frappe.db.get_value("Desktop Icon", {"app": app_name, "icon_type": "App", "label": OLD_TITLE})
	if not icon or frappe.db.exists("Desktop Icon", app_title):
		return
	frappe.rename_doc("Desktop Icon", icon, app_title, force=True)
	frappe.db.set_value("Desktop Icon", app_title, "label", app_title)
