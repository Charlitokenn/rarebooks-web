import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import {
  getAppMenuItems,
  router,
  stubFrappe,
  subscriptionStatus,
  supportChat,
  toast,
} from './helpers/frappe.mjs';

const {
  STORED_EMAIL_KEY,
  endSupportChat,
  hasSupportChat,
  openSupportChat,
  resetSupportChat,
  setSupportChat,
} = supportChat;

// Spec 0009: a signed tawk.to chat, loaded only when the user asks for it.
const CHAT = {
  property_id: 'property-123',
  widget_id: 'widget-abc',
  visitor: { name: 'Asha', email: 'asha@books.test', hash: 'abc123' },
  attributes: { company: 'Asha Books', site: 'asha.books.test' },
  support_email: 'help@books.test',
};

let scripts;
let storage;
let toasts;

/** A document that records the script tags the loader adds. */
function stubDocument() {
  scripts = [];
  globalThis.document = {
    head: { appendChild: (element) => scripts.push(element) },
    createElement: () => {
      const element = {
        attributes: {},
        setAttribute: (name, value) => (element.attributes[name] = value),
        remove: () => scripts.splice(scripts.indexOf(element), 1),
      };
      return element;
    },
    getElementById: (id) => scripts.find((script) => script.id === id),
  };
}

function stubStorage() {
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
}

/** Records every tawk.to API call, as tawk.to's script would add them on load. */
function loadTawk({ logout = (callback) => callback() } = {}) {
  const api = globalThis.window.Tawk_API;
  const calls = [];
  for (const name of ['hideWidget', 'showWidget', 'maximize']) {
    api[name] = () => calls.push([name]);
  }
  api.setAttributes = (attributes, callback) => {
    calls.push(['setAttributes', attributes]);
    callback?.();
  };
  api.logout = (callback) => {
    calls.push(['logout']);
    logout(callback);
  };
  api.onLoad();
  return calls;
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

beforeEach(() => {
  resetSupportChat();
  globalThis.window = { open: () => {} };
  stubDocument();
  stubStorage();
  toasts = [];
  toast.warning = (message, options) => toasts.push({ message, ...options });
  router.currentRoute = { value: { path: '/pos' } };
  subscriptionStatus.value = { phase: 'trial' };
});

afterEach(() => {
  delete globalThis.document;
  delete globalThis.localStorage;
});

const getChatEntry = () =>
  getAppMenuItems()
    .flatMap(({ options }) => options)
    .find(({ label }) => label === 'Chat with support');

test('no chat block means no entry and no tawk.to script (AC-1)', async () => {
  setSupportChat(null);
  assert.equal(hasSupportChat(), false);
  assert.equal(getChatEntry(), undefined);

  await openSupportChat();
  assert.equal(scripts.length, 0);
});

test('the Help group carries the entry when the chat is on (AC-2)', () => {
  setSupportChat(CHAT);
  const help = getAppMenuItems()[0];
  assert.equal(help.group, 'Help');
  assert.ok(help.options.some(({ label }) => label === 'Chat with support'));
});

test('the first pick loads the script once with the signed visitor (AC-3, AC-4, AC-5)', async () => {
  setSupportChat(CHAT);
  const opening = openSupportChat();
  const second = openSupportChat();

  assert.equal(scripts.length, 1);
  const [script] = scripts;
  assert.equal(script.src, 'https://embed.tawk.to/property-123/widget-abc');
  assert.equal(script.async, true);
  assert.equal(script.charset, 'UTF-8');
  assert.equal(script.attributes.crossorigin, '*');
  assert.deepEqual(globalThis.window.Tawk_API.visitor, CHAT.visitor);

  const calls = loadTawk();
  await Promise.all([opening, second]);

  assert.deepEqual(calls, [
    ['hideWidget'],
    [
      'setAttributes',
      {
        ...CHAT.attributes,
        phase: 'trial',
        screen: '/books/pos',
        ...CHAT.visitor,
      },
    ],
    ['showWidget'],
    ['maximize'],
  ]);
  assert.equal(storage.get(STORED_EMAIL_KEY), CHAT.visitor.email);
});

test('a later pick sends the live phase and screen without a second script (AC-3, AC-5)', async () => {
  setSupportChat(CHAT);
  const opening = openSupportChat();
  const calls = loadTawk();
  await opening;
  calls.length = 0;

  subscriptionStatus.value = { phase: 'locked' };
  router.currentRoute = { value: { path: '/list/SalesInvoice' } };
  await openSupportChat();

  assert.equal(scripts.length, 1);
  assert.deepEqual(calls, [
    [
      'setAttributes',
      {
        phase: 'locked',
        screen: '/books/list/SalesInvoice',
        ...CHAT.visitor,
      },
    ],
    ['showWidget'],
    ['maximize'],
  ]);
});

test('minimizing or closing the chat hides the bubble again (AC-3, AC-10)', async () => {
  setSupportChat(CHAT);
  const opening = openSupportChat();
  const calls = loadTawk();
  await opening;
  calls.length = 0;

  globalThis.window.Tawk_API.onChatMinimized();
  globalThis.window.Tawk_API.onChatHidden();
  assert.deepEqual(calls, [['hideWidget'], ['hideWidget']]);
});

test('a blocked script shows the support email and the next pick tries again (AC-8)', async () => {
  setSupportChat(CHAT);
  const opening = openSupportChat();
  scripts[0].onerror();
  await opening;

  assert.equal(scripts.length, 0);
  assert.deepEqual(toasts, [
    {
      message: 'Chat could not load. Write to help@books.test.',
      id: 'support-chat-failed',
      duration: Infinity,
      action: undefined,
    },
  ]);

  const retry = openSupportChat();
  assert.equal(scripts.length, 1);
  loadTawk();
  await retry;
});

test('without a support email the toast says to try later (AC-8)', async () => {
  setSupportChat({ ...CHAT, support_email: undefined });
  const opening = openSupportChat();
  scripts[0].onerror();
  await opening;
  assert.equal(
    toasts[0].message,
    'Chat could not load. Please try again later.'
  );
});

test('an onLoad after the 10 second timeout does nothing (AC-8)', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  setSupportChat(CHAT);
  const opening = openSupportChat();
  const lateApi = globalThis.window.Tawk_API;
  t.mock.timers.tick(10_000);
  await opening;

  assert.equal(toasts.length, 1);
  assert.equal(scripts.length, 0);

  const calls = [];
  lateApi.hideWidget = () => calls.push('hideWidget');
  lateApi.maximize = () => calls.push('maximize');
  lateApi.onLoad();
  await flush();
  assert.deepEqual(calls, []);
  assert.equal(toasts.length, 1);
});

