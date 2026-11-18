import { t } from 'fyo/utils/translation';
import { fyo } from 'src/initFyo';
import { subscriptionStatus } from 'src/utils/refs';

/** The phases of spec 0005's state table, computed on the server. */
export type SubscriptionPhase =
  | 'unmanaged'
  | 'exempt'
  | 'active'
  | 'renew_soon'
  | 'grace'
  | 'lapsed'
  | 'trial'
  | 'prompt'
  | 'locked';

/** `frappe_books.subscription.get_subscription`'s status dict. Dates are ISO dates in the site's time zone. */
export interface SubscriptionStatus {
  phase: SubscriptionPhase;
  locked: boolean;
  today: string;
  day_number: number;
  trial_ends_on: string | null;
  lock_starts_on: string | null;
  removal_on: string | null;
  paid_until: string | null;
  grace_ends_on: string | null;
  provider: string | null;
  billing_period: string | null;
  auto_renews: boolean;
  payment_pending: boolean;
  can_subscribe: boolean;
  offered_provider: string | null;
  offered_periods: string[];
  /** Only for System Managers and Books Managers on a hosted site, from `get_subscription`. */
  plans?: SubscriptionPlan[];
  /** "Couldn't reach billing. Try again." when the control site couldn't be reached (AC-16). */
  plans_error?: string | null;
}

/** A plan the control site offers this site, with its price. */
export interface SubscriptionPlan {
  provider: string;
  billing_period: 'Monthly' | 'Yearly';
  amount: number;
  currency: string;
  label: string | null;
}

export interface SubscriptionBanner {
  message: string;
  /** The read only banners can't be dismissed. */
  dismissible: boolean;
  /** System Managers and Books Managers get a Subscribe button; others are told to ask. */
  canSubscribe: boolean;
}

export const SUBSCRIPTION_ROUTE = '/subscription';
export const BANNER_DISMISSED_KEY = 'books_subscription_banner_dismissed';
const LOCK_DAY = 26;
const TRIAL_LAST_DAY = 21;
const LOCK_ERROR_TYPES = new Set(['SiteLockedError', 'InReadOnlyMode']);

/** A refused write: the lock's own error, or the read only transaction's (never judged by HTTP status). */
export function isLockErrorType(excType?: string): boolean {
  return LOCK_ERROR_TYPES.has(excType ?? '');
}

/** Hosted sites show the banner, the sidebar item and the plan details. */
export function isManaged(status: SubscriptionStatus | null): boolean {
  return !!status && status.phase !== 'unmanaged' && status.phase !== 'exempt';
}

/** The banner for this phase, or null when none shows (AC-4, AC-8). */
export function getSubscriptionBanner(
  status: SubscriptionStatus | null,
  dismissedOn: string | null
): SubscriptionBanner | null {
  if (!status) {
    return null;
  }

  const canSubscribe = status.can_subscribe;
  if (status.locked) {
    return { message: getLockNotice(status), dismissible: false, canSubscribe };
  }

  // The open banners share the dismissal key, so each hides until the next site day (AC-4).
  const message = getOpenBannerMessage(status);
  if (message && dismissedOn !== status.today) {
    return { message, dismissible: true, canSubscribe };
  }

  return null;
}

/** The text of a banner that still leaves full access: the trial prompt, renew soon or grace. */
function getOpenBannerMessage(status: SubscriptionStatus): string | null {
  if (status.phase === 'prompt') {
    const daysLeft = LOCK_DAY - status.day_number;
    return t`${daysLeft} days left to subscribe before your books turn read only.`;
  }

  const paidUntil = formatDate(status.paid_until);
  if (status.phase === 'renew_soon') {
    return t`Your subscription ends on ${paidUntil}. Renew to keep full access.`;
  }

  if (status.phase === 'grace') {
    const graceEndsOn = formatDate(status.grace_ends_on);
    return t`Your subscription ended on ${paidUntil}. Renew by ${graceEndsOn} to keep full access.`;
  }

  return null;
}

export interface SubscriptionDetailRow {
  label: string;
  value: string;
  testid: string;
}

export interface SubscriptionDetails {
  heading: string;
  rows: SubscriptionDetailRow[];
}

const UNPAID_TRIAL_PHASES: SubscriptionPhase[] = ['trial', 'prompt', 'locked'];

/** The Subscription page's heading and date rows for a hosted site's phase (AC-3, AC-13, AC-14). */
export function getSubscriptionDetails(
  status: SubscriptionStatus
): SubscriptionDetails {
  if (UNPAID_TRIAL_PHASES.includes(status.phase)) {
    return {
      heading: status.locked ? t`Read only` : t`Free trial`,
      rows: getTrialRows(status),
    };
  }

  return { heading: getPaidHeading(status), rows: getPaidRows(status) };
}

