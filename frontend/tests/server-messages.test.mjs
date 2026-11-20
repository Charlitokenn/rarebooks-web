import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { setImmediate } from 'node:timers/promises';
import {
  FrappeDoc,
  call,
  frappeApi,
  loadFrappeDocTypes,
  newFrappeDoc,
  parseServerMessages,
  registerFrappeModels,
  showServerMessages,
  stubFrappe,
  toast,
} from './helpers/frappe.mjs';

// Spec 0006: a message sent with a successful write shows as a toast.

/** Every toast shown since the last reset, as `{ type, message, id, duration }`. */
const shown = [];
for (const type of ['info', 'success', 'warning', 'error', 'loading']) {
  toast[type] = (message, options = {}) =>
    shown.push({ type, message, id: options.id, duration: options.duration });
}

beforeEach(() => {
  shown.length = 0;
});

/** The toasts after the request and its on demand toast module have settled. */
async function settled() {
  await setImmediate();
  await setImmediate();
  return shown;
}

const warning = {
  message: 'EXP-0001 already has reference R-77 for Acme.',
  title: 'Possible duplicate',
  indicator: 'orange',
};

const doc = { doctype: 'Books Expense', name: 'EXP-0002' };

/** Answers every request successfully, with `messages` beside its data. */
function answerWith(messages) {
  return stubFrappe(() => ({ data: doc, docs: [doc], messages }));
}

const writes = [
  ['an insert', () => frappeApi.insertDocument('Books Expense', {})],
  ['a save', () => frappeApi.updateDocument('Books Expense', 'EXP-0002', {})],
  ['a delete', () => frappeApi.deleteDocument('Books Expense', 'EXP-0002')],
  ['a submit', () => frappeApi.runDocMethod('submit', doc)],
  ['a cancel', () => frappeApi.runDocMethod('cancel', doc)],
];

for (const [name, write] of writes) {
  test(`${name} that succeeds shows the server's messages`, async () => {
    answerWith([warning]);
    await write();
    assert.deepEqual(await settled(), [
      {
        type: 'warning',
        message: warning.message,
        id: `server-message:${warning.message}`,
        duration: Infinity,
      },
    ]);
  });
}

test('a GET read shows no messages', async () => {
  answerWith([warning]);
  await frappeApi.getDocument('Books Expense', 'EXP-0002');
  await frappeApi.getDocuments('Books Expense', {});
  assert.deepEqual(await settled(), []);
});

test('a quiet doc method shows no messages', async () => {
  answerWith([warning]);
  await frappeApi.runDocMethod('preview', doc, undefined, { quiet: true });
  assert.deepEqual(await settled(), []);
});

test("the form's preview shows no messages, as it runs on every change", async () => {
  class Note extends FrappeDoc {
    static doctype = 'Books Note';
    static previewMethod = 'preview';
  }

  const noteMeta = {
    name: 'Books Note',
    autoname: 'hash',
    permissions: [],
    fields: [{ fieldname: 'text', fieldtype: 'Data', label: 'Text' }],
  };
  const requests = stubFrappe(({ path, body }) => {
    if (path.endsWith('get_books_meta')) {
      return { message: { metas: [noteMeta], placements: {} } };
    }

    return { data: null, docs: [body.document], messages: [warning] };
  });
  registerFrappeModels({ Note });
  await loadFrappeDocTypes();

  const note = newFrappeDoc('Note');
  await note.set('text', 'Hello');
  await note.preview();

  assert.ok(requests.some(({ path }) => path.endsWith('run_doc_method')));
  assert.deepEqual(await settled(), []);
});

test('a failed write leaves its messages to the thrown error', async () => {
  stubFrappe(() => ({
    status: 417,
    body: { errors: [{ message: 'No' }], messages: [warning] },
  }));
  await assert.rejects(frappeApi.insertDocument('Books Expense', {}));
  assert.deepEqual(await settled(), []);
});

test('the same text twice in one response shows once', async () => {
  answerWith([warning, { ...warning, indicator: undefined }, { message: ' ' }]);
  await frappeApi.insertDocument('Books Expense', {});
  assert.equal((await settled()).length, 1);
});

test('each distinct message shows its own toast', async () => {
  answerWith([warning, { message: 'Second note' }]);
  await frappeApi.insertDocument('Books Expense', {});
  assert.deepEqual(
    (await settled()).map(({ message }) => message),
    [warning.message, 'Second note']
  );
});

const indicators = [
  ['orange', 'warning', Infinity],
  ['yellow', 'warning', Infinity],
  ['red', 'error', Infinity],
  ['green', 'success', 5_000],
  ['blue', 'info', 5_000],
  [undefined, 'info', 5_000],
];

