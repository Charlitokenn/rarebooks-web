"""For the support chat browser tests (spec 0009): `bench execute` these to turn the chat on or off."""

import frappe
from frappe.installer import update_site_config

from frappe_books.support_chat import CONFIG_KEYS

TEST_CHAT_CONFIG = {
	"books_tawk_property_id": "test-property",
	"books_tawk_widget_id": "test-widget",
	"books_tawk_api_key": "test-secure-mode-key",
}


def turn_chat_on(support_email: str = "help@books.test"):
	"""Test keys in this site's own config, so the bench's real keys stay untouched."""
	for key, value in TEST_CHAT_CONFIG.items():
		update_site_config(key, value)
	update_site_config("books_support_email", support_email or "None")
	# The boot is cached per user, so drop it for the next page load.
	frappe.clear_cache()


def turn_chat_off():
	for key in (*CONFIG_KEYS, "books_support_email"):
		update_site_config(key, "None")
	frappe.clear_cache()
