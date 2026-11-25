"""Kilima Hardware, the fictional shop the marketing homepage screenshots are taken from (spec 0019 AC-15).

It runs only on a fresh local site in developer mode, after the setup wizard:

	bench --site shots-tzs.localhost execute frappe_books.demo.shop.seed --kwargs "{'currency': 'TZS'}"

Every record goes through the normal controllers, so stock, the ledger, the dashboard cards and the reports
show real numbers. Dates are relative to the day it runs. Every name is made up: no real customer, person or
business.
"""

import random
from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, getdate, now_datetime
from frappe.utils.password import update_password

from frappe_books.accounting.money import company_currency
from frappe_books.accounting.payment import map_invoice_payment
from frappe_books.subscription import clock

LOCATION = "Stores"
# The three role users sign in with this password; it is fine only because the seed refuses any site that
# is not a fresh local developer mode site.
USER_PASSWORD = "demo-shop-only"
USERS = (
	("manager@kilima-hardware.example", "Amani", "Books Manager"),
	("clerk@kilima-hardware.example", "Rehema", "Books User"),
	("cashier@kilima-hardware.example", "Daudi", "Books Cashier"),
)
POS_PROFILE = "Kilima Counter"
MOBILE_MONEY = "Mobile Money"

# name, barcode, TZS price, USD price, opening stock. The first three are the ones the POS screenshot adds.
ITEMS = (
	("Cement 50kg bag", "201000000017", 18500, 9.50, 400),
	("Iron sheet 3m gauge 30", "201000000024", 32000, 16.00, 250),
	("Wire nails 3 inch 1kg", "201000000031", 4500, 2.25, 300),
	("Emulsion paint white 4L", "201000000048", 38000, 19.00, 120),
	("Gloss paint red 1L", "201000000055", 14500, 7.25, 90),
	("Paint brush 3 inch", "201000000062", 3500, 1.75, 150),
	("PVC pipe half inch 6m", "201000000079", 9000, 4.50, 200),
	("Elbow joint half inch", "201000000086", 800, 0.40, 600),
	("Padlock 50mm", "201000000093", 12000, 6.00, 80),
	("Claw hammer", "201000000109", 15000, 7.50, 60),
	("Wheelbarrow", "201000000116", 145000, 72.00, 20),
	("Electric cable 2.5mm 100m", "201000000123", 95000, 47.50, 30),
	("Socket outlet double", "201000000130", 6500, 3.25, 140),
	("LED bulb 9W", "201000000147", 3000, 1.50, 400),
	("Door hinge 4 inch pair", "201000000154", 2500, 1.25, 250),
	("Tile adhesive 20kg", "201000000161", 22000, 11.00, 100),
	("Steel bar 12mm 12m", "201000000178", 28000, 14.00, 180),
	("Measuring tape 5m", "201000000185", 7000, 3.50, 70),
	("Wood screws box", "201000000192", 5500, 2.75, 160),
	("Water tank 1000L", "201000000208", 285000, 142.00, 12),
)
# Buyers lean to these, so the best sellers chart has a clear shape.
POPULAR = (
	"Cement 50kg bag",
	"Iron sheet 3m gauge 30",
	"Emulsion paint white 4L",
	"Steel bar 12mm 12m",
	"Wire nails 3 inch 1kg",
)
WALK_IN = "Walk in customer"
CUSTOMERS = (
	"Baraka Builders",
	"Upendo Construction",
	"Mama Zawadi Shop",
	"Juma Electricals",
	"Tumaini Contractors",
	WALK_IN,
)
SUPPLIERS = ("Pwani Cement Supply", "Mji Steel Traders", "Rangi Paints Wholesale")
# Each purchase: supplier, days ago, and the items it restocks (a third of the opening stock each).
PURCHASES = (
	("Pwani Cement Supply", 24, ("Cement 50kg bag", "Tile adhesive 20kg")),
	("Mji Steel Traders", 17, ("Iron sheet 3m gauge 30", "Steel bar 12mm 12m", "Wire nails 3 inch 1kg")),
	("Rangi Paints Wholesale", 10, ("Emulsion paint white 4L", "Gloss paint red 1L", "Paint brush 3 inch")),
	("Pwani Cement Supply", 3, ("Cement 50kg bag",)),
)
# Each expense: chart account, description, TZS amount, USD amount, days ago, paid in cash or from the bank.
EXPENSES = (
	("Office Rent", "Shop rent", 800000, 450.00, 28, "bank"),
	("Utility Expenses", "Electricity tokens", 95000, 60.00, 26, "cash"),
	("Travel Expenses", "Transport for deliveries", 60000, 35.00, 21, "cash"),
	("Salary", "Wages, first half of the month", 700000, 400.00, 16, "bank"),
	("Utility Expenses", "Electricity tokens", 90000, 55.00, 12, "cash"),
	("Travel Expenses", "Transport for deliveries", 75000, 40.00, 8, "cash"),
	("Salary", "Wages, second half of the month", 700000, 400.00, 2, "bank"),
	("Travel Expenses", "Transport for deliveries", 45000, 30.00, 1, "cash"),
)
# Opening money in TZS and USD, from the owner's capital, dated before the 30 days the shots show.
OPENING_MONEY = {"cash": (1500000, 900.00), "bank": (15000000, 9000.00), MOBILE_MONEY: (850000, 0)}
INVOICE_COUNT = 54
POS_SALE_COUNT = 6
CURRENCY_INDEX = {"TZS": 0, "USD": 1}


