import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import {
  fyo,
  getAppMenuItems,
  pushNotifications,
  stubFrappe,
  subscriptionStatus,
  toast,
} from './helpers/frappe.mjs';

const {
  TOKEN_KEY_PREFIX,
  getDeviceLabel,
  getPushState,
  hasPush,
  refreshPushRegistration,
  setPush,
  stopPushForSignOut,
  stubFirebase,
  turnOffPush,
  turnOnPush,
} = pushNotifications;

// Spec 0026: a Firebase token per device, turned on and off from the app menu.
const PUSH = {
  web_config: {
    apiKey: 'key',
    projectId: 'books',
    messagingSenderId: '1',
    appId: 'app',
  },
  vapid_key: 'vapid',
};
const USER = 'asha@books.test';
const TOKEN_KEY = TOKEN_KEY_PREFIX + USER;
const REGISTER = '/api/method/frappe_books.notifications.register_device';
const UNREGISTER = '/api/method/frappe_books.notifications.unregister_device';
const CHROME_ANDROID =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36';
const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1';

globalThis.document ??= { cookie: '' };
const BROWSER_WINDOW = {
  open: () => {},
  location: { hostname: 'books.localhost' },
};
const flush = () => new Promise((resolve) => setImmediate(resolve));

let storage;
let toasts;
let firebaseCalls;
let unsubscribed;
let permission;
let nextToken;

function stubBrowser({
  userAgent = CHROME_ANDROID,
  supportsPush = true,
  standalone = false,
} = {}) {
  storage = new Map();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
  });
  const registration = {
    pushManager: {
      getSubscription: async () => ({
        unsubscribe: async () => (unsubscribed = true),
      }),
    },
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    writable: true,
    value: {
      userAgent,
      maxTouchPoints: 0,
      standalone,
      serviceWorker: {
        register: async () => ({ ...registration, active: {} }),
        ready: Promise.resolve(registration),
        getRegistration: async () => registration,
      },
    },
  });
  globalThis.window = supportsPush
    ? { ...BROWSER_WINDOW, PushManager: {}, Notification: {} }
    : { ...BROWSER_WINDOW };
  globalThis.Notification = {
    get permission() {
      return permission;
    },
    requestPermission: async () => {
      firebaseCalls.push(['requestPermission']);
      permission = permission === 'default' ? 'granted' : permission;
      return permission;
    },
  };
}

function stubFirebaseModules() {
  stubFirebase(async () => ({
    app: { getApps: () => [], initializeApp: (config) => ({ config }) },
    messaging: {
      getMessaging: (app) => ({ app }),
      getToken: async (_messaging, options) => {
        firebaseCalls.push(['getToken', options.vapidKey]);
        return nextToken;
      },
      deleteToken: async () => {
        firebaseCalls.push(['deleteToken']);
        return true;
      },
    },
  }));
}

const notificationEntry = () =>
  getAppMenuItems()
    .flatMap(({ options }) => options)
    .find(({ label }) => label.includes('notifications'));

beforeEach(() => {
  firebaseCalls = [];
  unsubscribed = false;
  permission = 'default';
  nextToken = 'token-1';
  toasts = [];
  for (const type of ['success', 'warning', 'info', 'error']) {
    toast[type] = (message, options) =>
      toasts.push({ type, message, ...options });
  }
  fyo.user = USER;
  subscriptionStatus.value = { phase: 'trial', locked: false };
  stubBrowser();
  stubFirebaseModules();
  setPush(PUSH);
});

afterEach(() => {
  setPush(null);
  delete globalThis.localStorage;
  delete globalThis.Notification;
});

test('no entry when push is off or the browser has no push', () => {
  setPush(null);
  assert.equal(getPushState(), 'hidden');
  assert.equal(notificationEntry(), undefined);

  setPush(PUSH);
  stubBrowser({ supportsPush: false });
  assert.equal(getPushState(), 'hidden');
});

test('turning on asks only after the click, registers and flips the label', async () => {
  const requests = stubFrappe(() => ({ message: { name: 'dev1' } }));
  assert.equal(notificationEntry().label, 'Turn on notifications');
  assert.deepEqual(firebaseCalls, []);

  await turnOnPush();

  assert.deepEqual(firebaseCalls, [
    ['requestPermission'],
    ['getToken', 'vapid'],
  ]);
  assert.deepEqual(
    requests.map(({ path, body }) => [path, body]),
    [
      [
        REGISTER,
        {
          token: 'token-1',
          previous_token: null,
          device_label: 'Chrome on Android',
        },
      ],
    ]
  );
  assert.equal(storage.get(TOKEN_KEY), 'token-1');
  assert.equal(notificationEntry().label, 'Turn off notifications');
  assert.deepEqual(
    toasts.map(({ type, message }) => [type, message]),
    [['success', 'Notifications are on for this device.']]
  );
});

test('a blocked prompt shows a toast that stays and registers nothing', async () => {
  const requests = stubFrappe(() => ({ message: {} }));
  permission = 'denied';

  await turnOnPush();

  assert.deepEqual(requests, []);
  assert.deepEqual(
    toasts.map(({ type, message, duration }) => [type, message, duration]),
    [
      [
        'warning',
        'Notifications are blocked. Allow them for this site in your browser settings.',
        Infinity,
      ],
    ]
  );
});

