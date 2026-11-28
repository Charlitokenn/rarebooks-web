"""The events that push (spec 0026): a payment received (AC-5), low stock (AC-6), the subscription (AC-7)."""

import functools

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import fmt_money, formatdate

from frappe_books.accounting.money import as_decimal, company_currency
from frappe_books.inventory.stock import format_quantity
from frappe_books.notifications import fcm
from frappe_books.notifications.sending import SETTINGS, event_enabled, notify, send_now
from frappe_books.subscription.clock import LOCKED_PHASES, current_clock

ITEM = "Books Item"
LEDGER = "Books Stock Ledger Entry"
# The phases a change into pushes; `locked` and `lapsed` share one message and one tag.
SUBSCRIPTION_PHASES = ("prompt", "renew_soon", "grace", *LOCKED_PHASES)
# Leaving these counts as a first run: nothing was pushed for them (AC-7).
UNCOUNTED_PHASES = ("", "unmanaged", "exempt")
READ_ONLY = "read-only"
# A deadlock rolls back the whole transaction, and a lock timeout means the user's own write is stuck too,
# so neither may be swallowed: the user's action must fail and be retried, not report a save that isn't there.
TRANSACTION_ERRORS = (frappe.QueryDeadlockError, frappe.QueryTimeoutError)


def never_blocks_the_action(event):
	"""Run an event hook inside the user's transaction without ever failing it (spec 0026 AC-10).

	Any error undoes only the hook's own writes (a savepoint) and is logged once; the payment, stock
	transaction, item save or POS sale goes on. Nothing here touches the Firebase key, so the log holds none.
	"""

	@functools.wraps(event)
	def guarded(*args, **kwargs):
		savepoint = "books_push_event"
		frappe.db.savepoint(savepoint)
		try:
			return event(*args, **kwargs)
		except TRANSACTION_ERRORS:
			raise
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(title=f"Books push: {event.__name__} failed")

	return guarded


# Payments (AC-5)


@never_blocks_the_action
def payment_submitted(payment):
	"""Books Payment `on_submit`: a Receive payment outside a POS sale pushes once."""
	if payment.payment_type != "Receive" or payment.amended_from or payment.flags.books_counter_payment:
		return
	_push_payment(payment.party, payment.amount, f"/books/edit/Payment/{payment.name}", payment.name)


@never_blocks_the_action
def pos_sale_paid(invoice, amounts: list):
	"""After `pay_at_counter`: one push for the sale, with the total of its tendered rows."""
	if not amounts:
		return
	total = sum((as_decimal(amount) for amount in amounts), as_decimal(0))
	_push_payment(invoice.party, total, f"/books/edit/SalesInvoice/{invoice.name}", invoice.name)


def _push_payment(party: str, amount, link: str, name: str):
	if not fcm.is_configured() or not event_enabled("payment_received"):
		return
	money = fmt_money(amount, currency=company_currency())

	def build(lang: str) -> dict:
		return {
			"title": _("Payment received", lang=lang),
			"body": _("{0} paid {1}", lang=lang).format(party, money),
			"link": link,
			"tag": f"payment:{name}",
		}

	# The one who took the money already knows.
	notify(build, exclude_user=frappe.session.user)


# Low stock (AC-6)


@never_blocks_the_action
def check_low_stock(item_names):
	"""After a stock transaction posts or cancels, or an item's level changes: push on the drop only.

	Each checked item row is locked first, so two transactions at once can't both see the flag clear.
	An item with no reorder level and no flag to clear is skipped by a plain read, taking no lock.
	"""
	if not fcm.is_configured():
		return
	names = sorted({name for name in item_names if name})
	if not names:
		return
	watched = frappe.get_all(
		ITEM,
		filters={"name": ["in", names], "track_item": 1},
		or_filters={"reorder_level": [">", 0], "low_stock_notified": 1},
		pluck="name",
		order_by="name asc",
	)
	for item in watched:
		_check_item(item)


@never_blocks_the_action
def item_saved(item):
	"""Books Item `on_update`: a changed level or tracking clears the flag and checks at once."""
	if not (item.has_value_changed("reorder_level") or item.has_value_changed("track_item")):
		return
	if not fcm.is_configured():
		return
	frappe.db.set_value(ITEM, item.name, "low_stock_notified", 0, update_modified=False)
	_check_item(item.name)


