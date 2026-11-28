/* eslint-disable no-console -- the tests stub console.warn to count the one AC-11 warning */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import {
  FrappeDoc,
  analytics,
  loadFrappeDocTypes,
  loadSaved,
  newFrappeDoc,
  registerFrappeModels,
  stubFrappe,
} from './helpers/frappe.mjs';

const {
  QUEUE_LIMIT,
  captureError,
  getInitOptions,
  getQueueLength,
  resetAnalytics,
  scrubEvent,
  setLoader,
  startAnalytics,
  track,
  trackPageview,
} = analytics;

// Spec 0027: PostHog in /books, with no record name ever leaving the site.
const BOOT = {
  key: 'phc_test',
  distinct_id: 'd9f957b938db79e1fc183ae612d775f7',
  site_key: 'duka.rarebooks.cc',
  roles: ['Books User'],
  country_code: 'tz',
  language: 'sw',
};
const ORIGIN = 'https://duka.rarebooks.cc';
const CUSTOMER = 'Mama Asha Traders';
const MODIFIED = '2026-11-28 10:00:00.000000';

const entryMeta = {
  name: 'Books Entry',
  autoname: 'Prompt',
  is_submittable: 1,
  permissions: [],
  fields: [{ fieldname: 'party', fieldtype: 'Data', label: 'Party' }],
};
const settingsMeta = {
  name: 'Books Entry Settings',
  issingle: 1,
  permissions: [],
  fields: [{ fieldname: 'note', fieldtype: 'Data', label: 'Note' }],
};
class Entry extends FrappeDoc {
  static doctype = 'Books Entry';
  static presentation = { label: 'Entry' };
}
class EntrySettings extends FrappeDoc {
  static doctype = 'Books Entry Settings';
  static presentation = { label: 'Entry Settings' };
}
registerFrappeModels({ Entry, EntrySettings });
stubFrappe(() => ({
  message: { metas: [entryMeta, settingsMeta], placements: {} },
}));
await loadFrappeDocTypes();

/** A posthog-js stand in that records what /books asks of it. */
function fakePostHog() {
  const calls = [];
  const record =
    (name) =>
    (...args) =>
      calls.push([name, ...args]);
  return {
    calls,
    init: record('init'),
    identify: record('identify'),
    group: record('group'),
    register: record('register'),
    capture: record('capture'),
    captureException: record('captureException'),
    captured: () =>
      calls.filter(([name]) => name === 'capture').map((call) => call.slice(1)),
  };
}

function route(path, template, params = {}, name) {
  return { path, name, params, matched: [{ path: template }] };
}
const START = { path: '/', params: {}, matched: [] };

let posthog;
let warnings;
let warn;

beforeEach(() => {
  resetAnalytics();
  posthog = fakePostHog();
  setLoader(async () => posthog);
  window.frappe.boot.books.analytics = BOOT;
  warnings = [];
  warn = console.warn;
  console.warn = (...args) => warnings.push(args);
});

afterEach(() => {
  console.warn = warn;
  delete window.frappe.boot.books.analytics;
  resetAnalytics();
});

// covers: AC-4
test('PostHog starts with the exact options, the person, the site group and the shared properties', async () => {
  await startAnalytics(BOOT, '16.1.0');

  const [init] = posthog.calls;
  assert.equal(init[0], 'init');
  assert.equal(init[1], 'phc_test');
  const { before_send, ...options } = init[2];
  assert.equal(typeof before_send, 'function');
  assert.deepEqual(options, {
    api_host: 'https://eu.i.posthog.com',
    ui_host: 'https://eu.posthog.com',
    capture_pageview: false,
    capture_pageleave: false,
    autocapture: false,
    disable_session_recording: true,
    disable_surveys: true,
    advanced_disable_flags: true,
    person_profiles: 'identified_only',
    persistence: 'localStorage',
    capture_exceptions: {
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
      capture_console_errors: false,
    },
  });
  assert.deepEqual(posthog.calls.slice(1), [
    [
      'identify',
      BOOT.distinct_id,
      { books_roles: ['Books User'], language: 'sw' },
    ],
    ['group', 'site', 'duka.rarebooks.cc'],
    [
      'register',
      {
        site_key: 'duka.rarebooks.cc',
        country_code: 'tz',
        app_version: '16.1.0',
      },
    ],
  ]);
  assert.equal(Object.keys(getInitOptions()).length, 12);
});

