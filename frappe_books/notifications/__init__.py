"""Push notifications through Firebase Cloud Messaging (spec 0026).

Hooks, the boot and `bench execute` reach these through `frappe_books.notifications.<name>`.
Only `notifications/fcm.py` talks to Google.
"""

from frappe_books.notifications.devices import (
	boot_block,
	delete_stale_devices,
	get_permission_query_conditions,
	has_permission,
	register_device,
	unregister_device,
)
from frappe_books.notifications.events import (
	check_low_stock,
	item_saved,
	notify_subscription_phase,
	payment_submitted,
	pos_sale_paid,
)
from frappe_books.notifications.sending import notify, send_job

__all__ = [
	"boot_block",
	"check_low_stock",
	"delete_stale_devices",
	"get_permission_query_conditions",
	"has_permission",
	"item_saved",
	"notify",
	"notify_subscription_phase",
	"payment_submitted",
	"pos_sale_paid",
	"register_device",
	"send_job",
	"unregister_device",
]
