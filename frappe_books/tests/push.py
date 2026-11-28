"""Push notification test config (spec 0026). `bench execute` these to turn push on or off for the browser tests."""

import json

import frappe
from frappe.installer import update_site_config

from frappe_books.notifications.fcm import CONFIG_KEYS, TOKEN_CACHE_KEY

# Not a real key: a send with it fails at Google, and tests patch every call to Google.
TEST_SERVICE_ACCOUNT = {
	"type": "service_account",
	"project_id": "books-push-test",
	"client_email": "push@books-push-test.iam.gserviceaccount.com",
	"private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
}
TEST_WEB_CONFIG = {
	"apiKey": "test-api-key",
	"projectId": "books-push-test",
	"messagingSenderId": "1234567890",
	"appId": "1:1234567890:web:abc",
}
TEST_VAPID_KEY = "test-vapid-key"


def test_push_config(service_account: dict | None = None) -> dict:
	return {
		"books_fcm_service_account": json.dumps(service_account or TEST_SERVICE_ACCOUNT),
		"books_fcm_web_config": json.dumps(TEST_WEB_CONFIG),
		"books_fcm_vapid_key": TEST_VAPID_KEY,
	}


def turn_push_on():
	"""Test keys in this site's own config, so the bench's real keys stay untouched."""
	for key, value in test_push_config().items():
		update_site_config(key, value)
	# The boot is cached per user, so drop it for the next page load.
	frappe.clear_cache()


def turn_push_off():
	for key in CONFIG_KEYS:
		update_site_config(key, "None")
	frappe.cache.delete_value(TOKEN_CACHE_KEY)
	frappe.clear_cache()
