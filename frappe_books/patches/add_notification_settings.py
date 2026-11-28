from frappe_books.notifications.sending import store_default_events


def execute():
	"""Turn every push event on for a site migrated to spec 0026 (AC-8); a value already set stays."""
	store_default_events()
