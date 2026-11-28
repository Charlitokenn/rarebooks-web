import { chromium, expect, test, type Page } from '@playwright/test';
import { waitForBooks } from './helpers/session';
import { bench, benchExecute, setPhase, site } from './helpers/subscription';

// Spec 0026: push notifications, with Google's Firebase endpoints and the browser push service
// stubbed (no real Firebase in CI). The test keys come from frappe_books/tests/push.py.
test.skip(!bench || !site, 'Requires an explicit Frappe test bench and site');
test.describe.configure({ mode: 'serial' });

const PUSH_USER = { usr: 'books-push@books.test', pwd: 'Books-Push-Test-1' };
const TOKEN = 'fcm-test-token';
const REGISTER = '**/api/method/frappe_books.notifications.register_device';
const UNREGISTER = '**/api/method/frappe_books.notifications.unregister_device';
const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1';

let cookies: Awaited<ReturnType<ReturnType<Page['context']>['cookies']>>;

/** A push subscription without a real push service, so Firebase gets a token from the stub below. */
const STUB_PUSH_SERVICE = `(() => {
  const key = new Uint8Array(65).fill(4).buffer;
  const auth = new Uint8Array(16).fill(1).buffer;
  let subscription = null;
  const make = () => ({
    endpoint: 'https://push.books.test/endpoint',
    expirationTime: null,
    options: { applicationServerKey: key, userVisibleOnly: true },
    getKey: (name) => (name === 'p256dh' ? key : auth),
    toJSON: () => ({ endpoint: 'https://push.books.test/endpoint', keys: { p256dh: 'BA', auth: 'AQ' } }),
    unsubscribe: async () => {
      subscription = null;
      window.__pushUnsubscribed = (window.__pushUnsubscribed || 0) + 1;
      return true;
    },
  });
  // Headless Chromium reports a granted permission as denied.
  if (window.Notification && window.__pushPermission !== 'denied') {
    Object.defineProperty(Notification, 'permission', { get: () => 'granted' });
    Notification.requestPermission = async () => 'granted';
  }
  if (window.PushManager) {
    PushManager.prototype.subscribe = async function () {
      subscription = make();
      return subscription;
    };
    PushManager.prototype.getSubscription = async function () {
      return subscription;
    };
    PushManager.prototype.permissionState = async () => 'granted';
  }
})();`;

async function stubFirebase(page: Page) {
  await page.addInitScript(STUB_PUSH_SERVICE);
  await page.route('https://firebaseinstallations.googleapis.com/**', (route) =>
    route.fulfill({
      json: {
        name: 'projects/books-push-test/installations/fid',
        fid: 'cKfidTest0000000000000',
        refreshToken: 'refresh',
        authToken: { token: 'installation-auth', expiresIn: '604800s' },
      },
    })
  );
  await page.route('https://fcmregistrations.googleapis.com/**', (route) =>
    route.fulfill({ json: { token: TOKEN } })
  );
}

async function open(page: Page, path = '/books') {
  await page.goto(path);
  await waitForBooks(page);
}

const bootPush = (page: Page) =>
  page.evaluate(
    () =>
      (
        window as Window & {
          frappe?: { boot?: { books?: { push?: unknown } } };
        }
      ).frappe?.boot?.books?.push ?? null
  );

/** Web workers cache site_config.json for 60 seconds, so a config switch takes a while. */
async function waitForPush(page: Page, on: boolean) {
  await expect
    .poll(
      async () => {
        await open(page);
        return !!(await bootPush(page));
      },
      { timeout: 90_000, intervals: [2_000, 5_000] }
    )
    .toBe(on);
}

async function openAppMenu(page: Page) {
  await page.getByTestId('company-name').getByRole('button').click();
}

const menuItem = (page: Page, name: string) =>
  page.getByRole('menuitem', { name });

test.beforeAll(async ({ browser, baseURL }) => {
  await benchExecute('frappe_books.tests.subscription.make_user', {
    args: [PUSH_USER.usr, 'Books Manager', PUSH_USER.pwd],
  });
  await benchExecute('frappe_books.tests.push.turn_push_on');
  const context = await browser.newContext({ baseURL });
  const response = await context.request.post('/api/method/login', {
    form: PUSH_USER,
  });
  expect(response.ok()).toBe(true);
  cookies = await context.cookies();
  await context.close();
});

test.afterAll(async () => {
  await benchExecute('frappe_books.tests.push.turn_push_off');
  await benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site');
});

test.beforeEach(async ({ page }) => {
  await page.context().addCookies(cookies);
});

