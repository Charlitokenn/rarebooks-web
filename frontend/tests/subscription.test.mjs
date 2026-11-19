import assert from 'node:assert/strict';
import { after, before, beforeEach, test } from 'node:test';
import {
  appFyo,
  call,
  errors,
  insertDocument,
  subscription,
  subscriptionStatus,
  updateDocument,
} from './helpers/accounting.mjs';

const {
  getLockNotice,
  getSubscriptionBanner,
  getSubscriptionStartsNote,
  getTrialDaysLeft,
  isManaged,
} = subscription;

const READ_ONLY = 'This site is read only. Subscribe to make changes again.';
const TRIAL_LOCK =
  'Your books are read only. Subscribe by 30/11/2026 to keep this site. After that it is removed and a copy of your data is emailed to the owner.';

/** A status dict as `get_subscription` sends it, for day `day` of an unpaid trial. */
function trialStatus(day, overrides = {}) {
  const phase = day <= 21 ? 'trial' : day < 26 ? 'prompt' : 'locked';
  return {
    phase,
    locked: phase === 'locked',
    today: '2026-11-18',
    day_number: day,
    trial_ends_on: '2026-11-21',
    lock_starts_on: '2026-11-26',
    removal_on: '2026-11-30',
    export_sent_on: null,
    removal_hold_until: null,
    paid_until: null,
    grace_ends_on: null,
    provider: null,
    billing_period: null,
    auto_renews: false,
    subscription_starts_on: null,
    payment_pending: false,
    can_subscribe: true,
    offered_provider: 'PayPal',
    offered_periods: ['Monthly', 'Yearly'],
    ...overrides,
  };
}

before(() => {
  globalThis.window = { location: { hostname: 'books.localhost' } };
  globalThis.document = { cookie: 'user_id=Administrator; user_lang=en' };
  appFyo.singles.SystemSettings = { date_format: 'dd/MM/yyyy' };
});
after(() => {
  delete globalThis.window;
  delete globalThis.document;
});
beforeEach(() => {
  subscriptionStatus.value = null;
});

test('days 1 to 21 show no banner', () => {
  for (const day of [1, 21]) {
    assert.equal(getSubscriptionBanner(trialStatus(day), null), null);
  }
});

test('days 22 to 25 count down to read only, and can be dismissed', () => {
  const banner = getSubscriptionBanner(trialStatus(22), null);
  assert.deepEqual(banner, {
    message: '4 days left to subscribe before your books turn read only.',
    dismissible: true,
    canSubscribe: true,
  });
  assert.match(getSubscriptionBanner(trialStatus(25), null).message, /^1 days/);
});

test('a PayPal subscription waiting to start hides the prompt banner, not the lock', () => {
  // covers: spec 0008 AC-21
  const waiting = {
    provider: 'PayPal',
    auto_renews: true,
    subscription_starts_on: '2026-11-22',
  };
  for (const day of [22, 25]) {
    assert.equal(getSubscriptionBanner(trialStatus(day, waiting), null), null);
  }
  assert.equal(
    getSubscriptionBanner(trialStatus(26, waiting), null)?.message,
    TRIAL_LOCK
  );
});

test('the starts on note names the day after the trial, only while waiting', () => {
  // covers: spec 0008 AC-21
  assert.equal(
    getSubscriptionStartsNote(
      trialStatus(23, { subscription_starts_on: '2026-11-22' })
    ),
    'Your PayPal subscription starts on 22/11/2026.'
  );
  assert.equal(getSubscriptionStartsNote(trialStatus(23)), null);
  assert.equal(getSubscriptionStartsNote(null), null);
});

test('a dismissed prompt stays hidden until the next site day', () => {
  const status = trialStatus(23);
  assert.equal(getSubscriptionBanner(status, '2026-11-18'), null);
  assert.ok(getSubscriptionBanner(status, '2026-11-17'));
});

test('only System Managers and Books Managers get the Subscribe button', () => {
  const status = trialStatus(23, { can_subscribe: false });
  assert.equal(getSubscriptionBanner(status, null).canSubscribe, false);
});

