import frappe


def execute():
	"""Turn usage analytics on for an existing site, as a new site starts (spec 0027 AC-10).

	A Check default fills only new rows, so without this an existing single would read 0 and send nothing.
	A Books Manager can still turn it off in Settings.
	"""
	frappe.db.set_single_value("Books System Settings", "share_usage_analytics", 1)
