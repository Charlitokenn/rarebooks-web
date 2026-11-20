# 0006. Show server messages from successful requests as toasts

**Date**: 2026-11-17
**Status**: Accepted

## Summary

When the server saves something but also has something to say (a `msgprint`, Frappe's way of sending a message along with a response), /books shows that message as a toast, the small notice in the corner. Warnings and errors stay until you close them; other messages fade after five seconds. Today /books drops these messages on every form, so the expense duplicate reference warning (spec 0004, AC-7) never reaches you. One place in the request layer handles this for every form, so no screen needs its own code.

## Context

Frappe lets a controller attach messages to a response that still succeeds: `frappe.msgprint(...)` adds an entry to `frappe.local.message_log`, and Frappe returns the list with the response. Desk shows each entry, as a toast when the call passed `alert=True` and as a modal dialog otherwise. The shape depends on the API version. `/api/v2` (which /books uses for documents and doc methods through `frontend/src/frappe/api.ts`) returns `messages`, the raw `message_log` entries: objects with a `message` string and optional `title`, `indicator` and `alert`. That includes a `DELETE`, which answers 202. `/api/method` (which /books reaches through frappe-ui's `call()` in `frontend/src/web/api.ts`) returns `_server_messages`, a JSON string holding a list of JSON strings.

/books reads neither on success. `request()` in `src/frappe/api.ts` returns only `data`. frappe-ui's `call()` returns only `message`, and passes `_server_messages` to a `serverMessagesHandler` only when one is configured. /books configures none, and frappe-ui calls that handler only for successful responses. Messages are read only from failed responses, where they become the thrown error. A message attached to a successful save is therefore lost on every form.

Two messages exist today. The expense controller warns that a supplier's reference was already used on a submitted expense (spec 0004, AC-7): the save must succeed and the user must see the warning. It sends no indicator yet. The setup wizard sends "RareBooks setup is complete." with `alert=True`. The verify run for spec 0004 confirmed the first is lost: the server sends it in `messages`, and the page shows only "EXP-1049 saved". Any later controller that warns without blocking would hit the same gap.

Constraints: business rules and their messages live in the Python controller (root `AGENTS.md`); the client only shows them. The server translates the text with `_()`, so the client must not translate it again. A document form runs its model's `previewMethod` on every field change, so a message from the preview would repeat as the user types. Frappe's own messages can contain HTML (`<strong>`, links), and frappe-ui's toast already sanitizes its message with DOMPurify, keeping only `a`, `em`, `strong`, `i`, `b` and `u`. The node tests run without a DOM, and they stub the server through `stubFrappe` (`tests/helpers/frappe.mjs`).

## Options considered

### Option 1: A toast for every message, typed by its indicator, from one handler in the request layer

The request layer passes every message from a successful write (and from `call()`) to one function, which shows one toast per distinct message. Frappe's `indicator` picks the toast type, and warnings and errors stay until closed.

**Pros**:
- Matches how /books already confirms a save (a toast), so nothing new interrupts the user.
- One place to change; every form and every later controller message works with no screen code.
- A warning that stays until closed can't slip by.

**Cons**:
- Ignores Desk's split between `alert` toasts and modal msgprints, so a message the server meant as a dialog shows as a toast.
- A controller that wants its toast to persist must set an orange, yellow or red indicator; with none, the message fades after five seconds.

### Option 2: Follow Desk (toast for `alert=True`, dialog otherwise)

Show `alert=True` messages as toasts and every other msgprint as a modal dialog the user must close, as Desk does.

**Pros**:
- The same behaviour as Desk, so a controller written for Desk reads the same in /books.
- A plain msgprint is impossible to miss.

**Cons**:
- Interrupts every save that warns, which slows down quick entry, above all on a phone.
- Two presentations to build and test.

### Option 3: Always a dialog

Every server message opens a dialog.

**Pros**:
- The most visible, and the simplest single rule for "the user must see this".

**Cons**:
- The most interrupting; even "setup is complete" needs a click.
- Out of step with how /books confirms saves today.

### Option 4: Each screen reads the messages it cares about

The expense form (and any later form) reads `messages` from its own save and shows them.

**Pros**:
- No change to shared code; nothing else in /books changes behaviour.

**Cons**:
- Every new controller message needs matching screen code, or it is lost again; the gap this spec closes stays open by default.
- Each screen invents its own presentation.

## Decision

**Chosen option**: Option 1: a toast for every message, typed by its indicator, from one handler in the request layer.

Every message the server returns with a successful write through `/api/v2` (insert, save, delete, submit and cancel, but not the form's preview), and with a successful `call()`, shows as a toast. There is one toast per distinct message, the type comes from the indicator, warnings and errors stay until closed, and the toast's own sanitizer handles any markup.

## Rationale

The forces are a warning that must reach the user without blocking the save (AC-7 in spec 0004), quick entry where expenses are logged on the spot, and a codebase where business messages come from controllers, not screens. A toast fits all three: /books already uses one to confirm the save, it doesn't stop the user, and a warning toast that stays until closed is as hard to miss as a dialog without the interruption. Desk's dialog split (Option 2) suits a desk user at a keyboard. It would add a second presentation and a click to every warned save. A dialog for everything (Option 3) costs the same click for messages that only inform.

Handling the messages once in the request layer (rather than Option 4's per screen code) is what ends the gap. Today a controller message is lost unless someone remembers the client side; a central handler makes "shown" the default. The cost is that a controller now controls how long its message stays, through the indicator. That is the field Desk uses for colour, so a controller written correctly for Desk does the right thing in /books.

The message goes to the toast as the server sent it. frappe-ui's toast already sanitizes with DOMPurify, so bold and safe links survive and anything else is dropped. Stripping tags in /books would add code and lose that formatting for no extra safety. The preview call is excluded because it runs on every field change: a controller that msgprints during preview would otherwise repeat its message as the user types. Messages from failed responses are left to the existing error path, which already shows them as the error.

## Standard definition

**Canonical pattern** (client, one module, called by the two request layers only):

```ts
// frontend/src/frappe/serverMessages.ts
export interface ServerMessage {
  message: string;
  title?: string; // not shown
  indicator?: string; // Frappe's colour: orange, yellow, red, green, blue, ...
  alert?: boolean | number; // ignored: every message is a toast
}

/** Shows each distinct message from a successful response as a toast. */
export async function showServerMessages(
  messages: ServerMessage[] = []
): Promise<void> {
  const distinct = [...new Set(messages.map((m) => m.message?.trim()).filter(Boolean))];
  if (!distinct.length) return;
  // Loaded on demand, as `showPreviewError` does, so the request layer and node tests don't pull in Vue.
  const { showToast } = await import('src/utils/interactive');
  for (const text of distinct) {
    const { indicator } = messages.find((m) => m.message?.trim() === text)!;
    const type = getToastType(indicator); // orange|yellow → warning, red → error, green → success, missing or other → info
    showToast({
      id: `server-message:${text}`, // a repeat on a later request replaces the shown toast
      message: text, // frappe-ui's toast sanitizes it with DOMPurify
      type,
      duration: type === 'warning' || type === 'error' ? 'until_closed' : 'long',
    });
  }
}

/** frappe-ui's `_server_messages`: JSON strings, or a plain string that fails to parse. */
export function parseServerMessages(raw: string[] = []): ServerMessage[] {
  return raw.map((entry) => {
    try {
      const value = JSON.parse(entry);
      return typeof value === 'string' ? { message: value } : value;
    } catch {
      return { message: entry };
    }
  });
}
```

```ts
// frontend/src/frappe/api.ts
// request(method, path, { body, params, quiet }) — after a successful response:
//   if (method !== 'GET' && !options.quiet) void showServerMessages(body.messages);
// ResponseBody gains `messages?: ServerMessage[]`.
// runDocMethod(method, document, kwargs, { quiet }) passes `quiet` through.
// Covered: insertDocument (POST), updateDocument (PUT), deleteDocument (DELETE),
// runDocMethod for submit, cancel and cancel_with_linked_docs.

// frontend/src/frappe/document.ts:1119, the preview call (the model's previewMethod) is the only quiet one:
//   api.runDocMethod(this.previewMethod!, document, kwargs, { quiet: true })

// frontend/src/web/api.ts, at module load (this module owns call(), so the hook is set before any call):
//   setConfig('serverMessagesHandler', (raw: string[]) => void showServerMessages(parseServerMessages(raw)));
```

```ts
// frontend/src/utils/ui.ts and interactive.ts: a duration that stays without the loading spinner
export const toastDurationMap = { short: 2_500, long: 5_000, very_long: Infinity, until_closed: Infinity } as const;
// showToast: 'very_long' keeps toast.loading; 'until_closed' uses the typed toast (warning, error, ...) with an
// Infinity duration. frappe-ui's Toaster already shows a close button on every toast.
```

```py
# A controller that warns without blocking sets the indicator, so the toast stays:
frappe.msgprint(
	_("{0} already has reference {1} for {2}.").format(other, self.reference_number, self.party),
	title=_("Possible duplicate"),
	indicator="orange",
)
```

Behaviour the build follows:
- **Which requests**: successful `POST`, `PUT` and `DELETE` through `request()`, and every successful `call()` response that carries `_server_messages`. Never a GET read, never the form's preview call, never a failed response.
- **Fields**: `message` is the text, shown as the server sent it (already translated). A missing `indicator` means info. `title` is not shown (a toast shows one line, and Frappe's default title "Message" adds nothing). `alert` is ignored.
- **Repeats**: identical text in one response shows once. The toast id is the text, so the same message on a later request (a save, then a submit) replaces the shown toast instead of stacking. That is intended.
- **Order**: no promise between a server message toast and the caller's own toast (such as "EXP-0001 saved"). Both show, and a warning stays after the other fades.
- **Layout**: the existing Toaster (bottom corner, three visible, the same on a phone); this spec changes nothing about it.

**Replaces**:
- Dropping `messages` from successful `/api/v2` responses in `request()`.
- Dropping `_server_messages` from successful `call()` responses (no `serverMessagesHandler` set).
- Any screen reading a response's messages itself; screens never handle server messages.

**Enforcement**:
Structural: only the two request layers (`request()` in `src/frappe/api.ts`, and the `serverMessagesHandler` set in `src/web/api.ts`) call `showServerMessages`, so every caller gets it without code of its own. Tests lock it:
- Node, `frontend/tests/server-messages.test.mjs` (server stubbed with `stubFrappe`): a successful insert, save, delete, submit and cancel that carry `messages` show toasts; the preview call and a GET do not; repeats in one response merge; each indicator maps to its type, and a missing one to info; warnings and errors use `'until_closed'`; `parseServerMessages` handles JSON entries, plain strings and unparseable text; a `call()` response with `_server_messages` reaches the same toasts.
- Browser, `frontend/tests/ui/expense.spec.ts`: the duplicate reference warning shows after a save and the expense is saved (spec 0004, AC-7).
- Python, `test_books_expense.py`: the duplicate warning's `message_log` entry carries `indicator` orange.

A review convention covers the server side: a controller message meant to warn sets `indicator="orange"` (or red for something worse).

**Rollout**:
New code immediately, in one change: the module, both request layers, the toast duration, the expense indicator and the tests, built as spec 0004's build plan task 7. No migration; nothing handled these messages before.

**Exceptions**:
- The form's preview call (runs on every field change) and GET reads.
- Failed responses: their messages already show through the thrown error and keep doing so.
- A `call()` whose response carries `docs`: frappe-ui returns it before reading `_server_messages`. No /books call does this today.
- Server side Data Import: rows are imported by a background job, and its messages go to the import log, not the browser.

## Consequences

**Positive**:
- The expense duplicate warning reaches the user, and the save still goes through (spec 0004, AC-7).
- Any later controller message shows on every form with no screen code.
- The setup wizard's "RareBooks setup is complete." now shows as an info toast.

**Negative / tradeoffs**:
- A message the server meant as a blocking dialog in Desk shows as a toast in /books. A controller that needs the user to acknowledge something must refuse the save (throw) instead.
- Several distinct messages in one response stack several toasts, and the Toaster shows three at a time.
- A warning stays on screen until closed, which is one more tap for a user who has already read it.
- The message's markup is limited to what the toast's DOMPurify allows (bold, italic, underline, links).

**Neutral**:
- `toastDurationMap` gains `until_closed`; `'very_long'` keeps its loading toast for the cases that use it.
- frappe-ui's `serverMessagesHandler` becomes part of /books, set where `call()` lives.

## Follow-up

- [ ] Build it as spec 0004's build plan task 7 (`/develop expenses`).
- [ ] `/sync` adds the rule to `frontend/AGENTS.md` (screens never handle server messages; a warning msgprint sets an indicator) and to `frappe_books/AGENTS.md`.
- [ ] Check the Toaster's fixed 360px width on narrow phones (an existing layout, not changed here).
