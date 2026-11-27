from frappe.locale import get_locale_value
from frappe.utils.jinja_globals import bundled_asset

from frappe_books.coa import chart_options
from frappe_books.regional import INDIAN_STATES
from frappe_books.settings import regional_code
from frappe_books.subscription import current_clock
from frappe_books.support_chat import boot_block as support_chat_block


def extend_bootinfo(bootinfo):
	"""Add what the Books app starts with to the session boot."""
	bootinfo.books = {
		"country_code": regional_code(),
		"charts_of_accounts": chart_options(),
		"indian_states": INDIAN_STATES,
		# The stylesheet Frappe prints with, for print previews in /books
		"print_style": bundled_asset("print.bundle.css"),
		# The trial clock and lock state, for the banner (spec 0005)
		"subscription": current_clock().status(),
		# The signed tawk.to visitor, or None when the chat is off (spec 0009)
		"support_chat": support_chat_block(),
		# The number format Frappe's importer reads for this user, which the Import Wizard writes numbers in
		# (spec 0025 AC-17): the user's Language record, else System Settings.
		"number_format": get_locale_value("number_format") or "#,###.##",
	}