function getTrialRows(status: SubscriptionStatus): SubscriptionDetailRow[] {
  const rows: SubscriptionDetailRow[] = [];
  if (status.phase !== 'locked') {
    rows.push({
      label: t`Days left in the trial`,
      value: String(getTrialDaysLeft(status)),
      testid: 'trial-days-left',
    });
  }

  rows.push(
    {
      label: t`Trial ends on`,
      value: formatDate(status.trial_ends_on),
      testid: 'trial-ends-on',
    },
    {
      label: t`Read only from`,
      value: formatDate(status.lock_starts_on),
      testid: 'lock-starts-on',
    }
  );
  return rows;
}

function getPaidHeading(status: SubscriptionStatus): string {
  if (status.locked) {
    return t`Read only`;
  }

  return status.phase === 'grace' ? t`Subscription ended` : t`Subscribed`;
}

function getPaidRows(status: SubscriptionStatus): SubscriptionDetailRow[] {
  const paidUntil = formatDate(status.paid_until);
  if (status.phase === 'active' && status.auto_renews) {
    // The renewal date is paid_until, as the renew banner's end date is.
    return [{ label: t`Renews on`, value: paidUntil, testid: 'renews-on' }];
  }

  if (status.phase === 'active' || status.phase === 'renew_soon') {
    return [{ label: t`Paid until`, value: paidUntil, testid: 'paid-until' }];
  }

  const rows = [{ label: t`Ended on`, value: paidUntil, testid: 'ended-on' }];
  if (status.phase === 'grace') {
    rows.push({
      label: t`Renew by`,
      value: formatDate(status.grace_ends_on),
      testid: 'renew-by',
    });
  }

  return rows;
}

/** The locked banner's text, which every refused write shows too (AC-8, with the AC-15 note). */
export function getLockNotice(status: SubscriptionStatus | null): string {
  const notice =
    status?.phase === 'locked' && status.removal_on
      ? t`Your books are read only. Subscribe by ${formatDate(status.removal_on)} to keep your data.`
      : status?.phase === 'lapsed'
        ? t`Your books are read only. Renew to make changes again.`
        : t`This site is read only. Subscribe to make changes again.`;
  if (!status?.payment_pending) {
    return notice;
  }

  return `${notice} ${t`Payment pending. The lock lifts as soon as your payment is confirmed.`}`;
}

/** Days left in the free trial, today included, as the banner counts its days (AC-3). */
export function getTrialDaysLeft(status: SubscriptionStatus): number {
  return Math.max(TRIAL_LAST_DAY + 1 - status.day_number, 0);
}

export function formatDate(isoDate: string | null): string {
  return isoDate ? fyo.format(isoDate, 'Date') : '';
}

/** Seeds the shared status from the session boot. */
export function setSubscriptionStatus(status: SubscriptionStatus | undefined) {
  subscriptionStatus.value = status ?? null;
}

/**
 * Fetches the status again, as after a refused write shows the site turned read only overnight.
 * `refresh` has the server pull fresh state from billing first, as on the return from checkout (AC-12).
 */
export async function refreshSubscriptionStatus(
  refresh = false
): Promise<SubscriptionStatus> {
  const { call } = await import('src/web/api');
  const status = await call<SubscriptionStatus>(
    'frappe_books.subscription.get_subscription',
    refresh ? { refresh: true } : {}
  );
  subscriptionStatus.value = status;
  return status;
}

/** Asks the server for a checkout link for the chosen period; the caller sends the browser there. */
export async function startCheckout(
  billingPeriod: SubscriptionPlan['billing_period']
): Promise<string> {
  const { call } = await import('src/web/api');
  const { checkout_url } = await call<{ checkout_url: string }>(
    'frappe_books.subscription.start_checkout',
    { billing_period: billingPeriod }
  );
  return checkout_url;
}

/** The plan's price per period, for example "USD 9.00 a month". */
export function formatPlanPrice(plan: SubscriptionPlan): string {
  const amount = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: plan.currency,
  }).format(plan.amount);
  return plan.billing_period === 'Monthly'
    ? t`${amount} a month`
    : t`${amount} a year`;
}

/** The plan's name: the control site's label, else the period. */
export function getPlanLabel(plan: SubscriptionPlan): string {
  return (
    plan.label || (plan.billing_period === 'Monthly' ? t`Monthly` : t`Yearly`)
  );
}

/** The return URL the control site sends the browser back to after checkout. */
export function isCheckoutReturn(query: Record<string, unknown>): boolean {
  return query.checkout === 'returned';
}

/** The site day the prompt banner was dismissed on, if the browser kept it. */
export function getDismissedOn(): string | null {
  try {
    return localStorage.getItem(BANNER_DISMISSED_KEY);
  } catch {
    return null;
  }
}

/** Hides the prompt banner until the next site day (the status dict's `today`, not the browser's). */
export function dismissBanner(today: string): void {
  try {
    localStorage.setItem(BANNER_DISMISSED_KEY, today);
  } catch {
    // Without storage the banner shows again on the next load.
  }
}
