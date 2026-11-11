from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from frappe_books.reports.dashboard import (
	get_best_sellers,
	get_cash_balances,
	get_cashflow,
	get_invoice_summary,
	get_period_dates,
	get_profit_and_loss,
	get_top_expenses,
)
from frappe_books.reports.financial_statements import get_account_balances
from frappe_books.tests.accounting import insert_sales_invoice, make_account, unique_name

TODAY = "2031-12-15"
PERIODS = ("This Year", "This Quarter", "This Month", "YTD")


class IntegrationTestDashboard(IntegrationTestCase):
	def test_ledger_totals_are_grouped_by_account_and_month(self):
		cash = make_account("Dashboard Cash", account_type="Cash")
		rent = make_account("Dashboard Rent", root_type="Expense")
		sales = make_account("Dashboard Sales", root_type="Income")
		for date, account, debit, credit in (
			("2031-01-10", rent, 30, 0),
			("2031-01-20", rent, 20, 0),
			("2031-01-20", cash, 0, 50),
			("2031-02-05", cash, 80, 0),
			("2031-02-05", sales, 0, 80),
		):
			_post(account, debit, credit, date)

		with self.freeze_time(TODAY):
			expenses = get_top_expenses("This Year")
			cashflow = get_cashflow("This Year")
			profit = get_profit_and_loss("This Year")

		self.assertIn({"account": rent.name, "total": Decimal("50.00")}, expenses)
		self.assertEqual(
			cashflow["months"][:3],
			[
				{"yearmonth": "2031-01", "inflow": Decimal("0.00"), "outflow": Decimal("50.00")},
				{"yearmonth": "2031-02", "inflow": Decimal("80.00"), "outflow": Decimal("0.00")},
				{"yearmonth": "2031-03", "inflow": Decimal("0.00"), "outflow": Decimal("0.00")},
			],
		)
		self.assertTrue(cashflow["has_data"])
		self.assertEqual(
			[(month["yearmonth"], month["balance"]) for month in profit["months"][:3]],
			[("2031-01", Decimal("-50.00")), ("2031-02", Decimal("80.00")), ("2031-03", Decimal("0.00"))],
		)
		self.assertTrue(profit["has_data"])

	def test_returns_reduce_the_paid_and_unpaid_totals(self):
		for total, outstanding, return_against in ((100, 40, None), (-30, -30, "Dashboard Original")):
			_invoice("2031-03-01", total, outstanding, return_against=return_against)

		with self.freeze_time(TODAY):
			summary = get_invoice_summary("Books Sales Invoice", "This Year")

		self.assertEqual(
			(summary["total"], summary["paid"], summary["unpaid"]),
			(Decimal("70.00"), Decimal("60.00"), Decimal("10.00")),
		)
		self.assertEqual((summary["paid_count"], summary["unpaid_count"]), (0, 2))


class IntegrationTestCashflow(IntegrationTestCase):
	def test_cashflow_has_data_only_with_cash_entries_in_the_period(self):
		_post(make_account("Period Cash", account_type="Cash"), 80, 0, "2031-01-10")

		with self.freeze_time(TODAY):
			self.assertTrue(get_cashflow("This Year")["has_data"])
			self.assertFalse(get_cashflow("This Month")["has_data"])


class IntegrationTestTopExpenses(IntegrationTestCase):
	def test_expenses_past_the_top_five_are_summed_as_others(self):
		for amount in (60, 50, 40, 30, 20, 10, 5):
			_post(make_account("Top Expense", root_type="Expense"), amount, 0, "2031-12-01")

		with self.freeze_time(TODAY):
			expenses = get_top_expenses("This Month")

		self.assertEqual([row["total"] for row in expenses], [60, 50, 40, 30, 20, 15])
		self.assertEqual(expenses[-1]["account"], "Others")


