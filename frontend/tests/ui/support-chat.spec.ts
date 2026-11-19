import { expect, test, type Page, type Route } from '@playwright/test';
import { waitForBooks } from './helpers/session';
import {
  bench,
  benchExecute,
  setPhase,
  site,
  waitForPhase,
} from './helpers/subscription';

// Spec 0009: the tawk.to support chat, against a stub tawk.to script (no real tawk.to in CI).
test.skip(!bench || !site, 'Requires an explicit Frappe test bench and site');
test.describe.configure({ mode: 'serial' });

const CHAT_USER = {
  usr: 'books-chat@books.test',
  pwd: 'Books-Chat-Test-1',
};
const SUPPORT_EMAIL = 'help@books.test';
const TAWK = 'https://embed.tawk.to/**';
const PHONE = {
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
};

/**
 * Stands in for the tawk.to embed: a floating bubble the API shows and hides,
 * and every API call recorded in `window.__tawkCalls`.
 */
const STUB_TAWK = `(() => {
  const api = window.Tawk_API;
  const calls = (window.__tawkCalls = window.__tawkCalls || []);
  window.__tawkLoads = (window.__tawkLoads || 0) + 1;
  const bubble = document.createElement('div');
  bubble.id = 'tawk-stub-bubble';
  bubble.textContent = 'Chat';
  bubble.style.cssText = 'position:fixed;bottom:16px;right:16px;width:60px;height:60px;z-index:9999;background:#03a84e';
  document.body.appendChild(bubble);
  const record = (name, run) => (...args) => {
    calls.push([name, ...args.filter((arg) => typeof arg !== 'function')]);
    return run && run(...args);
  };
  api.hideWidget = record('hideWidget', () => (bubble.style.display = 'none'));
  api.showWidget = record('showWidget', () => (bubble.style.display = 'block'));
  api.maximize = record('maximize');
  api.setAttributes = record('setAttributes', (attributes, callback) => callback && callback());
  api.logout = record('logout', (callback) => callback && callback());
  api.minimize = () => api.onChatMinimized && api.onChatMinimized();
  api.onLoad && api.onLoad();
})();`;

let cookies: Awaited<ReturnType<ReturnType<Page['context']>['cookies']>>;

type TawkCall = [string, ...unknown[]];

/** The page's window as the loader and the stub leave it. */
type ChatWindow = Window & {
  frappe?: { boot?: { books?: { support_chat?: unknown } } };
  Tawk_API?: {
    visitor?: { name: string; email: string; hash: string };
    minimize?: () => void;
  };
  __tawkCalls?: TawkCall[];
  __tawkLoads?: number;
};

const tawkCalls = (page: Page) =>
  page.evaluate(() => (window as ChatWindow).__tawkCalls ?? []);

const bootChat = (page: Page) =>
  page.evaluate(
    () => (window as ChatWindow).frappe?.boot?.books?.support_chat ?? null
  );

async function serveStub(page: Page, body = STUB_TAWK) {
  await page.route(TAWK, (route: Route) =>
    route.fulfill({ contentType: 'application/javascript', body })
  );
}

async function open(page: Page, path = '/books') {
  await page.goto(path);
  await waitForBooks(page);
}

/** Web workers cache site_config.json for 60 seconds, so a config switch takes a while. */
async function waitForChat(page: Page, on: boolean) {
  await expect
    .poll(
      async () => {
        await open(page);
        return !!(await bootChat(page));
      },
      { timeout: 90_000, intervals: [2_000, 5_000] }
    )
    .toBe(on);
}

async function openAppMenu(page: Page, isPhone = false) {
  if (isPhone) {
    await page.getByRole('button', { name: 'Menu' }).click();
    await page
      .getByRole('dialog', { name: 'Books' })
      .getByTestId('company-name')
      .getByRole('button')
      .click();
  } else {
    await page.getByTestId('company-name').getByRole('button').click();
  }
}

async function pickChat(page: Page, isPhone = false) {
  await openAppMenu(page, isPhone);
  await page.getByRole('menuitem', { name: 'Chat with support' }).click();
}

const bubble = (page: Page) => page.locator('#tawk-stub-bubble');

test.beforeAll(async ({ browser, baseURL }) => {
  await benchExecute('frappe_books.tests.subscription.make_user', {
    args: [CHAT_USER.usr, 'Books User', CHAT_USER.pwd],
  });
  await benchExecute('frappe_books.tests.support_chat.turn_chat_on', {
    kwargs: { support_email: SUPPORT_EMAIL },
  });
  const context = await browser.newContext({ baseURL });
  const response = await context.request.post('/api/method/login', {
    form: CHAT_USER,
  });
  expect(response.ok()).toBe(true);
  cookies = await context.cookies();
  await context.close();
});

test.afterAll(async () => {
  await benchExecute('frappe_books.tests.support_chat.turn_chat_off');
  await benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site');
});

test.beforeEach(async ({ page }) => {
  await page.context().addCookies(cookies);
});

