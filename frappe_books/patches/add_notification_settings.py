import frappe

SETTINGS = "Books Notification Settings"
EVENTS = ("payment_received", "low_stock", "subscription")


def execute():
	"""Turn every push event on for a site migrated to spec 0026 (AC-8); a value already set stays."""
	stored = frappe.db.get_singles_dict(SETTINGS)
	for fieldname in EVENTS:
		if stored.get(fieldname) is None:
			frappe.db.set_single_value(SETTINGS, fieldname, 1)
