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
  /** `no_trial_start` when a hosted site is locked because its trial start was never written (AC-8). */
  lock_reason: 'no_trial_start' | null;
  today: string;
  /** Null when there is no trial start, and so no day 1 to count from. */
  day_number: number | null;
  trial_ends_on: string | null;
  lock_starts_on: string | null;
  /** Day 30 of an unpaid trial, or `paid_until` plus 67 days once lapsed (spec 0007 AC-1). */
  removal_on: string | null;
  /** The site date the export email was sent, once it was (spec 0007 AC-8). */
  export_sent_on: string | null;
  /** The site date the site is removed after, once the export email was sent (spec 0007 AC-8). */
  removal_hold_until: string | null;
  paid_until: string | null;
  grace_ends_on: string | null;
  provider: string | null;
  billing_period: string | null;
  auto_renews: boolean;
  /** The day after the trial, while a PayPal subscription made during it waits for its first payment (spec 0008 AC-21). */
  subscription_starts_on: string | null;
  /** PayPal is retrying a first charge that failed on its start day (spec 0008 AC-21). */
  first_payment_overdue: boolean;
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
  // A PayPal subscription is already set to start after the trial, so there is nothing to prompt for.
  if (status.phase === 'prompt' && !status.subscription_starts_on) {
    const daysLeft = LOCK_DAY - (status.day_number ?? 0);
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
  if (status.lock_reason === 'no_trial_start') {
    // No day 1, so there are no trial dates to show (AC-8).
    return rows;
  }

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
  return [...rows, ...getRemovalRows(status)];
}

/** "Removal on" while a locked or lapsed site has a removal date (spec 0007 AC-2). */
function getRemovalRows(status: SubscriptionStatus): SubscriptionDetailRow[] {
  if (!status.locked || !status.removal_on) {
    return [];
  }

  return [
    {
      label: t`Removal on`,
      value: formatDate(status.removal_on),
      testid: 'removal-on',
    },
  ];
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

  return [...rows, ...getRemovalRows(status)];
}

/**
 * The locked banner's text, which every refused write shows too (AC-8, with the AC-15 note).
 * Pass `refusedWith` (the refusal's error type) only with a fresh status: an `InReadOnlyMode`
 * refusal on a site that isn't locked is Frappe's own maintenance mode (spec 0007 AC-5).
 */
export function getLockNotice(
  status: SubscriptionStatus | null,
  refusedWith?: string
): string {
  if (refusedWith === 'InReadOnlyMode' && status && !status.locked) {
    return t`This site is being updated and is read only for a few minutes. Try again shortly.`;
  }

  const notice = getLockText(status);
  if (!status?.payment_pending) {
    return notice;
  }

  return `${notice} ${t`Payment pending. The lock lifts as soon as your payment is confirmed.`}`;
}

function getLockText(status: SubscriptionStatus | null): string {
  if (status?.lock_reason === 'no_trial_start') {
    return t`Your books are read only. Contact support.`;
  }

  if (status?.locked && status.export_sent_on && status.removal_hold_until) {
    const removedAfter = formatDate(status.removal_hold_until);
    return t`Your books are read only. A copy of your data was emailed to the owner. This site will be removed after ${removedAfter}.`;
  }

  const removalOn = formatDate(status?.removal_on ?? null);
  if (status?.phase === 'locked' && removalOn) {
    return t`Your books are read only. Subscribe by ${removalOn} to keep this site. After that it is removed and a copy of your data is emailed to the owner.`;
  }

  if (status?.phase === 'lapsed' && removalOn) {
    return t`Your books are read only. Renew by ${removalOn} to keep this site. After that it is removed and a copy of your data is emailed to the owner.`;
  }

  if (status?.phase === 'lapsed') {
    return t`Your books are read only. Renew to make changes again.`;
  }

  return t`This site is read only. Subscribe to make changes again.`;
}

/**
 * The note for a PayPal subscription made in the trial with no payment yet: its start day up to that day,
 * then that the first payment hasn't arrived. Null otherwise (spec 0008 AC-21).
 */
export function getSubscriptionStartsNote(
  status: SubscriptionStatus | null
): string | null {
  if (status?.first_payment_overdue) {
    return t`Your first PayPal payment hasn't arrived. Check the payment method in your PayPal account.`;
  }

  if (!status?.subscription_starts_on) {
    return null;
  }

  const startsOn = formatDate(status.subscription_starts_on);
  return t`Your subscription starts on ${startsOn}.`;
}

/** Days left in the free trial, today included, as the banner counts its days (AC-3). */
export function getTrialDaysLeft(status: SubscriptionStatus): number {
  return Math.max(TRIAL_LAST_DAY + 1 - (status.day_number ?? 0), 0);
}

export function formatDate(isoDate: string | null): string {
  return isoDate ? fyo.format(isoDate, 'Date') : '';
}

/** Seeds the shared status from the session boot. */
export function setSubscriptionStatus(status: SubscriptionStatus | undefined) {
  subscriptionStatus.value = status ?? null;
}

export interface RefreshOptions {
  /** Have the server pull fresh state from billing first, as on the return from checkout (AC-12). */
  pull?: boolean;
  /** False asks for the status alone: no plans, and never a call to billing (spec 0007 AC-7). */
  withPlans?: boolean;
}

/** Fetches the status again and shares it, as after a refused write shows the site turned read only overnight. */
export async function refreshSubscriptionStatus({
  pull = false,
  withPlans = true,
}: RefreshOptions = {}): Promise<SubscriptionStatus> {
  const { call } = await import('src/web/api');
  const args: Record<string, boolean> = {};
  if (pull) {
    args.refresh = true;
  }

  if (!withPlans) {
    args.with_plans = false;
  }

  // A lock type error on the status call itself must not wait for another status call.
  const status = await call<SubscriptionStatus>(
    'frappe_books.subscription.get_subscription',
    args,
    { skipLockStatus: true }
  );
  // A status only answer carries no plans, so the Subscription page keeps the ones it has.
  subscriptionStatus.value = withPlans
    ? status
    : { ...getKeptPlans(subscriptionStatus.value), ...status };
  return subscriptionStatus.value;
}

let pendingLockStatus: Promise<SubscriptionStatus> | null = null;

/**
 * The fresh status a lock notice is worded from. Refusals that arrive together share one
 * status only call, which never waits on billing (spec 0007 AC-6).
 */
export function fetchLockStatus(): Promise<SubscriptionStatus> {
  pendingLockStatus ??= refreshSubscriptionStatus({ withPlans: false }).finally(
    () => (pendingLockStatus = null)
  );
  return pendingLockStatus;
}

function getKeptPlans(
  status: SubscriptionStatus | null
): Pick<SubscriptionStatus, 'plans' | 'plans_error'> {
  const kept: Pick<SubscriptionStatus, 'plans' | 'plans_error'> = {};
  if (status?.plans !== undefined) {
    kept.plans = status.plans;
  }

  if (status?.plans_error !== undefined) {
    kept.plans_error = status.plans_error;
  }

  return kept;
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