test('turning on asks, registers this device and flips the entry (AC-2, AC-3)', async ({
  page,
  context,
}) => {
  test.setTimeout(150_000);
  await context.grantPermissions(['notifications']);
  await stubFirebase(page);
  await waitForPush(page, true);
  // The public config only: never the service account key (AC-12).
  expect(await page.content()).not.toContain('PRIVATE KEY');

  const registered = page.waitForRequest(REGISTER);
  await openAppMenu(page);
  await menuItem(page, 'Turn on notifications').click();

  const body = (await registered).postDataJSON();
  expect(body).toMatchObject({ token: TOKEN, previous_token: null });
  expect(body.device_label).toMatch(/ on /);
  await expect(
    page.getByText('Notifications are on for this device.')
  ).toBeVisible();

  await openAppMenu(page);
  await expect(menuItem(page, 'Turn off notifications')).toBeVisible();
});

test('turning off drops the subscription and the row (AC-4)', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['notifications']);
  await stubFirebase(page);
  await open(page);
  await openAppMenu(page);
  await menuItem(page, 'Turn on notifications').click();
  await expect(
    page.getByText('Notifications are on for this device.')
  ).toBeVisible();

  const unregistered = page.waitForRequest(UNREGISTER);
  await openAppMenu(page);
  await menuItem(page, 'Turn off notifications').click();

  expect((await unregistered).postDataJSON()).toEqual({ token: TOKEN });
  await expect(
    page.getByText('Notifications are off for this device.')
  ).toBeVisible();
  await openAppMenu(page);
  await expect(menuItem(page, 'Turn on notifications')).toBeVisible();
});

test('signing out stops push before the Frappe logout (AC-4)', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['notifications']);
  await stubFirebase(page);
  await open(page);
  await openAppMenu(page);
  await menuItem(page, 'Turn on notifications').click();
  await expect(
    page.getByText('Notifications are on for this device.')
  ).toBeVisible();

  const order: string[] = [];
  await page.route(UNREGISTER, async (route) => {
    order.push('unregister');
    await route.continue();
  });
  // Answer the logout here, so the shared session cookie stays signed in.
  await page.route('**/api/method/logout', async (route) => {
    order.push('logout');
    await route.fulfill({ json: { message: null } });
  });
  await openAppMenu(page);
  await menuItem(page, 'Log out').click();

  // The faked logout keeps the session, so /login sends this Manager back to /books.
  await expect.poll(() => order).toEqual(['unregister', 'logout']);
});

test('a blocked prompt shows a toast that stays (AC-2)', async ({ page }) => {
  await page.addInitScript(() => {
    Notification.requestPermission = async () => 'denied';
  });
  let registered = false;
  page.on('request', (request) => {
    registered ||= request.url().includes('register_device');
  });
  await open(page);
  await openAppMenu(page);
  await menuItem(page, 'Turn on notifications').click();

  await expect(
    page.getByText(
      'Notifications are blocked. Allow them for this site in your browser settings.'
    )
  ).toBeVisible();
  expect(registered).toBe(false);
});

test.describe('an iPhone outside the Home Screen', () => {
  test.use({ userAgent: IPHONE_SAFARI });

  test('is told to add RareBooks first (AC-2)', async ({ page }) => {
    await page.addInitScript(() => {
      delete (window as Partial<Window & { PushManager: unknown }>).PushManager;
    });
    await open(page);
    await openAppMenu(page);
    await menuItem(page, 'Turn on notifications').click();

    await expect(
      page.getByText(
        'Add RareBooks to your Home Screen first, then turn on notifications from there.'
      )
    ).toBeVisible();
  });
});

test('a locked site shows the lock notice and registers nothing (AC-13)', async ({
  page,
  context,
}) => {
  test.setTimeout(150_000);
  await context.grantPermissions(['notifications']);
  await stubFirebase(page);
  await setPhase(page, 'locked');
  let registered = false;
  page.on('request', (request) => {
    registered ||= request.url().includes('register_device');
  });
  await open(page);
  await openAppMenu(page);
  await menuItem(page, 'Turn on notifications').click();

  await expect(page.getByRole('dialog')).toContainText('read only');
  expect(registered).toBe(false);
  await benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site');
});

