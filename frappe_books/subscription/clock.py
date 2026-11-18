"""The trial clock: works out a site's phase from the stored facts, today and the site's time zone."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_datetime, getdate

from frappe_books.settings import company_country

TRIAL_LAST_DAY = 21
LOCK_DAY = 26
REMOVAL_DAY = 30
GRACE_DAYS = 7
RENEW_NOTICE_DAYS = 14
PAYMENT_PENDING_HOURS = 24
LOCKED_PHASES = ("locked", "lapsed")
SUBSCRIBER_ROLES = ("System Manager", "Books Manager")
DOCTYPE = "Books Subscription"


def current_clock() -> SubscriptionClock:
	"""The clock for this site now. Cached reads only, so the lock check adds no query once warm."""
	return SubscriptionClock(frappe.get_cached_doc(DOCTYPE), is_managed(), utc_now())


def is_locked() -> bool:
	# An unmanaged site reads nothing, so it behaves exactly as before this feature.
	return is_managed() and current_clock().locked


def is_managed() -> bool:
	"""A site is hosted (and so on the clock) only when provisioning wrote the control site URL."""
	return bool(frappe.conf.get("books_control_url"))


def utc_now() -> datetime:
	"""Naive UTC, the way the single stores its Datetime fields."""
	return datetime.now(UTC).replace(tzinfo=None)


class SubscriptionClock:
	def __init__(self, facts, managed: bool, now: datetime):
		self.facts = facts
		self.managed = managed
		self.now = now
		self.zone = site_zone()
		self.today = _local_date(now, self.zone)
		started = facts.trial_started_on
		self.day_one = _local_date(get_datetime(started), self.zone) if started else self.today
		self.paid_until = getdate(facts.paid_until) if facts.paid_until else None

	@property
	def day_number(self) -> int:
		return (self.today - self.day_one).days + 1

	@property
	def phase(self) -> str:
		"""The first matching row of the spec's state table wins."""
		if not self.managed:
			return "unmanaged"
		if self.facts.exempt:
			return "exempt"
		if self.paid_until:
			return self._paid_phase()
		if not self.facts.trial_started_on:
			# Install and the patch always set it, so a hosted site without one is broken: fail closed,
			# rather than read as a new day 1 every day. `bench execute frappe_books.subscription.start_trial` fixes it.
			return "locked"
		if self.day_number <= TRIAL_LAST_DAY:
			return "trial"
		if self.day_number < LOCK_DAY:
			return "prompt"
		return "locked"

	@property
	def locked(self) -> bool:
		return self.phase in LOCKED_PHASES

	def status(self) -> dict:
		"""The status dict boot and get_subscription send. Dates are ISO dates in the site's time zone."""
		phase = self.phase
		offered_provider, offered_periods = offered_plan()
		unpaid_trial = phase in ("trial", "prompt", "locked")
		return {
			"phase": phase,
			"locked": phase in LOCKED_PHASES,
			"today": _iso(self.today),
			"day_number": self.day_number,
			"trial_ends_on": _iso(self._trial_day(TRIAL_LAST_DAY)),
			"lock_starts_on": _iso(self._trial_day(LOCK_DAY)),
			"removal_on": _iso(self._trial_day(REMOVAL_DAY)) if unpaid_trial else None,
			"paid_until": _iso(self.paid_until),
			"grace_ends_on": _iso(self.paid_until + timedelta(days=GRACE_DAYS)) if self.paid_until else None,
			"provider": self.facts.provider or None,
			"billing_period": self.facts.billing_period or None,
			"auto_renews": bool(self.facts.auto_renews),
			"payment_pending": self._payment_pending(),
			"can_subscribe": can_subscribe(),
			"offered_provider": offered_provider,
			"offered_periods": offered_periods,
		}

	def _paid_phase(self) -> str:
		days_left = (self.paid_until - self.today).days
		if days_left >= 0:
			if self.facts.auto_renews or days_left > RENEW_NOTICE_DAYS:
				return "active"
			return "renew_soon"
		if -days_left <= GRACE_DAYS:
			return "grace"
		return "lapsed"

	def _trial_day(self, number: int) -> date:
		return self.day_one + timedelta(days=number - 1)

	def _payment_pending(self) -> bool:
		started = self.facts.checkout_started_on
		return bool(started) and self.now - get_datetime(started) <= timedelta(hours=PAYMENT_PENDING_HOURS)


def site_zone() -> ZoneInfo:
	"""System Settings time zone, or UTC while it is empty (never Frappe's Asia/Kolkata fallback)."""
	return ZoneInfo(frappe.get_system_settings("time_zone") or "UTC")


def can_subscribe() -> bool:
	return bool(set(SUBSCRIBER_ROLES) & set(frappe.get_roles()))


def offered_plan() -> tuple[str | None, list[str]]:
	"""Tanzanian companies pay yearly through ClickPesa, everyone else through PayPal."""
	country = company_country()
	if not country:
		return None, []
	if country == "Tanzania":
		return "ClickPesa", ["Yearly"]
	return "PayPal", ["Monthly", "Yearly"]


def _local_date(naive_utc: datetime, zone: ZoneInfo) -> date:
	return naive_utc.replace(tzinfo=UTC).astimezone(zone).date()


def _iso(value: date | None) -> str | None:
	return value.isoformat() if value else None