def _check_item(item: str):
	row = frappe.db.get_value(
		ITEM,
		item,
		["low_stock_notified", "reorder_level", "track_item", "unit"],
		as_dict=True,
		for_update=True,
	)
	if not row:
		return
	level = as_decimal(row.reorder_level)
	if not row.track_item or level <= 0:
		if row.low_stock_notified:
			_set_notified(item, 0)
		return

	total = _stock_on_hand(item)
	if total <= level:
		if not row.low_stock_notified:
			_set_notified(item, 1)
			_push_low_stock(item, total, row.unit, level)
	elif row.low_stock_notified:
		_set_notified(item, 0)


def _stock_on_hand(item: str):
	"""Every location and date. Ledger quantities are signed, so this can be negative.

	A locking read, so a transaction that waited on the item row sees what the other one committed.
	"""
	sle = frappe.qb.DocType(LEDGER)
	rows = frappe.qb.from_(sle).select(Sum(sle.quantity)).where(sle.item == item).for_update().run()
	return as_decimal(rows[0][0] if rows else 0)


def _set_notified(item: str, value: int):
	frappe.db.set_value(ITEM, item, "low_stock_notified", value, update_modified=False)


def _push_low_stock(item: str, total, unit: str | None, level):
	if not event_enabled("low_stock"):
		return
	quantity, reorder_level = format_quantity(total), format_quantity(level)

	def build(lang: str) -> dict:
		return {
			"title": _("Low stock: {0}", lang=lang).format(item),
			"body": _("{0} {1} left (reorder level {2})", lang=lang).format(
				quantity, unit or "", reorder_level
			),
			"link": f"/books/edit/Item/{item}",
			"tag": f"low-stock:{item}",
		}

	notify(build)


# Subscription (AC-7, AC-13)


def notify_subscription_phase():
	"""Hourly job: push once on entering a phase the owner must act on, then store the phase.

	Sent here, not from a queued job, since a locked site leaves only scheduled jobs writable.
	"""
	clock = current_clock()
	phase = clock.phase
	last = frappe.db.get_singles_dict(SETTINGS).get("last_subscription_phase") or ""
	if phase == last:
		return

	if _pushes(last, phase) and event_enabled("subscription") and not _already_subscribing(clock, phase):
		status = clock.status()
		if not send_now(lambda lang: _subscription_message(phase, status, lang)):
			# Google refused every send: nothing went out, so the next run tries again.
			return
	frappe.db.set_single_value(SETTINGS, "last_subscription_phase", phase)


def _already_subscribing(clock, phase: str) -> bool:
	"""A PayPal subscription set to start after the trial: no `prompt` push, as the banner (spec 0026 AC-7).

	The clock knows this only on day 22, the charge day. The phase is still stored, so the skip is final and a
	late first charge on day 23 sends nothing either.
	"""
	return phase == "prompt" and bool(clock.subscription_starts_on)


def _pushes(last: str, phase: str) -> bool:
	if last in UNCOUNTED_PHASES or phase not in SUBSCRIPTION_PHASES:
		return False
	return _tag(last) != _tag(phase)


def _tag(phase: str) -> str:
	return READ_ONLY if phase in LOCKED_PHASES else phase


def _subscription_message(phase: str, status: dict, lang: str) -> dict:
	if phase == "prompt":
		# The trial ended the day before `prompt` starts; what the owner must beat is the lock (spec 0026 AC-7).
		title = _("Your books turn read only soon", lang=lang)
		body = _("Subscribe before {0} to keep making changes.", lang=lang).format(
			_date(status.get("lock_starts_on"))
		)
	elif phase == "renew_soon":
		title = _("Renewal due", lang=lang)
		body = _("Your subscription ends on {0}. Renew to keep making changes.", lang=lang).format(
			_date(status.get("paid_until"))
		)
	elif phase == "grace":
		title = _("Payment overdue", lang=lang)
		body = _("Your subscription ended. Pay by {0} to keep making changes.", lang=lang).format(
			_date(status.get("grace_ends_on"))
		)
	else:
		title = _("RareBooks is now read only", lang=lang)
		body = _("Subscribe to make changes again.", lang=lang)
	return {
		"title": title,
		"body": body,
		"link": "/books/subscription",
		"tag": f"subscription:{_tag(phase)}",
	}


def _date(value: str | None) -> str:
	# The clock's dates are already in the site's time zone; this writes them in the site's date format.
	return formatdate(value) if value else ""