test('a locked trial shows the day 30 date and ignores the dismissal', () => {
  const banner = getSubscriptionBanner(trialStatus(27), '2026-11-18');
  assert.deepEqual(banner, {
    message: TRIAL_LOCK,
    dismissible: false,
    canSubscribe: true,
  });
});

test('a site locked with no trial start says to contact support, with no dates', () => {
  const status = trialStatus(27, {
    lock_reason: 'no_trial_start',
    day_number: null,
    trial_ends_on: null,
    lock_starts_on: null,
    removal_on: null,
  });
  const banner = getSubscriptionBanner(status, '2026-11-18');
  assert.deepEqual(banner, {
    message: 'Your books are read only. Contact support.',
    dismissible: false,
    canSubscribe: true,
  });
  assert.equal(getLockNotice(status), banner.message);
  const details = subscription.getSubscriptionDetails(status);
  assert.equal(details.heading, 'Read only');
  assert.deepEqual(details.rows, []);
});

test('a lapsed site with no removal date asks to renew', () => {
  const status = trialStatus(90, {
    phase: 'lapsed',
    locked: true,
    removal_on: null,
    paid_until: '2026-10-01',
  });
  assert.equal(
    getSubscriptionBanner(status, null).message,
    'Your books are read only. Renew to make changes again.'
  );
});

test('a lapsed site names its removal date', () => {
  // covers: spec 0007 AC-2
  const status = trialStatus(90, {
    phase: 'lapsed',
    locked: true,
    removal_on: '2027-01-15',
    paid_until: '2026-11-09',
  });
  const banner = getSubscriptionBanner(status, '2026-11-18');
  assert.equal(
    banner.message,
    'Your books are read only. Renew by 15/01/2027 to keep this site. After that it is removed and a copy of your data is emailed to the owner.'
  );
  assert.equal(banner.dismissible, false);
});

test('once the export is emailed the banner names the removal date', () => {
  // covers: spec 0007 AC-8, AC-19 (the date goes through the date formatter)
  const held = {
    export_sent_on: '2026-11-30',
    removal_hold_until: '2026-12-03',
  };
  const expected =
    'Your books are read only. A copy of your data was emailed to the owner. This site will be removed after 03/12/2026.';
  for (const status of [
    trialStatus(30, held),
    paidStatus('lapsed', { ...held, removal_on: '2026-11-30' }),
  ]) {
    const banner = getSubscriptionBanner(status, null);
    assert.equal(banner.message, expected);
    assert.equal(banner.canSubscribe, true);
  }

  appFyo.singles.SystemSettings = { date_format: 'MM/dd/yyyy' };
  try {
    assert.match(getLockNotice(trialStatus(30, held)), /after 12\/03\/2026\.$/);
  } finally {
    appFyo.singles.SystemSettings = { date_format: 'dd/MM/yyyy' };
  }
});

test('the hold text needs both hold dates', () => {
  // covers: spec 0007 AC-8 ("while both are set")
  for (const held of [
    { export_sent_on: '2026-11-30' },
    { removal_hold_until: '2026-12-03' },
  ]) {
    assert.equal(getLockNotice(trialStatus(30, held)), TRIAL_LOCK);
  }
});

test('a pending payment adds its note to the lock notice', () => {
  const status = trialStatus(27, { payment_pending: true });
  assert.match(
    getLockNotice(status),
    /emailed to the owner\. Payment pending\. The lock lifts as soon as your payment is confirmed\.$/
  );
});

test('paid, unmanaged and exempt sites show no banner here', () => {
  for (const phase of ['active', 'unmanaged', 'exempt']) {
    const status = trialStatus(5, { phase, removal_on: null });
    assert.equal(getSubscriptionBanner(status, null), null);
  }
  assert.equal(isManaged(trialStatus(5, { phase: 'unmanaged' })), false);
  assert.equal(isManaged(trialStatus(5, { phase: 'exempt' })), false);
  assert.equal(isManaged(trialStatus(5)), true);
  assert.equal(isManaged(null), false);
});