test('an iPhone outside the Home Screen is told to add it first', async () => {
  stubBrowser({ userAgent: IPHONE_SAFARI, supportsPush: false });
  const requests = stubFrappe(() => ({ message: {} }));
  assert.equal(notificationEntry().label, 'Turn on notifications');

  await turnOnPush();

  assert.deepEqual(requests, []);
  assert.deepEqual(firebaseCalls, []);
  assert.equal(
    toasts[0].message,
    'Add RareBooks to your Home Screen first, then turn on notifications from there.'
  );
});

test('a locked site registers nothing', async () => {
  subscriptionStatus.value = { phase: 'locked', locked: true };
  const requests = stubFrappe(() => ({ message: {} }));

  // It waits on the lock notice dialog, which no one closes here.
  void turnOnPush();
  await flush();

  assert.deepEqual(requests, []);
  assert.deepEqual(firebaseCalls, []);
});

test('turning off drops the subscription, then the row', async () => {
  permission = 'granted';
  storage.set(TOKEN_KEY, 'token-1');
  const requests = stubFrappe(() => ({ message: { deleted: true } }));

  await turnOffPush();

  assert.deepEqual(firebaseCalls, [['deleteToken']]);
  assert.equal(unsubscribed, true);
  assert.deepEqual(
    requests.map(({ path, body }) => [path, body]),
    [[UNREGISTER, { token: 'token-1' }]]
  );
  assert.equal(storage.has(TOKEN_KEY), false);
  assert.equal(toasts[0].message, 'Notifications are off for this device.');
  assert.equal(getPushState(), 'off');
});

test('sign out stops push even when the server refuses', async () => {
  permission = 'granted';
  storage.set(TOKEN_KEY, 'token-1');
  const requests = stubFrappe(() => ({
    status: 403,
    body: { exc_type: 'SiteLockedError', exception: 'SiteLockedError' },
  }));

  await stopPushForSignOut();

  assert.equal(unsubscribed, true);
  assert.equal(requests[0].path, UNREGISTER);
  assert.equal(storage.has(TOKEN_KEY), false);
});

test('start up registers again with the stored token, and skips a locked site', async () => {
  permission = 'granted';
  storage.set(TOKEN_KEY, 'token-1');
  nextToken = 'token-2';
  const requests = stubFrappe(() => ({ message: { name: 'dev1' } }));

  await refreshPushRegistration();

  assert.deepEqual(requests[0].body.previous_token, 'token-1');
  assert.equal(requests[0].body.token, 'token-2');
  assert.equal(storage.get(TOKEN_KEY), 'token-2');

  subscriptionStatus.value = { phase: 'locked', locked: true };
  await refreshPushRegistration();
  assert.equal(requests.length, 1);
});

test('device labels name the browser and the system', () => {
  assert.equal(getDeviceLabel(CHROME_ANDROID), 'Chrome on Android');
  assert.equal(getDeviceLabel(IPHONE_SAFARI), 'Safari on iOS');
  assert.equal(
    getDeviceLabel(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15',
      5
    ),
    'Safari on iOS'
  );
  assert.equal(
    getDeviceLabel(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0'
    ),
    'Edge on Windows'
  );
  assert.equal(
    getDeviceLabel(
      'Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0'
    ),
    'Firefox on Linux'
  );
});

test('the entry reads on only with both the permission and the stored token', () => {
  permission = 'granted';
  assert.equal(getPushState(), 'off');
  storage.set(TOKEN_KEY, 'token-1');
  assert.equal(getPushState(), 'on');
  permission = 'denied';
  assert.equal(getPushState(), 'off');
});

test('the stored token belongs to one user only', () => {
  permission = 'granted';
  storage.set(TOKEN_KEY_PREFIX + 'someone@books.test', 'their-token');
  assert.equal(getPushState(), 'off');
});

test('an iPad outside the Home Screen is told to add RareBooks first', () => {
  stubBrowser({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15',
    supportsPush: false,
  });
  navigator.maxTouchPoints = 5;
  assert.equal(getPushState(), 'needs_install');

  navigator.maxTouchPoints = 0;
  assert.equal(getPushState(), 'hidden');
});

test('an iPhone opened from the Home Screen without push support shows no entry', () => {
  stubBrowser({
    userAgent: IPHONE_SAFARI,
    supportsPush: false,
    standalone: true,
  });
  assert.equal(getPushState(), 'hidden');
});

test('start up does nothing when the permission was revoked', async () => {
  permission = 'denied';
  storage.set(TOKEN_KEY, 'token-1');
  const requests = stubFrappe(() => ({ message: {} }));

  await refreshPushRegistration();

  assert.deepEqual(requests, []);
  assert.deepEqual(firebaseCalls, []);
});

test('sign out goes on after two seconds when the server never answers', async () => {
  permission = 'granted';
  storage.set(TOKEN_KEY, 'token-1');
  stubFrappe(() => new Promise(() => {}));

  const started = Date.now();
  await stopPushForSignOut();

  assert.ok(Date.now() - started < 3_000);
  assert.equal(unsubscribed, true);
});

test('sign out with push never turned on here asks nothing', async () => {
  const requests = stubFrappe(() => ({ message: {} }));
  await stopPushForSignOut();
  assert.deepEqual(requests, []);
  assert.deepEqual(firebaseCalls, []);
});

test('the Settings tab shows only while push is set up', () => {
  assert.equal(hasPush(), true);
  setPush(null);
  assert.equal(hasPush(), false);
});

test('device labels fall back for an unknown browser and system', () => {
  assert.equal(getDeviceLabel('curl/8.0'), 'Browser on an unknown system');
  assert.ok(getDeviceLabel('x'.repeat(500)).length <= 140);
});
