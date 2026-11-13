import frappe

from frappe_books.series import NUMBER_SERIES
from frappe_books.setup import DEFAULT_SERIES_START, _insert_if_missing, set_default_print_formats


def execute():
	"""Give existing sites the EXP- series, make it the default when none is set, and the expense print format."""
	prefix, reference_type, defaults_field = NUMBER_SERIES["Books Expense"]
	values = {"start": DEFAULT_SERIES_START, "pad_zeros": 4, "reference_type": reference_type}
	_insert_if_missing("Books Number Series", prefix, values)
	if not frappe.db.get_single_value("Books Defaults", defaults_field):
		frappe.db.set_single_value("Books Defaults", defaults_field, prefix)
	set_default_print_formats()
