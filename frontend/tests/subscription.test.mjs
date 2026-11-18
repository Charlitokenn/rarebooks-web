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

const { getLockNotice, getSubscriptionBanner, getTrialDaysLeft, isManaged } =
  subscription;

const READ_ONLY = 'This site is read only. Subscribe to make changes again.';

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
    paid_until: null,
    grace_ends_on: null,
    provider: null,
    billing_period: null,
    auto_renews: false,
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
    message:
      'Your books are read only. Subscribe by 30/11/2026 to keep your data.',
    dismissible: false,
    canSubscribe: true,
  });
});

test('a lapsed site asks to renew, with no removal date', () => {
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

test('a pending payment adds its note to the lock notice', () => {
  const status = trialStatus(27, { payment_pending: true });
  assert.match(
    getLockNotice(status),
    /keep your data\. Payment pending\. The lock lifts as soon as your payment is confirmed\.$/
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

test('a 403 SiteLockedError gives the lock notice, not ForbiddenError', async () => {
  subscriptionStatus.value = trialStatus(27);
  respondV2(403, 'SiteLockedError');
  const error = await insertDocument('ToDo', {}).catch((error) => error);
  assert.ok(error instanceof errors.SiteLockedError);
  assert.ok(!(error instanceof errors.ForbiddenError));
  assert.equal(
    error.message,
    'Your books are read only. Subscribe by 30/11/2026 to keep your data.'
  );
  assert.equal(error.shouldStore, false);
});

test('a 503 InReadOnlyMode gives the lock notice too, in v1 and v2', async () => {
  subscriptionStatus.value = trialStatus(90, {
    phase: 'lapsed',
    removal_on: null,
  });
  respondV1(503, 'InReadOnlyMode');
  const fromCall = await call('method').catch((error) => error);
  respondV2(503, 'InReadOnlyMode');
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

test('a lock refusal while the browser thinks the site is open fetches the status', async () => {
  subscriptionStatus.value = trialStatus(25);
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(String(url));
    if (String(url).includes('get_subscription')) {
      return Response.json({ message: trialStatus(26) });
    }
    return Response.json(
      { errors: [{ type: 'SiteLockedError', message: READ_ONLY }] },
      { status: 403 }
    );
  };
  const error = await insertDocument('ToDo', {}).catch((error) => error);
  assert.equal(error.message, READ_ONLY);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.ok(requests.some((url) => url.includes('get_subscription')));
  assert.equal(subscriptionStatus.value.phase, 'locked');
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
