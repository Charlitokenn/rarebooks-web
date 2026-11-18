"""Whitelisted methods /books calls for the subscription status (spec 0005)."""

import frappe

from frappe_books.subscription.clock import DOCTYPE, current_clock


@frappe.whitelist(methods=["GET"])
def get_subscription() -> dict:
	"""The status dict, for the Subscription page and the banner. Allowed on a locked site."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	return current_clock().status()