test('the first pick loads tawk.to once with the signed visitor (AC-2 to AC-5)', async ({
  page,
}) => {
  const requests: string[] = [];
  page.on('request', (request) => {
    if (request.url().startsWith('https://embed.tawk.to/')) {
      requests.push(request.url());
    }
  });
  await serveStub(page);
  await waitForChat(page, true);
  await open(page, '/books/list/SalesInvoice?status=Paid#top');
  expect(requests).toEqual([]);

  await pickChat(page);
  await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);
  expect(requests).toEqual(['https://embed.tawk.to/test-property/test-widget']);

  const visitor = await page.evaluate(
    () => (window as ChatWindow).Tawk_API?.visitor
  );
  expect(visitor?.email).toBe(CHAT_USER.usr);
  expect(visitor?.hash).toMatch(/^[0-9a-f]{64}$/);
  const html = await page.content();
  expect(html).not.toContain('test-secure-mode-key');

  const calls = await tawkCalls(page);
  const attributes = calls.find(([name]) => name === 'setAttributes')?.[1];
  expect(attributes).toMatchObject({
    roles: 'Books User',
    screen: '/books/list/SalesInvoice',
  });
  expect(attributes).toHaveProperty('phase');
  expect(attributes).toHaveProperty('site');
  expect(attributes).toHaveProperty('app-version');
  await expect(bubble(page)).toBeVisible();

  await page.evaluate(() => (window as ChatWindow).Tawk_API?.minimize?.());
  await expect(bubble(page)).toBeHidden();

  await pickChat(page);
  await expect(bubble(page)).toBeVisible();
  expect(await page.evaluate(() => (window as ChatWindow).__tawkLoads)).toBe(1);
  expect(requests).toHaveLength(1);
});

test('a blocked tawk.to shows the support email and /books keeps working (AC-8)', async ({
  page,
}) => {
  await page.route(TAWK, (route) => route.abort());
  await open(page);
  await pickChat(page);

  await expect(
    page.getByText(`Chat could not load. Write to ${SUPPORT_EMAIL}.`)
  ).toBeVisible();
  await page.getByRole('link', { name: 'Sales', exact: true }).first().click();
  await expect(page).toHaveURL(/\/books\//);
});

test('a tawk.to that never loads times out after 10 seconds (AC-8)', async ({
  page,
}) => {
  await page.clock.install();
  await serveStub(page, '// never calls onLoad');
  await open(page);
  await pickChat(page);
  await expect
    .poll(() => page.locator('script#books-support-chat').count())
    .toBe(1);

  await page.clock.fastForward(10_000);
  await expect(
    page.getByText(`Chat could not load. Write to ${SUPPORT_EMAIL}.`)
  ).toBeVisible();
  await expect(page.locator('script#books-support-chat')).toHaveCount(0);
});

test('signing out ends the tawk.to session before the Frappe logout (AC-9)', async ({
  page,
}) => {
  await serveStub(page);
  await open(page);
  await pickChat(page);
  await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);

  let callsAtLogout: TawkCall[] = [];
  // Answer the logout here, so the shared session cookie stays signed in.
  await page.route('**/api/method/logout', async (route) => {
    callsAtLogout = await tawkCalls(page);
    await route.fulfill({ json: { message: null } });
  });
  await openAppMenu(page);
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  await page.waitForURL(/\/login/);

  expect(callsAtLogout).toContainEqual(['logout']);
});

test('a tawk.to logout that never answers still signs out (AC-9)', async ({
  page,
}) => {
  await serveStub(
    page,
    STUB_TAWK.replace(
      "api.logout = record('logout', (callback) => callback && callback());",
      "api.logout = record('logout');"
    )
  );
  await open(page);
  await pickChat(page);
  await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);

  await page.route('**/api/method/logout', (route) =>
    route.fulfill({ json: { message: null } })
  );
  await openAppMenu(page);
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  await page.waitForURL(/\/login/, { timeout: 10_000 });
});

test("another user's chat in this browser is logged out first (AC-9)", async ({
  page,
}) => {
  await serveStub(page);
  await page.addInitScript(() =>
    localStorage.setItem('books_support_chat_email', 'someone-else@books.test')
  );
  await open(page);
  await pickChat(page);
  await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);

  const names = (await tawkCalls(page)).map(([name]) => name);
  expect(names.indexOf('logout')).toBeLessThan(names.indexOf('setAttributes'));
});

test('the Subscription page opens the chat (AC-7)', async ({ page }) => {
  await serveStub(page);
  await open(page, '/books/subscription');
  await page.getByTestId('subscription-support-chat').click();
  await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);
});

test.describe('on a phone', () => {
  test.use(PHONE);

  for (const path of ['/books', '/books/pos']) {
    test(`no tawk.to element floats over ${path} while the chat is closed (AC-10)`, async ({
      page,
    }) => {
      await serveStub(page);
      await open(page, path);
      await expect(bubble(page)).toHaveCount(0);

      await pickChat(page, true);
      await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);
      await page.evaluate(() => (window as ChatWindow).Tawk_API?.minimize?.());
      await expect(bubble(page)).toBeHidden();
    });
  }
});

test('a locked site still chats, from the banner, with phase locked (AC-6)', async ({
  page,
}) => {
  await serveStub(page);
  await open(page);
  await setPhase(page, 'locked');
  await open(page);

  await page.getByTestId('banner-support-chat').click();
  await expect.poll(() => tawkCalls(page)).toContainEqual(['maximize']);
  const attributes = (await tawkCalls(page)).find(
    ([name]) => name === 'setAttributes'
  )?.[1];
  expect(attributes).toMatchObject({ phase: 'locked' });

  await openAppMenu(page);
  await expect(
    page.getByRole('menuitem', { name: 'Chat with support' })
  ).toBeVisible();
});

test('with the keys off there is no entry and no tawk.to request (AC-1)', async ({
  page,
}) => {
  await benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site');
  await waitForPhase(page, 'unmanaged');
  await benchExecute('frappe_books.tests.support_chat.turn_chat_off');
  const requests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('tawk.to')) {
      requests.push(request.url());
    }
  });
  await waitForChat(page, false);

  await openAppMenu(page);
  await expect(page.getByRole('menuitem', { name: 'Log out' })).toBeVisible();
  await expect(
    page.getByRole('menuitem', { name: 'Chat with support' })
  ).toHaveCount(0);
  expect(requests).toEqual([]);
});
