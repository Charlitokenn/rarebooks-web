import { t } from 'fyo';
import router from 'src/router';
import { showToast } from 'src/utils/interactive';
import { subscriptionStatus } from 'src/utils/refs';

/** `bootinfo.books.support_chat`, signed by the server (spec 0009). */
export interface SupportChat {
  property_id: string;
  widget_id: string;
  visitor: { name: string; email: string; hash: string };
  /** company, site, roles, app-version; empty values are left out. */
  attributes: Record<string, string>;
  support_email?: string;
}

type TawkCallback = (error?: unknown) => void;

/** The parts of the tawk.to JavaScript API /books uses. */
interface TawkApi {
  visitor?: SupportChat['visitor'];
  onLoad?: () => void;
  onChatMinimized?: () => void;
  onChatHidden?: () => void;
  hideWidget?: () => void;
  showWidget?: () => void;
  maximize?: () => void;
  setAttributes?: (
    attributes: Record<string, string>,
    callback?: TawkCallback
  ) => void;
  logout?: (callback?: TawkCallback) => void;
}

declare global {
  interface Window {
    Tawk_API?: TawkApi;
    Tawk_LoadStart?: Date;
  }
}

type LoaderState = 'idle' | 'loading' | 'ready' | 'failed';

export const SCRIPT_ID = 'books-support-chat';
export const STORED_EMAIL_KEY = 'books_support_chat_email';
const LOAD_TIMEOUT = 10_000;
const LOGOUT_TIMEOUT = 2_000;
// tawk.to cuts custom attribute values at 255 characters.
const ATTRIBUTE_LIMIT = 255;

let chat: SupportChat | null = null;
let state: LoaderState = 'idle';
// A load whose generation is not the current one is ignored (a late onLoad).
let generation = 0;
let pendingLoad: Promise<boolean> | null = null;

/** Stored at startup from the session boot, beside the subscription status. */
export function setSupportChat(value: SupportChat | null | undefined) {
  chat = value ?? null;
}

/** Chat entries show only when the server turned the chat on for this user. */
export function hasSupportChat(): boolean {
  return !!chat;
}

/** Opens the tawk.to chat, loading its script on the first pick (AC-3). */
export async function openSupportChat(): Promise<void> {
  if (!chat) {
    return;
  }

  const pickAttributes = getPickAttributes();
  if (state === 'ready') {
    const api = getApi();
    api.setAttributes?.(pickAttributes, logTawkError);
    showChat(api);
    return;
  }

  pendingLoad ??= loadChat(chat, pickAttributes);
  await pendingLoad;
}

/** Ends this browser's tawk.to session before the Frappe sign out (AC-9). */
export async function endSupportChat(): Promise<void> {
  const deadline = Date.now() + LOGOUT_TIMEOUT;
  if (state === 'loading' && pendingLoad) {
    await withTimeout(pendingLoad, LOGOUT_TIMEOUT);
  }

  if (state === 'ready') {
    await logoutTawk(getApi(), Math.max(deadline - Date.now(), 0));
  }
  removeStoredEmail();
}

/** `phase` and `screen` as they are at the pick, since the boot can be stale (AC-5). */
function getPickAttributes(): Record<string, string> {
  return compactAttributes({
    phase: subscriptionStatus.value?.phase,
    screen: '/books' + router.currentRoute.value.path,
  });
}

function loadChat(
  current: SupportChat,
  pickAttributes: Record<string, string>
): Promise<boolean> {
  const loadGeneration = ++generation;
  state = 'loading';

  return new Promise<boolean>((resolve) => {
    const isCurrent = () =>
      loadGeneration === generation && state === 'loading';
    const fail = () => {
      if (!isCurrent()) {
        return;
      }
      clearTimeout(timer);
      state = 'failed';
      pendingLoad = null;
      document.getElementById(SCRIPT_ID)?.remove();
      showLoadFailed(current.support_email);
      resolve(false);
    };

    // A fresh API object per load, so nothing from a failed load lingers.
    const api: TawkApi = { visitor: { ...current.visitor } };
    api.onLoad = () => {
      if (!isCurrent()) {
        return;
      }
      clearTimeout(timer);
      state = 'ready';
      void startChat(api, current, pickAttributes).finally(() => {
        pendingLoad = null;
        resolve(true);
      });
    };
    api.onChatMinimized = () => api.hideWidget?.();
    api.onChatHidden = () => api.hideWidget?.();
    window.Tawk_API = api;
    window.Tawk_LoadStart = new Date();

    const timer = setTimeout(fail, LOAD_TIMEOUT);
    const script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = `https://embed.tawk.to/${encodeURIComponent(current.property_id)}/${encodeURIComponent(current.widget_id)}`;
    script.charset = 'UTF-8';
    script.setAttribute('crossorigin', '*');
    script.onerror = fail;
    document.head.appendChild(script);
  });
}

async function startChat(
  api: TawkApi,
  current: SupportChat,
  pickAttributes: Record<string, string>
) {
  api.hideWidget?.();
  // A session that expired without a sign out may still hold another user's chat.
  const previousEmail = readStoredEmail();
  if (previousEmail && previousEmail !== current.visitor.email) {
    await logoutTawk(api, LOGOUT_TIMEOUT);
    api.setAttributes?.({ ...current.visitor }, logTawkError);
  }
  storeEmail(current.visitor.email);
  api.setAttributes?.(
    { ...current.attributes, ...pickAttributes },
    logTawkError
  );
  showChat(api);
}

function showChat(api: TawkApi) {
  api.showWidget?.();
  api.maximize?.();
}

function getApi(): TawkApi {
  return window.Tawk_API ?? {};
}

function logoutTawk(api: TawkApi, timeout: number): Promise<void> {
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, timeout);
    const done: TawkCallback = (error) => {
      logTawkError(error);
      clearTimeout(timer);
      resolve();
    };
    try {
      if (!api.logout) {
        done();
        return;
      }
      api.logout(done);
    } catch (error) {
      done(error);
    }
  });
}

function showLoadFailed(supportEmail?: string) {
  const message = supportEmail
    ? t`Chat could not load. Write to ${supportEmail}.`
    : t`Chat could not load. Please try again later.`;
  showToast({
    id: 'support-chat-failed',
    type: 'warning',
    duration: 'until_closed',
    message,
  });
}

function compactAttributes(
  values: Record<string, string | null | undefined>
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values)
      .filter((entry): entry is [string, string] => !!entry[1])
      .map(([key, value]) => [key, value.slice(0, ATTRIBUTE_LIMIT)])
  );
}

function withTimeout<T>(promise: Promise<T>, timeout: number) {
  return Promise.race([
    promise,
    new Promise<void>((resolve) => setTimeout(resolve, timeout)),
  ]);
}

function logTawkError(error?: unknown) {
  if (error) {
    console.error('tawk.to:', error);
  }
}

function readStoredEmail(): string | null {
  try {
    return globalThis.localStorage?.getItem(STORED_EMAIL_KEY) ?? null;
  } catch {
    return null;
  }
}

function storeEmail(email: string) {
  try {
    globalThis.localStorage?.setItem(STORED_EMAIL_KEY, email);
  } catch {
    // Storage may be blocked; the guard is skipped, never fatal.
  }
}

function removeStoredEmail() {
  try {
    globalThis.localStorage?.removeItem(STORED_EMAIL_KEY);
  } catch {
    // Storage may be blocked; nothing to clear.
  }
}

/** Puts the loader back to its first state, for tests. */
export function resetSupportChat() {
  chat = null;
  state = 'idle';
  generation += 1;
  pendingLoad = null;
}