test('signing out logs out of tawk.to before the Frappe logout (AC-9)', async () => {
  setSupportChat(CHAT);
  const opening = openSupportChat();
  const calls = loadTawk();
  await opening;

  const order = [];
  globalThis.window.location = { assign: () => order.push('assign') };
  const requests = stubFrappe(({ path }) => {
    order.push(path);
    return { message: null };
  });
  globalThis.window.Tawk_API.logout = (callback) => {
    order.push('tawk logout');
    callback();
  };
  const logOut = getAppMenuItems()
    .flatMap(({ options }) => options)
    .find(({ label }) => label === 'Log out');
  await logOut.onClick();

  assert.deepEqual(order, ['tawk logout', '/api/method/logout', 'assign']);
  assert.equal(requests.length, 1);
  assert.equal(storage.has(STORED_EMAIL_KEY), false);
  assert.ok(calls.length > 0);
});

test('a tawk.to logout that never answers still ends after 2 seconds (AC-9)', async (t) => {
  setSupportChat(CHAT);
  const opening = openSupportChat();
  loadTawk();
  await opening;

  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  globalThis.window.Tawk_API.logout = () => {};
  let ended = false;
  const ending = endSupportChat().then(() => (ended = true));
  await flush();
  assert.equal(ended, false);
  t.mock.timers.tick(2_000);
  await ending;
  assert.equal(ended, true);
});

test('signing out before any chat makes no tawk.to call (AC-9)', async () => {
  setSupportChat(CHAT);
  storage.set(STORED_EMAIL_KEY, 'old@books.test');
  await endSupportChat();
  assert.equal(globalThis.window.Tawk_API, undefined);
  assert.equal(storage.has(STORED_EMAIL_KEY), false);
});

test("another user's stored email logs tawk.to out before the new identity (AC-9)", async () => {
  setSupportChat(CHAT);
  storage.set(STORED_EMAIL_KEY, 'previous@books.test');
  const opening = openSupportChat();
  const calls = loadTawk();
  await opening;

  assert.deepEqual(calls.slice(0, 3), [
    ['hideWidget'],
    ['logout'],
    ['setAttributes', CHAT.visitor],
  ]);
  assert.deepEqual(calls[3][0], 'setAttributes');
  assert.equal(storage.get(STORED_EMAIL_KEY), CHAT.visitor.email);
});

test('blocked storage never stops the chat', async () => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    get() {
      throw new Error('SecurityError');
    },
  });
  setSupportChat(CHAT);
  const opening = openSupportChat();
  const calls = loadTawk();
  await opening;
  assert.deepEqual(calls.at(-1), ['maximize']);
  await endSupportChat();
});

test('phase and screen are cut to 255 characters, and an empty phase is left out (AC-5)', async () => {
  setSupportChat(CHAT);
  subscriptionStatus.value = null;
  router.currentRoute = { value: { path: '/' + 'x'.repeat(300) } };
  const opening = openSupportChat();
  const calls = loadTawk();
  await opening;

  const [, attributes] = calls.find(([name]) => name === 'setAttributes');
  assert.equal('phase' in attributes, false);
  assert.equal(attributes.screen.length, 255);
});