class IntegrationTestDashboardPeriods(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value(
			"Books Accounting Settings", {"fiscal_year_start": "2026-04-01", "fiscal_year_end": "2027-03-31"}
		)

	def test_periods_end_today_and_start_on_the_first_of_a_month(self):
		with self.freeze_time("2031-09-30 18:00:00"):
			periods = {period: get_period_dates(period) for period in PERIODS}
			months = get_profit_and_loss("This Month")["months"]

		self.assertEqual(
			periods,
			{
				"This Year": _dates("2030-10-01", "2031-09-30"),
				"This Quarter": _dates("2031-07-01", "2031-09-30"),
				"This Month": _dates("2031-09-01", "2031-09-30"),
				"YTD": _dates("2031-04-01", "2031-09-30"),
			},
		)
		self.assertEqual([month["yearmonth"] for month in months], ["2031-09"])

	def test_year_to_date_starts_on_the_fiscal_year_holding_today(self):
		with self.freeze_time("2032-02-15"):
			self.assertEqual(get_period_dates("YTD"), _dates("2031-04-01", "2032-02-15"))

	def test_invoices_dated_after_today_are_left_out(self):
		for date in ("2031-09-30 09:00:00", "2031-10-01 09:00:00"):
			_invoice(date, 100, 0)

		with self.freeze_time("2031-09-30 18:00:00"):
			summary = get_invoice_summary("Books Sales Invoice", "This Month")

		self.assertEqual((summary["paid_count"], summary["total"]), (1, Decimal("100.00")))


class IntegrationTestInvoiceDrillDown(IntegrationTestCase):
	def test_invoice_list_filters_select_the_invoices_the_summary_counts(self):
		_invoice("2031-09-10 09:00:00", 100, 0)
		_invoice("2031-09-11 09:00:00", 100, 100)
		_invoice("2031-09-12 09:00:00", 100, 0, docstatus=2)
		_invoice("2031-09-13 09:00:00", 100, 0, docstatus=0)
		_invoice("2031-08-31 09:00:00", 100, 0)

		with self.freeze_time("2031-09-30 18:00:00"):
			summary = get_invoice_summary("Books Sales Invoice", "This Month")

		self.assertEqual((summary["paid_count"], summary["unpaid_count"]), (1, 1))
		for operator, count in (("=", summary["paid_count"]), ("!=", summary["unpaid_count"])):
			# The filters the Paid and Unpaid buttons open the invoice list with.
			filters = [
				["docstatus", "in", [1, 2]],
				["docstatus", "not in", [2]],
				["outstanding_amount", operator, 0],
				["date", ">=", summary["from_date"]],
				["date", "<", summary["before_date"]],
			]
			self.assertEqual(len(frappe.get_list("Books Sales Invoice", filters=filters)), count)


class IntegrationTestAccountBalances(IntegrationTestCase):
	def test_account_balances_are_kept_on_the_root_type_side(self):
		cash = make_account("Balance Cash", account_type="Cash")
		sales = make_account("Balance Sales", root_type="Income")
		_post(cash, 80, 0)
		_post(sales, 0, 80)
		_post(cash, 0, 50)

		result = get_account_balances()

		self.assertEqual(
			(result["balances"][cash.name], result["balances"][sales.name]), (Decimal(30), Decimal(80))
		)
		self.assertEqual(result["credit_root_types"], ["Equity", "Income", "Liability"])


class IntegrationTestCashBalances(IntegrationTestCase):
	def test_leaf_cash_and_bank_accounts_are_listed_in_chart_order_with_their_total(self):
		cash = make_account("Balances Cash", account_type="Cash")
		bank = make_account("Balances Bank", account_type="Bank")
		group = make_account("Balances Bank Group", account_type="Bank", is_group=1)
		rent = make_account("Balances Rent", root_type="Expense")
		_post(cash, 80, 0)
		_post(cash, 0, 30)
		_post(bank, 120, 0)
		_post(rent, 40, 0)

		with self.freeze_time(TODAY):
			result = get_cash_balances()

		balances = {row["account"]: row["balance"] for row in result["accounts"]}
		self.assertEqual((balances[cash.name], balances[bank.name]), (Decimal("50.00"), Decimal("120.00")))
		self.assertNotIn(group.name, balances)
		self.assertNotIn(rent.name, balances)
		names = [row["account"] for row in result["accounts"]]
		lft = {name: frappe.db.get_value("Books Account", name, "lft") for name in names}
		self.assertEqual(names, sorted(names, key=lft.get))
		self.assertEqual(result["total"], sum(balances.values()))

	def test_entries_after_today_and_reverted_entries_are_left_out(self):
		cash = make_account("Cut Off Cash", account_type="Cash")
		_post(cash, 100, 0, TODAY)
		_post(cash, 70, 0, "2031-12-16")
		_post(cash, 25, 0, reverted=1)
		_post(cash, 0, 25, reverted=1)

		with self.freeze_time(TODAY):
			result = get_cash_balances()

		self.assertIn({"account": cash.name, "balance": Decimal("100.00")}, result["accounts"])
		self.assertEqual(result["as_of"], getdate(TODAY))

	def test_an_empty_account_shows_zero_and_an_overdrawn_one_lowers_the_total(self):
		empty = make_account("Empty Bank", account_type="Bank")
		overdrawn = make_account("Overdrawn Bank", account_type="Bank")
		_post(overdrawn, 0, 60)

		with self.freeze_time(TODAY):
			result = get_cash_balances()

		balances = {row["account"]: row["balance"] for row in result["accounts"]}
		self.assertEqual(
			(balances[empty.name], balances[overdrawn.name]), (Decimal("0.00"), Decimal("-60.00"))
		)
		others = sum(balance for name, balance in balances.items() if name != overdrawn.name)
		self.assertEqual(result["total"], others - 60)


class IntegrationTestBestSellers(IntegrationTestCase):
	def test_the_five_largest_items_are_returned_and_every_item_counts_in_the_total(self):
		items = _items("Best Seller", 7)
		for item, amount in zip(items, (70, 60, 50, 40, 30, 20, 10), strict=True):
			insert_sales_invoice("2031-12-05 10:00:00", [{"item": item, "amount": amount}])

		with self.freeze_time(TODAY):
			result = get_best_sellers("This Month")

		self.assertEqual(
			result["items"],
			[_sale(item, amount) for item, amount in zip(items[:5], (70, 60, 50, 40, 30), strict=True)],
		)
		self.assertEqual(result["total"], 280)

	def test_amounts_are_after_the_row_discount_and_in_base_currency(self):
		before_tax, after_tax, doubled, zero_rate, empty_rate = _items("Discount Seller", 5)
		insert_sales_invoice(
			"2031-11-05", [{"item": before_tax, "amount": 100, "discounted": 90, "taxed": 99}]
		)
		insert_sales_invoice(
			"2031-11-05",
			[{"item": after_tax, "amount": 100, "discounted": 99, "taxed": 110}],
			discount_after_tax=1,
		)
		insert_sales_invoice("2031-11-05", [{"item": doubled, "amount": 25}], exchange_rate=2)
		insert_sales_invoice("2031-11-05", [{"item": zero_rate, "amount": 30}], exchange_rate=0)
		insert_sales_invoice("2031-11-05", [{"item": empty_rate, "amount": 20}], exchange_rate=None)

		with self.freeze_time("2031-11-20"):
			result = get_best_sellers("This Month")

		self.assertEqual(
			result["items"],
			[
				_sale(before_tax, 90),
				_sale(after_tax, 89),
				_sale(doubled, 50),
				_sale(zero_rate, 30),
				_sale(empty_rate, 20),
			],
		)

	def test_a_sale_late_on_the_last_day_counts_and_sales_outside_the_period_do_not(self):
		late, next_day, before = _items("Edge Seller", 3)
		insert_sales_invoice("2031-10-20 23:30:00", [{"item": late, "amount": 10}])
		insert_sales_invoice("2031-10-21 00:00:00", [{"item": next_day, "amount": 10}])
		insert_sales_invoice("2031-09-30 23:59:00", [{"item": before, "amount": 10}])

		with self.freeze_time("2031-10-20 09:00:00"):
			result = get_best_sellers("This Month")

		self.assertEqual(result, {"items": [_sale(late, 10)], "total": 10})

	def test_returns_lower_an_item_and_drafts_and_cancelled_invoices_change_nothing(self):
		returned, refunded, unsold = _items("Return Seller", 3)
		insert_sales_invoice(
			"2031-08-03", [{"item": returned, "amount": 100}, {"item": refunded, "amount": 50}]
		)
		insert_sales_invoice(
			"2031-08-10", [{"item": returned, "amount": -30}, {"item": refunded, "amount": -60}]
		)
		insert_sales_invoice("2031-08-11", [{"item": returned, "amount": 40}], docstatus=0)
		insert_sales_invoice("2031-08-12", [{"item": unsold, "amount": 40}], docstatus=2)

		with self.freeze_time("2031-08-20"):
			result = get_best_sellers("This Month")

		self.assertEqual(result, {"items": [_sale(returned, 70)], "total": 70})

	def test_ties_are_broken_by_item_and_only_the_first_five_are_returned(self):
		prefix = unique_name("Tie Seller")
		items = [f"{prefix} {letter}" for letter in "ABCDEF"]
		for item, amount in zip(reversed(items), (20, 20, 30, 40, 50, 60), strict=True):
			insert_sales_invoice("2031-07-04", [{"item": item, "amount": amount}])

		with self.freeze_time("2031-07-20"):
			result = get_best_sellers("This Month")

		self.assertEqual([row["item"] for row in result["items"]], items[:5])
		self.assertEqual(result["total"], 220)

	# covers: AC-1, AC-2
	def test_an_item_sums_across_invoices_rates_and_discount_modes_over_the_year(self):
		(item,) = _items("Mixed Seller", 1)
		insert_sales_invoice("2031-01-10", [{"item": item, "amount": 100, "discounted": 90}])
		insert_sales_invoice("2031-06-10", [{"item": item, "amount": 10}], exchange_rate=3)
		insert_sales_invoice(
			"2031-11-10",
			[{"item": item, "amount": 100, "discounted": 99, "taxed": 110}],
			discount_after_tax=1,
		)
		# An invoice with no item rows joins as a row with no item and is skipped.
		insert_sales_invoice("2031-11-11", [])

		with self.freeze_time(TODAY):
			result = get_best_sellers("This Year")

		self.assertIn(_sale(item, 90 + 30 + 89), result["items"])
		self.assertTrue(all(row["item"] for row in result["items"]))

	def test_few_items_all_come_back_and_no_sales_give_an_empty_result(self):
		items = _items("Few Seller", 3)
		for item, amount in zip(items, (30, 20, 10), strict=True):
			insert_sales_invoice("2031-06-04", [{"item": item, "amount": amount}])
		insert_sales_invoice("2031-05-04", [{"item": items[0], "amount": -10}])

		with self.freeze_time("2031-06-20"):
			few = get_best_sellers("This Month")
		with self.freeze_time("2031-05-20"):
			below_zero = get_best_sellers("This Month")
		with self.freeze_time("2031-04-20"):
			none = get_best_sellers("This Month")

		self.assertEqual(
			few,
			{
				"items": [_sale(item, amount) for item, amount in zip(items, (30, 20, 10), strict=True)],
				"total": 60,
			},
		)
		self.assertEqual(below_zero, {"items": [], "total": 0})
		self.assertEqual(none, {"items": [], "total": 0})


def _post(account, debit, credit, date="2031-01-10", **values):
	frappe.get_doc(
		{
			"doctype": "Books Ledger Entry",
			"posting_date": date,
			"account": account.name,
			"debit": debit,
			"credit": credit,
			**values,
		}
	).insert()


def _invoice(date, total, outstanding, **values):
	frappe.get_doc(
		{
			"doctype": "Books Sales Invoice",
			"name": frappe.generate_hash(),
			"date": date,
			"docstatus": 1,
			"base_grand_total": total,
			"outstanding_amount": outstanding,
			**values,
		}
	).db_insert()


def _items(label, count):
	return [unique_name(label) for _index in range(count)]


def _sale(item, amount):
	return {"item": item, "amount": Decimal(amount)}


def _dates(*dates):
	return tuple(getdate(date) for date in dates)
