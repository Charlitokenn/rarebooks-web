import frappe

from frappe_books.notifications.events import site_now
from frappe_books.notifications.sending import SETTINGS, store_default_events


def execute():
	"""Turn the daily low stock reminder on, its first summary the next morning (spec 0026 AC-8, AC-15).

	Recording today means a site migrated mid morning does not get a summary minutes after the upgrade.
	"""
	store_default_events()
	frappe.db.set_single_value(SETTINGS, "last_low_stock_nudge_on", site_now().date())
