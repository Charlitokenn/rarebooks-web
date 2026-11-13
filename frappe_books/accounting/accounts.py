import frappe
from frappe import _

PARTY_ACCOUNT_TYPES = {
	"Customer": ("Receivable",),
	"Supplier": ("Payable",),
	"Both": ("Receivable", "Payable"),
}
PAYMENT_ACCOUNT_TYPES = ("Cash", "Bank")
# The root types of the accounts the dashboard's balances card may list.
DASHBOARD_ROOT_TYPES = ("Asset", "Liability")


def validate_account(doc, fieldname, account_types=(), root_types=()):
	"""Throw unless the field holds a ledger account of one of the account types and root types."""
	account = doc.get(fieldname)
	values = account and frappe.db.get_value(
		"Books Account", account, ["is_group", "account_type", "root_type"], as_dict=True
	)
	if not values:
		return
	label = _(doc.meta.get_label(fieldname))
	if values.is_group:
		frappe.throw(_("{0} cannot be the group account {1}.").format(label, account))
	for allowed, value in ((account_types, values.account_type), (root_types, values.root_type)):
		if allowed and value not in allowed:
			frappe.throw(
				_("{0} must be of type {1}, but {2} is not.").format(
					label, " or ".join(_(option) for option in allowed), account
				)
			)


def validate_payment_account(doc, fieldname, method_type):
	"""Cash methods take cash accounts; other methods cash or bank, as the Books payment form offers."""
	validate_account(doc, fieldname, ("Cash",) if method_type == "Cash" else PAYMENT_ACCOUNT_TYPES)


def is_expense_payment_account(values) -> bool:
	"""An expense is paid from a cash or bank account, or a liability with no type (a loan or a card)."""
	if values.is_group:
		return False
	return values.account_type in PAYMENT_ACCOUNT_TYPES or (
		values.root_type == "Liability" and not values.account_type
	)


def validate_expense_payment_account(doc, fieldname):
	"""Throw unless the field holds an account an expense can be paid from."""
	account = doc.get(fieldname)
	values = account and frappe.db.get_value(
		"Books Account", account, ["is_group", "account_type", "root_type"], as_dict=True
	)
	if not values:
		return
	label = _(doc.meta.get_label(fieldname))
	if values.is_group:
		frappe.throw(_("{0} cannot be the group account {1}.").format(label, account))
	if not is_expense_payment_account(values):
		frappe.throw(
			_(
				"{0} must be a Cash or Bank account, or a liability with no account type, but {1} is not."
			).format(label, account)
		)


# The accounts an expense row can take; `validate_account(..., root_types=("Expense",))` checks the same on save.
EXPENSE_ROW_ACCOUNT_FILTERS = [["is_group", "=", 0], ["root_type", "=", "Expense"]]


def check_expense_picker_permission():
	"""Let only someone who can record or change an expense search its accounts (a Books User, not a Cashier)."""
	if not any(frappe.has_permission("Books Expense", ptype) for ptype in ("create", "write")):
		frappe.throw(_("You are not permitted to pick accounts for an expense."), frappe.PermissionError)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_expense_payment_accounts(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: list | dict | None = None,
	**kwargs,
) -> list[frappe._dict]:
	"""The Paid From picker of an expense: the names of the accounts its save accepts.

	Called by `search_widget` as its `query`. It is gated on the expense rights, not on Books Account
	rights, so a Books User fills the field without reading the chart of accounts, and it returns
	names only. `is_expense_payment_account` alone decides, as it does on save, so the client
	`filters` are ignored. Books Account is a translated doctype: `search_widget` sends an empty
	`txt` and a large page, then matches the translated names and pages the result itself, so
	`txt`, `start` and `page_len` are ignored too.
	"""
	check_expense_picker_permission()
	rows = frappe.get_all(
		"Books Account",
		filters=[["is_group", "=", 0]],
		or_filters=[["account_type", "in", PAYMENT_ACCOUNT_TYPES], ["root_type", "=", "Liability"]],
		fields=["name", "is_group", "account_type", "root_type"],
		order_by="lft",
	)
	# search_widget sorts translated results by `row.name`, so each row is a frappe._dict.
	return [frappe._dict(name=row.name) for row in rows if is_expense_payment_account(row)]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_expense_accounts(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: list | dict | None = None,
	**kwargs,
) -> list[frappe._dict]:
	"""The account picker of an expense row: the names of the leaf Expense accounts.

	Gated and shaped like `search_expense_payment_accounts`, for the same reasons.
	"""
	check_expense_picker_permission()
	names = frappe.get_all("Books Account", filters=EXPENSE_ROW_ACCOUNT_FILTERS, pluck="name", order_by="lft")
	return [frappe._dict(name=name) for name in names]


def validate_party_account(doc, fieldname, role):
	"""A customer's ledger account is receivable, a supplier's payable."""
	validate_account(doc, fieldname, PARTY_ACCOUNT_TYPES.get(role, ()))


def validate_changed_accounts(doc, rules):
	"""Check the accounts that changed, as `{fieldname: {"account_types": ..., "root_types": ...}}`."""
	for fieldname, types in rules.items():
		if doc.has_value_changed(fieldname):
			validate_account(doc, fieldname, **types)


def latest_ledger_account(account_type):
	"""Return the newest ledger account of the type, the one the Books app offers first."""
	return frappe.db.get_value(
		"Books Account", {"account_type": account_type, "is_group": 0}, "name", order_by="creation desc"
	)


def validate_party_role(doc, is_purchase):
	"""Sales go to customers and purchases come from suppliers; a party with both roles does either."""
	role = doc.party and frappe.db.get_value("Books Party", doc.party, "role")
	expected = "Supplier" if is_purchase else "Customer"
	if role and role not in (expected, "Both"):
		frappe.throw(
			_("{0} must be a {1}, but {2} is a {3}.").format(
				_(doc.meta.get_label("party")), _(expected), doc.party, _(role)
			)
		)


def validate_item_usage(doc, is_purchase):
	"""Sales take items kept for sales and purchases items kept for purchases, as Item Usage says."""
	items = sorted({row.item for row in doc.items if row.item})
	usage, other_usage = ("Purchases", "Sales") if is_purchase else ("Sales", "Purchases")
	other_only = items and frappe.get_all(
		"Books Item", filters={"name": ["in", items], "item_usage": other_usage}, pluck="name"
	)
	if other_only:
		frappe.throw(_("Item {0} is not for {1}.").format(", ".join(sorted(other_only)), _(usage)))