test('the Notifications tab switches an event off for the shop (AC-8)', async ({
  page,
}) => {
  await page.goto('/books/settings?tab=NotificationSettings');
  await waitForBooks(page);
  const settings = page.getByRole('dialog', { name: 'Settings' });
  await expect(
    settings.getByRole('tab', { name: 'Notifications' })
  ).toHaveAttribute('aria-selected', 'true');
  for (const name of ['Payment received', 'Low stock', 'Subscription']) {
    await expect(settings.getByRole('switch', { name })).toBeChecked();
  }

  const saved = page.waitForResponse((response) =>
    response.url().includes('/api/v2/document/Books%20Notification%20Settings')
  );
  await settings.getByRole('switch', { name: 'Low stock' }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  expect((await saved).ok()).toBe(true);
  await page.getByRole('button', { name: 'No', exact: true }).click();

  const response = await page.request.get(
    '/api/v2/document/Books Notification Settings/Books Notification Settings'
  );
  expect((await response.json()).data.low_stock).toBe(0);
  await settings.getByRole('switch', { name: 'Low stock' }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
});

test('without the Firebase keys there is no entry (AC-1)', async ({ page }) => {
  test.setTimeout(150_000);
  await benchExecute('frappe_books.tests.push.turn_push_off');
  await waitForPush(page, false);
  await openAppMenu(page);

  await expect(menuItem(page, 'Documentation')).toBeVisible();
  await expect(menuItem(page, 'Turn on notifications')).toHaveCount(0);
});

test('a tapped push moves an open /books tab the worker does not control (AC-11)', async ({
  page,
  context,
}) => {
  // /books sits outside the worker's /books/ scope, so the worker can't navigate it and messages it instead.
  await open(page, '/books');
  await page.evaluate(() =>
    navigator.serviceWorker.register('/books/sw.js', { scope: '/books/' })
  );
  const worker =
    context.serviceWorkers()[0] ??
    (await context.waitForEvent('serviceworker'));
  expect(await page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(
    false
  );
  const origin = new URL(page.url()).origin;

  // The worker's own click step. Outside a real tap the browser refuses its final focus(), which is fine here.
  const tap = (link: string) =>
    worker.evaluate(
      (url) =>
        (self as unknown as { openBooks: (url: string) => Promise<void> })
          .openBooks(url)
          .catch(() => undefined),
      link
    );

  await tap(`${origin}/books/list/SalesInvoice`);
  await expect(page).toHaveURL(/\/books\/list\/SalesInvoice$/);

  // A link outside /books is ignored by the page.
  await worker.evaluate(async () => {
    const windows = await self.clients.matchAll({
      type: 'window',
      includeUncontrolled: true,
    });
    windows.forEach((client) =>
      client.postMessage({
        type: 'books-push-open',
        link: 'https://evil.test/books/',
      })
    );
  });
  await page.waitForTimeout(500);
  await expect(page).toHaveURL(/\/books\/list\/SalesInvoice$/);
});

// The old headless mode refuses every notification; the new one (channel `chromium`) shows them.
// A click can't be made from a test (the worker may focus a window only inside a real click).
test('the service worker shows a push only for a /books link (AC-11)', async ({
  baseURL,
}) => {
  const browser = await chromium.launch({ channel: 'chromium' });
  const context = await browser.newContext({ baseURL });
  try {
    await context.addCookies(cookies);
    const page = await context.newPage();

    await context.grantPermissions(['notifications']);
    await open(page);
    const worker = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.register(
        '/books/sw.js',
        {
          scope: '/books/',
        }
      );
      return registration.scope;
    });
    expect(worker).toMatch(/\/books\/$/);
    if (!context.serviceWorkers().length) {
      await context.waitForEvent('serviceworker');
    }

    const cdp = await context.newCDPSession(page);
    const registrationId = new Promise<string>((resolve) => {
      cdp.on('ServiceWorker.workerRegistrationUpdated', ({ registrations }) => {
        const books = registrations.find(({ scopeURL }) =>
          scopeURL.endsWith('/books/')
        );
        if (books) resolve(books.registrationId);
      });
    });
    await cdp.send('ServiceWorker.enable');
    const origin = new URL(page.url()).origin;
    const deliver = async (data: Record<string, string>) =>
      cdp.send('ServiceWorker.deliverPushMessage', {
        origin,
        registrationId: await registrationId,
        data: JSON.stringify({ data }),
      });
    const shown = () =>
      page.evaluate(async () => {
        const registration =
          await navigator.serviceWorker.getRegistration('/books/');
        const notifications = (await registration?.getNotifications()) ?? [];
        return notifications.map(({ title, body, tag, data }) => ({
          title,
          body,
          tag,
          data,
        }));
      });

    // A push with a link outside /books, or no title, shows nothing.
    await deliver({
      title: 'Phish',
      body: 'x',
      link: 'https://evil.test/books/',
      tag: 'a',
    });
    await deliver({ title: '', body: 'x', link: '/books/', tag: 'b' });
    await deliver({
      title: 'Payment received',
      body: 'Asha paid Sh 5,000.00',
      link: '/books/edit/Payment/PAY-1001',
      tag: 'payment:PAY-1001',
    });

    await expect.poll(shown).toEqual([
      {
        title: 'Payment received',
        body: 'Asha paid Sh 5,000.00',
        tag: 'payment:PAY-1001',
        data: { link: `${origin}/books/edit/Payment/PAY-1001` },
      },
    ]);
  } finally {
    await browser.close();
  }
});
