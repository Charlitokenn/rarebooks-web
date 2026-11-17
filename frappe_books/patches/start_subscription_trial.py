from frappe_books.subscription import start_trial


def execute():
	"""Start the trial clock on an existing site, from the moment this patch runs (spec 0005, AC-1)."""
	start_trial()