/** A status dict for a paid site in `phase`, with `paid_until` and its grace end. */
function paidStatus(phase, overrides = {}) {
  return trialStatus(100, {
    phase,
    locked: phase === 'lapsed',
    removal_on: null,
    paid_until: '2026-11-30',
    grace_ends_on: '2026-12-07',
    provider: 'ClickPesa',
    billing_period: 'Yearly',
    ...overrides,
  });
}

const { getSubscriptionDetails } = subscription;

test('an active site shows no banner, renewing or not', () => {
  for (const auto_renews of [true, false]) {
    assert.equal(
      getSubscriptionBanner(paidStatus('active', { auto_renews }), null),
      null
    );
  }
});

test('renew soon names the last paid day and can be dismissed', () => {
  assert.deepEqual(getSubscriptionBanner(paidStatus('renew_soon'), null), {
    message: 'Your subscription ends on 30/11/2026. Renew to keep full access.',
    dismissible: true,
    canSubscribe: true,
  });
});

test('grace names the end and the renew by date, and can be dismissed', () => {
  const status = paidStatus('grace', {
    paid_until: '2026-11-15',
    grace_ends_on: '2026-11-22',
  });
  assert.deepEqual(getSubscriptionBanner(status, null), {
    message:
      'Your subscription ended on 15/11/2026. Renew by 22/11/2026 to keep full access.',
    dismissible: true,
    canSubscribe: true,
  });
  assert.equal(getSubscriptionBanner(status, status.today), null);
  assert.ok(getSubscriptionBanner(status, '2026-11-17'));
});

test('renew banners tell other users to ask', () => {
  for (const phase of ['renew_soon', 'grace']) {
    const status = paidStatus(phase, { can_subscribe: false });
    assert.equal(getSubscriptionBanner(status, null).canSubscribe, false);
  }
});

test('a lapsed banner ignores the dismissal', () => {
  const banner = getSubscriptionBanner(paidStatus('lapsed'), '2026-11-18');
  assert.equal(banner.dismissible, false);
  assert.equal(
    banner.message,
    'Your books are read only. Renew to make changes again.'
  );
});

const detailRows = (status) =>
  getSubscriptionDetails(status).rows.map(({ testid, label, value }) => [
    testid,
    label,
    value,
  ]);

test('an auto renewing site shows the renewal date', () => {
  const status = paidStatus('active', {
    provider: 'PayPal',
    auto_renews: true,
  });
  assert.equal(getSubscriptionDetails(status).heading, 'Subscribed');
  assert.deepEqual(detailRows(status), [
    ['renews-on', 'Renews on', '30/11/2026'],
  ]);
});

test('a site that does not renew on its own shows the paid until date', () => {
  for (const phase of ['active', 'renew_soon']) {
    assert.equal(
      getSubscriptionDetails(paidStatus(phase)).heading,
      'Subscribed'
    );
    assert.deepEqual(detailRows(paidStatus(phase)), [
      ['paid-until', 'Paid until', '30/11/2026'],
    ]);
  }
});

test('grace shows when it ended and the renew by date', () => {
  const status = paidStatus('grace');
  assert.equal(getSubscriptionDetails(status).heading, 'Subscription ended');
  assert.deepEqual(detailRows(status), [
    ['ended-on', 'Ended on', '30/11/2026'],
    ['renew-by', 'Renew by', '07/12/2026'],
  ]);
});

test('lapsed with a removal date shows a Removal on row', () => {
  // covers: spec 0007 AC-2
  const status = paidStatus('lapsed', { removal_on: '2027-02-05' });
  assert.deepEqual(detailRows(status), [
    ['ended-on', 'Ended on', '30/11/2026'],
    ['removal-on', 'Removal on', '05/02/2027'],
  ]);
});

test('an open trial shows no Removal on row', () => {
  // covers: spec 0007 AC-2 (only locked or lapsed)
  for (const day of [5, 23]) {
    assert.ok(
      !detailRows(trialStatus(day)).some(([testid]) => testid === 'removal-on')
    );
  }
});