// covers: AC-3, AC-8, AC-19
test('with analytics off nothing loads and nothing is queued', async () => {
  delete window.frappe.boot.books.analytics;
  let loads = 0;
  setLoader(async () => {
    loads++;
    return posthog;
  });

  track('doc_created', { schema_name: 'Entry' });
  trackPageview(route('/list/Entry', '/list/:schemaName/:pageTitle?'), START);
  captureError(new TypeError('boom'));
  await startAnalytics(null, '16.1.0');

  assert.equal(loads, 0);
  assert.equal(getQueueLength(), 0);
  assert.deepEqual(posthog.calls, []);
});

// covers: AC-5, AC-8
test('the first pageview waits for PostHog, then each navigation sends its route template', async () => {
  const form = route(
    `/edit/SalesInvoice/${CUSTOMER}`,
    '/edit/:schemaName/:name',
    { schemaName: 'SalesInvoice', name: CUSTOMER },
    'CommonForm'
  );
  trackPageview(form, START);
  assert.equal(getQueueLength(), 1);

  await startAnalytics(BOOT, '16.1.0');
  const list = route('/list/Customer', '/list/:schemaName/:pageTitle?', {
    schemaName: 'Customer',
  });
  trackPageview(list, form);

  assert.deepEqual(posthog.captured(), [
    [
      '$pageview',
      {
        route_template: '/edit/:schemaName/:name',
        route_name: 'CommonForm',
        schema_name: 'SalesInvoice',
      },
    ],
    [
      '$pageview',
      {
        route_template: '/list/:schemaName/:pageTitle?',
        schema_name: 'Customer',
      },
    ],
  ]);
  assert.equal(JSON.stringify(posthog.calls).includes(CUSTOMER), false);
});

// covers: AC-5
test('a failed navigation and a query only change send no pageview', async () => {
  await startAnalytics(BOOT, '16.1.0');
  const list = route('/list/Customer', '/list/:schemaName/:pageTitle?', {
    schemaName: 'Customer',
  });
  trackPageview(list, START, { type: 4 });
  trackPageview(list, list);

  assert.deepEqual(posthog.captured(), []);
});

// covers: AC-8
test('the early queue keeps the newest 50 events', () => {
  for (let index = 0; index < QUEUE_LIMIT + 5; index++) {
    track('doc_created', { schema_name: `Schema${index}` });
  }
  assert.equal(getQueueLength(), QUEUE_LIMIT);
});

// covers: AC-6
test('before_send leaves no record name in a pageview URL, title or referrer', () => {
  const url = `${ORIGIN}/books/edit/Customer/${encodeURIComponent(CUSTOMER)}?tab=1#top`;
  const event = scrubEvent(
    {
      uuid: '1',
      event: '$pageview',
      properties: {
        route_template: '/edit/:schemaName/:name',
        $current_url: url,
        $pathname: `/books/edit/Customer/${CUSTOMER}`,
        $title: `${CUSTOMER} - RareBooks`,
        $referrer: `${ORIGIN}/books/edit/Customer/${CUSTOMER}`,
        $referring_domain: 'duka.rarebooks.cc',
        $initial_current_url: url,
        $session_entry_url: url,
        $prev_pageview_pathname: `/books/edit/Customer/${CUSTOMER}`,
        $host: 'duka.rarebooks.cc',
      },
      $set_once: { $initial_current_url: url, $initial_pathname: url },
      $set: { $current_url: url },
    },
    ORIGIN
  );

  assert.equal(
    event.properties.$current_url,
    `${ORIGIN}/books/edit/:schemaName/:name`
  );
  assert.equal(event.properties.$pathname, '/books/edit/:schemaName/:name');
  assert.equal(event.properties.$host, 'duka.rarebooks.cc');
  for (const key of ['$title', '$referrer', '$referring_domain']) {
    assert.equal(key in event.properties, false, key);
  }
  const sent = JSON.stringify(event);
  assert.equal(sent.includes('Mama'), false);
  assert.equal(sent.includes('Asha'), false);
});