def seed(currency: str):
	"""Fill this site with Kilima Hardware, priced in `currency` (TZS or USD)."""
	check_can_seed(currency)
	shop = DemoShop(currency)
	shop.run()
	frappe.db.commit()
	return _("Kilima Hardware is seeded in {0}.").format(currency)


def check_can_seed(currency):
	"""Refuse anything but a fresh, set up, local developer mode site, so it can never touch a customer site."""
	if currency not in CURRENCY_INDEX:
		frappe.throw(_("The demo shop is priced in TZS or USD, not {0}.").format(currency))
	if not frappe.conf.get("developer_mode"):
		frappe.throw(_("The demo shop seeds only a site in developer mode."))
	if clock.is_managed():
		frappe.throw(_("The demo shop never seeds a hosted site, and this site has books_control_url set."))
	if frappe.db.exists("Books Sales Invoice", {"docstatus": 1}):
		frappe.throw(_("The demo shop seeds only a fresh site, and this one has submitted sales invoices."))
	if not frappe.db.get_single_value("Books Accounting Settings", "setup_complete"):
		frappe.throw(_("Finish the RareBooks setup wizard before you seed the demo shop."))
	if company_currency() != currency:
		frappe.throw(
			_("This company keeps its books in {0}, so seed it in {0}, not {1}.").format(
				company_currency(), currency
			)
		)


