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