// covers: AC-6
test('other events use the route of the last pageview', () => {
  trackPageview(
    route(`/print/SalesInvoice/${CUSTOMER}`, '/print/:schemaName/:name', {
      schemaName: 'SalesInvoice',
    }),
    START
  );
  const event = scrubEvent(
    {
      uuid: '2',
      event: 'print_opened',
      properties: {
        schema_name: 'SalesInvoice',
        $current_url: `${ORIGIN}/books/print/SalesInvoice/${CUSTOMER}`,
      },
    },
    ORIGIN
  );
  assert.equal(
    event.properties.$current_url,
    `${ORIGIN}/books/print/:schemaName/:name`
  );
});

// covers: AC-6, AC-9
test('before_send keeps only the exception type, and the server details', () => {
  const message = `Customer ${CUSTOMER} not found`;
  const event = scrubEvent(
    {
      uuid: '3',
      event: '$exception',
      properties: {
        exc_type: 'DoesNotExistError',
        status: 404,
        $exception_list: [
          { type: 'Error', value: message, stacktrace: { frames: [] } },
        ],
        $exception_values: [message],
        $exception_message: message,
        $exception_type: 'Error',
      },
    },
    ORIGIN
  );

  assert.equal(
    event.properties.$exception_list[0].value,
    'Error (DoesNotExistError, 404)'
  );
  assert.deepEqual(event.properties.$exception_values, [
    'Error (DoesNotExistError, 404)',
  ]);
  assert.equal(JSON.stringify(event).includes('Asha'), false);
});

// covers: AC-9
test('a stored server error is captured with its exc_type and status', async () => {
  await startAnalytics(BOOT, '16.1.0');
  const error = Object.assign(new Error(`No ${CUSTOMER}`), {
    excType: 'DoesNotExistError',
    status: 404,
  });
  captureError(error);

  const [call] = posthog.calls.filter(([name]) => name === 'captureException');
  assert.equal(call[1], error);
  assert.deepEqual(call[2], { exc_type: 'DoesNotExistError', status: 404 });
});

// covers: AC-11
test('a PostHog that fails to load warns once and turns analytics off', async () => {
  setLoader(async () => {
    throw new Error('blocked by the browser');
  });
  track('doc_created', { schema_name: 'Entry' });

  await startAnalytics(BOOT, '16.1.0');
  track('doc_created', { schema_name: 'Entry' });
  captureError(new TypeError('boom'));

  assert.equal(warnings.length, 1);
  assert.equal(getQueueLength(), 0);
});

/** A server that inserts, submits and cancels Books Entry, or refuses with `refuse`. */
function stubEntryServer({ refuse } = {}) {
  stubFrappe(({ method, path, body }) => {
    if (refuse) {
      return { status: 417, body: { errors: [{ message: refuse }] } };
    }
    if (body.method) {
      const docstatus = body.method === 'submit' ? 1 : 2;
      return { docs: [{ ...body.document, docstatus, modified: MODIFIED }] };
    }
    if (method === 'POST' && path.endsWith('/Books Entry')) {
      return { data: { ...body, modified: MODIFIED, docstatus: 0 } };
    }
    return { data: { ...body, modified: MODIFIED } };
  });
}

// covers: AC-7
test('a new doc sends doc_created once, then doc_submitted and doc_cancelled, with only its schema name', async () => {
  await startAnalytics(BOOT, '16.1.0');
  stubEntryServer();
  const entry = newFrappeDoc('Entry', { name: 'ENT-0001', party: CUSTOMER });

  await Promise.all([entry.sync(), entry.sync()]);
  await entry.sync();
  await entry.submit();
  await entry.cancel();

  assert.deepEqual(posthog.captured(), [
    ['doc_created', { schema_name: 'Entry' }],
    ['doc_submitted', { schema_name: 'Entry' }],
    ['doc_cancelled', { schema_name: 'Entry' }],
  ]);
});

// covers: AC-7
test('a failed save and a settings single send nothing', async () => {
  await startAnalytics(BOOT, '16.1.0');
  stubEntryServer({ refuse: 'Party is required' });
  const entry = newFrappeDoc('Entry', { name: 'ENT-0002' });
  await assert.rejects(entry.sync(), /Party is required/);

  stubEntryServer();
  const settings = newFrappeDoc('EntrySettings', { note: 'Hello' });
  await loadSaved(settings, { modified: MODIFIED });
  await settings.set('note', 'Changed');
  stubEntryServer();
  await settings.sync();

  assert.deepEqual(posthog.captured(), []);
});