for (const [indicator, type, duration] of indicators) {
  test(`indicator ${indicator ?? 'missing'} shows a ${type} toast`, async () => {
    answerWith([{ message: 'Note', indicator }]);
    await frappeApi.insertDocument('Books Expense', {});
    const [shownToast] = await settled();
    assert.equal(shownToast.type, type);
    assert.equal(shownToast.duration, duration);
  });
}

test('parseServerMessages reads JSON entries, plain strings and unparseable text', () => {
  assert.deepEqual(
    parseServerMessages([
      JSON.stringify({ message: 'Saved', indicator: 'green' }),
      JSON.stringify('A plain string'),
      'not json {',
    ]),
    [
      { message: 'Saved', indicator: 'green' },
      { message: 'A plain string' },
      { message: 'not json {' },
    ]
  );
  assert.deepEqual(parseServerMessages(), []);
});

test('a call() with _server_messages shows the same toasts', async () => {
  globalThis.fetch = async () =>
    Response.json({
      message: 'ok',
      _server_messages: JSON.stringify([
        JSON.stringify({ message: 'RareBooks setup is complete.', alert: 1 }),
      ]),
    });
  assert.equal(await call('frappe_books.setup'), 'ok');
  assert.deepEqual(await settled(), [
    {
      type: 'info',
      message: 'RareBooks setup is complete.',
      id: 'server-message:RareBooks setup is complete.',
      duration: 5_000,
    },
  ]);
});

test('a toast that fails to show is logged, and the save still succeeds', async (t) => {
  const failure = new Error('Toaster is gone');
  t.mock.method(toast, 'warning', () => {
    throw failure;
  });
  const logged = t.mock.method(console, 'error', () => {});
  const unhandled = [];
  const onUnhandled = (reason) => unhandled.push(reason);
  process.on('unhandledRejection', onUnhandled);
  t.after(() => process.off('unhandledRejection', onUnhandled));
  answerWith([warning]);

  const saved = await frappeApi.insertDocument('Books Expense', {});
  await settled();

  assert.equal(saved.name, 'EXP-0002');
  assert.deepEqual(unhandled, []);
  assert.equal(logged.mock.callCount(), 1);
  assert.equal(logged.mock.calls[0].arguments.at(-1), failure);
});

test('showServerMessages never rejects', async (t) => {
  t.mock.method(toast, 'info', () => {
    throw new Error('Toaster is gone');
  });
  t.mock.method(console, 'error', () => {});

  await assert.doesNotReject(showServerMessages([{ message: 'Note' }]));
});

test('whitespace duplicates keep the first indicator and response order', async () => {
  await showServerMessages([
    { message: '  Saved  ', indicator: 'green' },
    { message: 'Second', indicator: 'orange' },
    { message: 'Saved', indicator: 'red' },
  ]);

  assert.deepEqual(shown, [
    {
      type: 'success',
      message: 'Saved',
      id: 'server-message:Saved',
      duration: 5_000,
    },
    {
      type: 'warning',
      message: 'Second',
      id: 'server-message:Second',
      duration: Infinity,
    },
  ]);
});

test('invalid message entries do not hide a later valid message', async () => {
  await showServerMessages([
    null,
    undefined,
    {},
    { message: 42 },
    { message: '' },
    { message: '\n\t ' },
    { message: 'Valid' },
  ]);

  assert.deepEqual(
    shown.map(({ message }) => message),
    ['Valid']
  );
});

test('an unknown indicator falls back to an informational toast', async () => {
  await showServerMessages([
    { message: 'Notice', indicator: 'purple', alert: 1 },
  ]);
  assert.deepEqual(shown, [
    {
      type: 'info',
      message: 'Notice',
      id: 'server-message:Notice',
      duration: 5_000,
    },
  ]);
});

test('deduplication is per response and repeated messages reuse the toast id', async () => {
  await showServerMessages([warning]);
  await showServerMessages([warning]);

  assert.equal(shown.length, 2);
  assert.equal(shown[0].id, shown[1].id);
});

test('a write without messages succeeds without showing a toast', async () => {
  answerWith(undefined);
  assert.equal(
    (await frappeApi.insertDocument('Books Expense', {})).name,
    doc.name
  );
  assert.deepEqual(await settled(), []);
});

test('malformed JSON message values are discarded before displaying toasts', async () => {
  await showServerMessages(
    parseServerMessages([
      'null',
      '42',
      'false',
      '{}',
      '[]',
      JSON.stringify({ message: 'Saved', indicator: 'green' }),
    ])
  );

  assert.deepEqual(
    shown.map(({ message }) => message),
    ['Saved']
  );
});