test('lapsed reads as read only with no removal or renew by date', () => {
  const status = paidStatus('lapsed');
  assert.equal(getSubscriptionDetails(status).heading, 'Read only');
  assert.deepEqual(detailRows(status), [
    ['ended-on', 'Ended on', '30/11/2026'],
  ]);
});

test('the trial page rows are unchanged', () => {
  assert.equal(getSubscriptionDetails(trialStatus(5)).heading, 'Free trial');
  assert.deepEqual(
    detailRows(trialStatus(5)).map(([testid]) => testid),
    ['trial-days-left', 'trial-ends-on', 'lock-starts-on']
  );
  assert.equal(getSubscriptionDetails(trialStatus(27)).heading, 'Read only');
  assert.deepEqual(
    detailRows(trialStatus(27)).map(([testid]) => testid),
    ['trial-ends-on', 'lock-starts-on', 'removal-on']
  );
});

test('trial days left count today, as the banner does', () => {
  assert.equal(getTrialDaysLeft(trialStatus(1)), 21);
  assert.equal(getTrialDaysLeft(trialStatus(21)), 1);
  assert.equal(getTrialDaysLeft(trialStatus(23)), 0);
});

function respondV1(status, excType) {
  const message = JSON.stringify({ message: 'Server says no' });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        exc_type: excType,
        _server_messages: JSON.stringify([message]),
      }),
      { status }
    );
}

function respondV2(status, type) {
  globalThis.fetch = async () =>
    Response.json(
      { errors: [{ type, message: 'Server says no' }] },
      { status }
    );
}

const MAINTENANCE =
  'This site is being updated and is read only for a few minutes. Try again shortly.';

/**
 * Every write is refused with `type`, as v1 and v2 answer it, while `get_subscription`
 * answers `fresh` (or fails when it is null). Returns the status calls' bodies.
 */
function refuseWith(status, type, fresh) {
  const statusCalls = [];
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('get_subscription')) {
      statusCalls.push(JSON.parse(init?.body ?? '{}'));
      await new Promise((resolve) => setTimeout(resolve, 5));
      return fresh
        ? Response.json({ message: fresh })
        : Response.json({ exc_type: 'Exception' }, { status: 500 });
    }
    if (String(url).includes('/api/v2/')) {
      return Response.json(
        { errors: [{ type, message: 'Server says no' }] },
        { status }
      );
    }
    return Response.json({ exc_type: type }, { status });
  };
  return statusCalls;
}

test('a 403 SiteLockedError gives the lock notice, not ForbiddenError', async () => {
  subscriptionStatus.value = trialStatus(27);
  respondV2(403, 'SiteLockedError');
  const error = await insertDocument('ToDo', {}).catch((error) => error);
  assert.ok(error instanceof errors.SiteLockedError);
  assert.ok(!(error instanceof errors.ForbiddenError));
  assert.equal(error.message, TRIAL_LOCK);
  assert.equal(error.shouldStore, false);
});

test('a 503 InReadOnlyMode gives the lock notice too, in v1 and v2', async () => {
  // covers: spec 0007 AC-6 (the notice waits for the fresh status)
  const lapsed = trialStatus(90, { phase: 'lapsed', removal_on: null });
  subscriptionStatus.value = lapsed;
  refuseWith(503, 'InReadOnlyMode', lapsed);
  const fromCall = await call('method').catch((error) => error);
  const fromSave = await updateDocument('ToDo', 'x', {}).catch((e) => e);
  for (const error of [fromCall, fromSave]) {
    assert.ok(error instanceof errors.SiteLockedError);
    assert.equal(
      error.message,
      'Your books are read only. Renew to make changes again.'
    );
  }
});

test('a 503 of another type is a real outage, not the lock', async () => {
  subscriptionStatus.value = trialStatus(27);
  respondV1(503, 'ServiceUnavailable');
  const error = await call('method').catch((error) => error);
  assert.ok(!(error instanceof errors.SiteLockedError));
  assert.equal(error.message, 'Server says no');
});