class DemoShop:
	def __init__(self, currency):
		self.currency = currency
		self.local = currency == "TZS"
		self.index = CURRENCY_INDEX[currency]
		# A fixed seed, so every run makes the same shop and the screenshots stay comparable.
		self.random = random.Random(19)
		self.today = getdate()
		self.now = now_datetime()

	def run(self):
		self.read_accounts()
		self.turn_on_features()
		self.make_money_accounts()
		self.make_parties()
		self.make_items()
		self.make_users()
		self.make_pos_profile()
		self.open_money()
		self.open_stock()
		self.make_purchases()
		self.make_expenses()
		self.make_sales()
		self.make_pos_sales()

	def read_accounts(self):
		inventory = frappe.get_single("Books Inventory Settings")
		self.cash = frappe.db.get_single_value("Books Pos Settings", "cash_account")
		self.bank = frappe.db.get_value("Books Payment Method", "Bank", "account")
		self.receivable = frappe.db.get_single_value("Books Pos Settings", "default_account")
		self.payable = frappe.db.get_value("Books Account", {"account_type": "Payable", "is_group": 0})
		self.income = frappe.db.get_value("Books Account", {"name": "Sales", "is_group": 0})
		self.received = inventory.stock_received_but_not_billed
		self.equity = frappe.db.get_value("Books Account", {"name": "Opening Balance Equity", "is_group": 0})
		missing = [
			label
			for label, account in (
				(_("Cash"), self.cash),
				(_("Bank"), self.bank),
				(_("Debtors"), self.receivable),
				(_("Creditors"), self.payable),
				(_("Sales"), self.income),
				(_("Stock Received But Not Billed"), self.received),
				(_("Opening Balance Equity"), self.equity),
			)
			if not account
		]
		if missing:
			frappe.throw(
				_("Set up the company with the standard chart of accounts. Missing: {0}").format(
					", ".join(missing)
				)
			)

	def turn_on_features(self):
		frappe.db.set_single_value("Books Accounting Settings", "enable_inventory", 1)
		frappe.db.set_single_value(
			"Books Inventory Settings", {"enable_point_of_sale": 1, "enable_barcodes": 1}
		)
		# Sales ship from and purchases arrive at the one store, on submit.
		frappe.db.set_single_value(
			"Books Defaults", {"shipment_location": LOCATION, "purchase_receipt_location": LOCATION}
		)

	def make_money_accounts(self):
		"""Tanzanian shops take mobile money, so the TZS shop has a mobile money wallet and method."""
		self.methods = {"cash": ("Cash", self.cash), "bank": ("Bank", self.bank)}
		if not self.local:
			return
		parent = frappe.db.get_value("Books Account", self.bank, "parent_books_account")
		if not frappe.db.exists("Books Account", MOBILE_MONEY):
			frappe.get_doc(
				{
					"doctype": "Books Account",
					"account_name": MOBILE_MONEY,
					"parent_books_account": parent,
					"root_type": "Asset",
					"account_type": "Bank",
				}
			).insert()
		if not frappe.db.exists("Books Payment Method", MOBILE_MONEY):
			frappe.get_doc(
				{
					"doctype": "Books Payment Method",
					"name": MOBILE_MONEY,
					"type": "Bank",
					"account": MOBILE_MONEY,
				}
			).insert()
		self.methods[MOBILE_MONEY] = (MOBILE_MONEY, MOBILE_MONEY)

	def make_parties(self):
		for name in CUSTOMERS:
			self.insert_party(name, "Customer", self.receivable)
		for name in SUPPLIERS:
			self.insert_party(name, "Supplier", self.payable)
		frappe.db.set_single_value("Books Defaults", "pos_customer", WALK_IN)

	def insert_party(self, name, role, account):
		frappe.get_doc(
			{
				"doctype": "Books Party",
				"name": name,
				"role": role,
				"default_account": account,
				"currency": self.currency,
			}
		).insert()

	def make_items(self):
		self.prices = {}
		for name, barcode, *prices, _stock in ITEMS:
			rate = prices[self.index]
			self.prices[name] = rate
			frappe.get_doc(
				{
					"doctype": "Books Item",
					"name": name,
					"item_usage": "Both",
					"item_type": "Product",
					"unit": "Unit",
					"rate": rate,
					"barcode": barcode,
					"track_item": 1,
					"income_account": self.income,
					"expense_account": self.received,
				}
			).insert()

	def cost(self, item):
		"""The shop buys at about 70 percent of its price, to the currency's smallest unit."""
		rate = self.prices[item] * 0.7
		return round(rate, -2) if self.local else round(rate, 2)

	def make_users(self):
		for email, first_name, role in USERS:
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": first_name,
						"send_welcome_email": 0,
						"roles": [{"role": role}],
					}
				).insert(ignore_permissions=True)
			update_password(email, USER_PASSWORD)

	def make_pos_profile(self):
		frappe.get_doc(
			{
				"doctype": "Books Pos Profile",
				"name": POS_PROFILE,
				"pos_customer": WALK_IN,
				"inventory": LOCATION,
				"pos_ui": "Classic",
				"item_visibility": "Inventory Items",
			}
		).insert()
		frappe.db.set_single_value("Books Pos Settings", "pos_profile", POS_PROFILE)

	def open_money(self):
		"""The owner's opening cash, bank and mobile money, a day before the 30 days the shots show."""
		rows = [
			{"account": self.methods[key][1], "debit": amounts[self.index]}
			for key, amounts in OPENING_MONEY.items()
			if key in self.methods and amounts[self.index]
		]
		self.opening_entry(rows, sum(row["debit"] for row in rows), _("Opening balances"))

	def opening_entry(self, rows, total, remark):
		"""An opening entry 31 days ago that `rows` balance against Opening Balance Equity."""
		entry = frappe.get_doc(
			{
				"doctype": "Books Journal Entry",
				"entry_type": "Opening Entry",
				"posting_date": add_days(self.today, -31),
				"user_remark": remark,
				"accounts": [*rows, {"account": self.equity, "credit": total}],
			}
		).insert()
		entry.submit()

	def open_stock(self):
		"""One stock entry 31 days ago, before the 30 days of profit and loss the shots show."""
		movement = frappe.get_doc(
			{
				"doctype": "Books Stock Movement",
				"movement_type": "MaterialReceipt",
				"date": self.at(31, 8),
				"items": [
					{"item": name, "to_location": LOCATION, "quantity": stock, "rate": self.cost(name)}
					for name, _barcode, *_prices, stock in ITEMS
				],
			}
		).insert()
		movement.submit()
		# A stock receipt credits Stock Adjustment; opening stock is the owner's capital, not income.
		adjustment = frappe.db.get_single_value("Books Inventory Settings", "stock_adjustment")
		self.opening_entry(
			[{"account": adjustment, "debit": movement.amount}], movement.amount, _("Opening stock")
		)

	def make_purchases(self):
		stock = {name: quantity for name, _barcode, *_prices, quantity in ITEMS}
		for supplier, days_ago, items in PURCHASES:
			invoice = frappe.get_doc(
				{
					"doctype": "Books Purchase Invoice",
					"party": supplier,
					"account": self.payable,
					"date": self.at(days_ago, 10),
					"make_auto_payment": 0,
					"make_auto_stock_transfer": 1,
					"items": [
						{
							"item": item,
							"account": self.received,
							"rate": self.cost(item),
							"quantity": max(stock[item] // 3, 1),
						}
						for item in items
					],
				}
			).insert()
			invoice.submit()
			self.pay(invoice, "bank", days_ago)

	def make_expenses(self):
		for account, description, *amounts, days_ago, paid_from in EXPENSES:
			expense = frappe.get_doc(
				{
					"doctype": "Books Expense",
					"date": add_days(self.today, -days_ago),
					"paid_from": self.methods[paid_from][1],
					"accounts": [
						{"account": account, "description": description, "amount": amounts[self.index]}
					],
				}
			).insert()
			expense.submit()

	def make_sales(self):
		"""About two sales a day over the last 30 days, most paid at once, a few left for the customer to owe."""
		buyers = [name for name in CUSTOMERS if name != WALK_IN]
		for number in range(INVOICE_COUNT):
			days_ago = INVOICE_COUNT // 2 - 1 - number // 2
			customer = WALK_IN if self.random.random() < 0.45 else self.random.choice(buyers)
			invoice = frappe.get_doc(
				{
					"doctype": "Books Sales Invoice",
					"party": customer,
					"account": self.receivable,
					"date": self.at(days_ago, 9 + (number % 2) * 5 + self.random.randint(0, 2)),
					"make_auto_payment": 0,
					"make_auto_stock_transfer": 1,
					"items": self.basket(),
				}
			).insert()
			invoice.submit()
			if customer == WALK_IN or self.random.random() < 0.7:
				self.pay(invoice, self.sale_method(), days_ago)

	def basket(self):
		lines = self.random.randint(1, 3)
		names = set()
		while len(names) < lines:
			pool = POPULAR if self.random.random() < 0.65 else [name for name, *_rest in ITEMS]
			names.add(self.random.choice(pool))
		return [
			{
				"item": name,
				"account": self.income,
				"rate": self.prices[name],
				"quantity": self.random.randint(1, 6),
			}
			for name in sorted(names)
		]

	def sale_method(self):
		roll = self.random.random()
		if self.local and roll < 0.4:
			return MOBILE_MONEY
		return "cash" if roll < 0.75 else "bank"

	def pay(self, invoice, method_key, days_ago):
		method, account = self.methods[method_key]
		payment = map_invoice_payment(invoice.doctype, invoice.name)
		payment.update(
			{
				"date": self.at(days_ago, 17),
				"payment_method": method,
				"payment_account": account,
				"reference_id": None if method == "Cash" else f"DEMO-{invoice.name}",
			}
		)
		payment.insert()
		payment.submit()

	def make_pos_sales(self):
		"""Today's counter sales, in an open shift that stays open for the point of sale screenshot."""
		frappe.get_doc(
			{
				"doctype": "Books Pos Opening Shift",
				"opening_amounts": [{"payment_method": "Cash", "amount": 0}],
			}
		).insert().submit()
		for _number in range(POS_SALE_COUNT):
			items = self.basket()
			total = sum(row["rate"] * row["quantity"] for row in items)
			frappe.get_doc(
				{
					"doctype": "Books Sales Invoice",
					"party": WALK_IN,
					"account": self.receivable,
					"date": self.now,
					"is_pos": 1,
					"items": items,
					"payments": [{"payment_method": "Cash", "amount": total}],
				}
			).insert().submit()

	def at(self, days_ago, hour):
		"""A time `days_ago` days back at `hour`, never later than now."""
		moment = datetime.combine(add_days(self.today, -days_ago), time(min(hour, 23)))
		return min(moment, add_to_date(self.now, minutes=-5))