test('the first refusal after the lock starts waits for the status and shows the dated text', async () => {
  // covers: spec 0007 AC-6, AC-7 (a status only call)
  subscriptionStatus.value = trialStatus(25);
  const statusCalls = refuseWith(403, 'SiteLockedError', trialStatus(26));
  const error = await insertDocument('ToDo', {}).catch((error) => error);
  assert.ok(error instanceof errors.SiteLockedError);
  assert.equal(error.message, TRIAL_LOCK);
  assert.deepEqual(statusCalls, [{ with_plans: false }]);
  assert.equal(subscriptionStatus.value.phase, 'locked');
});

test('a 503 InReadOnlyMode on a site that is not locked is maintenance, in v1 and v2', async () => {
  // covers: spec 0007 AC-5. The stored status said locked; the fresh one wins.
  for (const stored of [trialStatus(27), trialStatus(5)]) {
    subscriptionStatus.value = stored;
    refuseWith(503, 'InReadOnlyMode', trialStatus(5));
    const fromCall = await call('method').catch((error) => error);
    const fromSave = await updateDocument('ToDo', 'x', {}).catch((e) => e);
    for (const error of [fromCall, fromSave]) {
      assert.ok(error instanceof errors.SiteLockedError);
      assert.equal(error.message, MAINTENANCE);
      assert.doesNotMatch(error.message, /Subscribe/);
    }
  }
});

test('a failed status call falls back to the plain read only text', async () => {
  // covers: spec 0007 AC-6
  subscriptionStatus.value = trialStatus(25);
  for (const [status, type] of [
    [403, 'SiteLockedError'],
    [503, 'InReadOnlyMode'],
  ]) {
    refuseWith(status, type, null);
    const error = await insertDocument('ToDo', {}).catch((error) => error);
    assert.ok(error instanceof errors.SiteLockedError);
    assert.equal(error.message, READ_ONLY);
  }
});

test('a SiteLockedError on a site the browser knows is locked needs no status call', async () => {
  // covers: spec 0007 AC-6. SiteLockedError always shows the lock notice, never maintenance.
  subscriptionStatus.value = trialStatus(27);
  const statusCalls = refuseWith(403, 'SiteLockedError', trialStatus(5));
  const error = await insertDocument('ToDo', {}).catch((error) => error);
  assert.equal(error.message, TRIAL_LOCK);
  assert.deepEqual(statusCalls, []);
});

test('refusals that arrive together share one status call', async () => {
  // covers: spec 0007 AC-6
  subscriptionStatus.value = trialStatus(25);
  const statusCalls = refuseWith(503, 'InReadOnlyMode', trialStatus(26));
  const refused = await Promise.all([
    insertDocument('ToDo', {}).catch((error) => error),
    updateDocument('ToDo', 'x', {}).catch((error) => error),
    call('method').catch((error) => error),
  ]);
  assert.equal(statusCalls.length, 1);
  for (const error of refused) {
    assert.match(error.message, /Subscribe by 30\/11\/2026/);
  }
});

test(
  'a status call refused with a lock error itself starts no second status call',
  { timeout: 2000 },
  async () => {
    // covers: spec 0007 AC-6 (the loop guard). Every request answers InReadOnlyMode, get_subscription too.
    subscriptionStatus.value = trialStatus(27);
    const statusCalls = [];
    globalThis.fetch = async (url, init) => {
      if (String(url).includes('get_subscription')) {
        statusCalls.push(JSON.parse(init?.body ?? '{}'));
      }
      return Response.json({ exc_type: 'InReadOnlyMode' }, { status: 503 });
    };
    const error = await call('method').catch((error) => error);
    assert.ok(error instanceof errors.SiteLockedError);
    assert.equal(error.message, TRIAL_LOCK);
    assert.deepEqual(statusCalls, [{ with_plans: false }]);
  }
);

test('a status only fetch keeps the plans the browser already has', async () => {
  // covers: spec 0007 AC-7
  const plans = [
    {
      provider: 'PayPal',
      billing_period: 'Monthly',
      amount: 9,
      currency: 'USD',
      label: null,
    },
  ];
  subscriptionStatus.value = trialStatus(25, { plans, plans_error: null });
  globalThis.fetch = async () => Response.json({ message: trialStatus(26) });
  await subscription.refreshSubscriptionStatus({ withPlans: false });
  assert.equal(subscriptionStatus.value.phase, 'locked');
  assert.deepEqual(subscriptionStatus.value.plans, plans);
  assert.equal(subscriptionStatus.value.plans_error, null);
});

test("a logged out caller's 403 still goes to login, lock type or not", async () => {
  globalThis.document.cookie = 'user_lang=en';
  window.location.href = undefined;
  respondV2(403, 'SiteLockedError');
  let settled = false;
  insertDocument('ToDo', {}).finally(() => (settled = true));
  await new Promise((resolve) => setTimeout(resolve, 10));
  globalThis.document.cookie = 'user_id=Administrator; user_lang=en';
  assert.equal(settled, false);
  assert.equal(window.location.href, '/login?redirect-to=%2Fbooks');
});

test('the return refresh asks the server to pull from billing and updates the shared status', async () => {
  subscriptionStatus.value = trialStatus(27);
  const bodies = [];
  globalThis.fetch = async (url, init) => {
    bodies.push([String(url), JSON.parse(init?.body ?? '{}')]);
    return Response.json({
      message: trialStatus(27, {
        phase: 'active',
        locked: false,
        paid_until: '2027-11-18',
        removal_on: null,
      }),
    });
  };
  await subscription.refreshSubscriptionStatus({ pull: true });
  const [url, body] = bodies[0];
  assert.ok(url.includes('frappe_books.subscription.get_subscription'));
  assert.equal(body.refresh, true);
  assert.equal(subscriptionStatus.value.phase, 'active');
  assert.equal(getSubscriptionBanner(subscriptionStatus.value, null), null);
});

test('a plain refresh does not ask for a pull', async () => {
  const bodies = [];
  globalThis.fetch = async (_url, init) => {
    bodies.push(JSON.parse(init?.body ?? '{}'));
    return Response.json({ message: trialStatus(5) });
  };
  await subscription.refreshSubscriptionStatus();
  assert.equal(bodies[0].refresh, undefined);
});

test('checkout sends the chosen period and returns the link', async () => {
  const bodies = [];
  globalThis.fetch = async (url, init) => {
    bodies.push([String(url), JSON.parse(init?.body ?? '{}')]);
    return Response.json({
      message: { checkout_url: 'https://pay.example.com/abc' },
    });
  };
  const url = await subscription.startCheckout('Yearly');
  assert.equal(url, 'https://pay.example.com/abc');
  assert.ok(bodies[0][0].includes('frappe_books.subscription.start_checkout'));
  assert.equal(bodies[0][1].billing_period, 'Yearly');
});

test('a refused checkout carries the server message', async () => {
  respondV1(417, 'ValidationError');
  const error = await subscription
    .startCheckout('Monthly')
    .catch((error) => error);
  assert.equal(error.message, 'Server says no');
});

test('plans read as a price per period', () => {
  const monthly = {
    provider: 'PayPal',
    billing_period: 'Monthly',
    amount: 9,
    currency: 'USD',
    label: null,
  };
  assert.match(subscription.formatPlanPrice(monthly), /9\.00 a month$/);
  assert.match(
    subscription.formatPlanPrice({ ...monthly, billing_period: 'Yearly' }),
    / a year$/
  );
  assert.equal(subscription.getPlanLabel(monthly), 'Monthly');
  assert.equal(
    subscription.getPlanLabel({ ...monthly, label: 'Starter' }),
    'Starter'
  );
});

test('only ?checkout=returned counts as the return from checkout', () => {
  assert.equal(subscription.isCheckoutReturn({ checkout: 'returned' }), true);
  assert.equal(subscription.isCheckoutReturn({ checkout: 'cancelled' }), false);
  assert.equal(subscription.isCheckoutReturn({}), false);
});
