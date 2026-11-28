import { t } from 'fyo';
import { SiteLockedError } from 'fyo/utils/errors';
import type * as FirebaseApp from 'firebase/app';
import type { FirebaseOptions } from 'firebase/app';
import type * as FirebaseMessaging from 'firebase/messaging';
import type { Messaging } from 'firebase/messaging';
import { handleErrorWithDialog } from 'src/errorHandling';
import { fyo } from 'src/initFyo';
import { showToast } from 'src/utils/interactive';
import { subscriptionStatus } from 'src/utils/refs';
import { getLockNotice } from 'src/utils/subscription';
import { call } from 'src/web/api';
import { ref } from 'vue';

/** `bootinfo.books.push`: the public Firebase config, or null when push is off (spec 0026 AC-1, AC-12). */
export interface PushBoot {
  web_config: FirebaseOptions;
  vapid_key: string;
}

/**
 * What the app menu shows for this device (AC-2): nothing, the Home Screen hint on an iPhone that
 * did not open /books from the Home Screen, or the turn on or turn off entry.
 */
export type PushState = 'hidden' | 'needs_install' | 'off' | 'on';

export const TOKEN_KEY_PREFIX = 'books_push_token:';
const REGISTER_METHOD = 'frappe_books.notifications.register_device';
const UNREGISTER_METHOD = 'frappe_books.notifications.unregister_device';
const SERVICE_WORKER = '/books/sw.js';
const SCOPE = '/books/';
const LABEL_LIMIT = 140;
const SIGN_OUT_TIMEOUT = 2_000;

type Firebase = {
  app: Pick<typeof FirebaseApp, 'initializeApp' | 'getApps'>;
  messaging: Pick<
    typeof FirebaseMessaging,
    'getMessaging' | 'getToken' | 'deleteToken'
  >;
};

/** Firebase loads only when push is used, so other screens never download it. */
let loadFirebase = async (): Promise<Firebase> => {
  const [app, messaging] = await Promise.all([
    import('firebase/app'),
    import('firebase/messaging'),
  ]);
  return { app, messaging };
};

let push: PushBoot | null = null;
let messaging: Promise<Messaging> | null = null;
/** Bumped on every change, so the menu reads the state again. */
const version = ref(0);

/** Stored at startup from the session boot, beside the support chat. */
export function setPush(value: PushBoot | null | undefined) {
  push = value ?? null;
  messaging = null;
  version.value += 1;
}

/** Push is set up on this site for this user, so the Settings dialog shows its tab (AC-8). */
export function hasPush(): boolean {
  return !!push;
}

/** The entry this device shows in the app menu (AC-2). */
export function getPushState(): PushState {
  void version.value;
  if (!push) {
    return 'hidden';
  }

  if (!isPushSupported()) {
    return isIOS() && !isStandalone() ? 'needs_install' : 'hidden';
  }

  return Notification.permission === 'granted' && readStoredToken()
    ? 'on'
    : 'off';
}

/** Picking "Turn on notifications": the browser's own prompt shows only now, after the click. */
export async function turnOnPush(): Promise<void> {
  if (!push) {
    return;
  }

  if (getPushState() === 'needs_install') {
    showToast({
      id: 'push-install-first',
      type: 'info',
      duration: 'long',
      message: t`Add RareBooks to your Home Screen first, then turn on notifications from there.`,
    });
    return;
  }

  // A locked site registers nothing, so no browser subscription is made either (AC-13).
  if (subscriptionStatus.value?.locked) {
    await handleErrorWithDialog(
      new SiteLockedError(getLockNotice(subscriptionStatus.value)),
      undefined,
      true
    );
    return;
  }

  const permission = await Notification.requestPermission();
  if (permission === 'denied') {
    showBlocked();
    return;
  }
  if (permission !== 'granted') {
    return;
  }

  try {
    await register();
  } catch (error) {
    await handleErrorWithDialog(error, undefined, true);
    return;
  } finally {
    version.value += 1;
  }

  showToast({
    id: 'push-on',
    type: 'success',
    message: t`Notifications are on for this device.`,
  });
}

/** Picking "Turn off notifications" (AC-4). */
export async function turnOffPush(): Promise<void> {
  await stopPush();
  showToast({
    id: 'push-off',
    type: 'success',
    message: t`Notifications are off for this device.`,
  });
}

/**
 * Before the Frappe sign out, so the next person on this browser never gets this user's pushes
 * (AC-4). Never throws and never takes more than two seconds, so sign out always goes on.
 */
export async function stopPushForSignOut(): Promise<void> {
  if (!push || !readStoredToken()) {
    return;
  }

  await withTimeout(stopPush().catch(logPushError), SIGN_OUT_TIMEOUT);
}

/**
 * At every /books start on a device that was turned on: register again, sending the token stored
 * last time, so a token FCM rotated replaces the old row (AC-3). Skipped on a locked site.
 */
export async function refreshPushRegistration(): Promise<void> {
  if (getPushState() !== 'on' || subscriptionStatus.value?.locked) {
    return;
  }

  try {
    await register();
  } catch (error) {
    // Permission revoked or the server refused: the entry reads "Turn on" again.
    logPushError(error);
  } finally {
    version.value += 1;
  }
}

async function register() {
  const token = await getFcmToken();
  const previous = readStoredToken();
  await call(REGISTER_METHOD, {
    token,
    previous_token: previous && previous !== token ? previous : null,
    device_label: getDeviceLabel(navigator.userAgent, navigator.maxTouchPoints),
  });
  storeToken(token);
}

/** Removes the browser subscription first: a locked site can't delete the row, but pushes stop (AC-13). */
async function stopPush() {
  const token = readStoredToken();
  removeStoredToken();
  version.value += 1;
  await removeSubscription();
  if (token) {
    try {
      await call(UNREGISTER_METHOD, { token });
    } catch (error) {
      // FCM answers UNREGISTERED for the token now, which deletes the row later.
      logPushError(error);
    }
  }
}

async function getFcmToken(): Promise<string> {
  const { getToken } = (await loadFirebase()).messaging;
  const registration = await getServiceWorker();
  return getToken(await getMessaging(), {
    vapidKey: push!.vapid_key,
    serviceWorkerRegistration: registration,
  });
}

async function removeSubscription() {
  try {
    const { deleteToken } = (await loadFirebase()).messaging;
    await deleteToken(await getMessaging());
  } catch (error) {
    logPushError(error);
  }

  // Whatever Firebase managed, the browser must not keep a subscription for this user.
  try {
    const registration = await navigator.serviceWorker.getRegistration(SCOPE);
    const subscription = await registration?.pushManager.getSubscription();
    await subscription?.unsubscribe();
  } catch (error) {
    logPushError(error);
  }
}

function getMessaging(): Promise<Messaging> {
  messaging ??= (async () => {
    const firebase = await loadFirebase();
    const { initializeApp, getApps } = firebase.app;
    const { getMessaging } = firebase.messaging;
    const app = getApps()[0] ?? initializeApp(push!.web_config);
    // No onMessage handler: the service worker shows every push, so the page never doubles it (AC-11).
    return getMessaging(app);
  })();
  return messaging;
}

/** The /books service worker shows the notification; no firebase-messaging-sw.js is ever requested. */
async function getServiceWorker(): Promise<ServiceWorkerRegistration> {
  const registration = await navigator.serviceWorker.register(SERVICE_WORKER, {
    scope: SCOPE,
  });
  // Not `serviceWorker.ready`: the page at /books sits outside the /books/ scope, so it never resolves.
  await whenActive(registration);
  return registration;
}

function whenActive(registration: ServiceWorkerRegistration): Promise<void> {
  const worker = registration.installing ?? registration.waiting;
  if (registration.active || !worker) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    worker.addEventListener('statechange', () => {
      if (worker.state === 'activated' || worker.state === 'redundant') {
        resolve();
      }
    });
  });
}

export function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

function isIOS(): boolean {
  const { userAgent, maxTouchPoints } = navigator;
  // iPadOS reports a Mac user agent with touch support.
  return (
    /iphone|ipad|ipod/i.test(userAgent) ||
    (/macintosh/i.test(userAgent) && maxTouchPoints > 1)
  );
}

function isStandalone(): boolean {
  return (
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

/** "{browser} on {OS}", for example "Safari on iOS" (AC-3). */
export function getDeviceLabel(userAgent: string, maxTouchPoints = 0): string {
  const browser =
    match(userAgent, [
      [/edg(e|a|ios)?\//i, 'Edge'],
      [/opr\/|opera/i, 'Opera'],
      [/samsungbrowser/i, 'Samsung Internet'],
      [/firefox|fxios/i, 'Firefox'],
      [/chrome|crios|chromium/i, 'Chrome'],
      [/safari/i, 'Safari'],
    ]) ?? 'Browser';
  const isIPad = /macintosh/i.test(userAgent) && maxTouchPoints > 1;
  const os =
    (isIPad ? 'iOS' : null) ??
    match(userAgent, [
      [/android/i, 'Android'],
      [/iphone|ipad|ipod/i, 'iOS'],
      [/windows/i, 'Windows'],
      [/cros/i, 'ChromeOS'],
      [/macintosh|mac os x/i, 'macOS'],
      [/linux/i, 'Linux'],
    ]) ??
    'an unknown system';
  return `${browser} on ${os}`.slice(0, LABEL_LIMIT);
}

function match(text: string, patterns: [RegExp, string][]): string | null {
  return patterns.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

function showBlocked() {
  showToast({
    id: 'push-blocked',
    type: 'warning',
    duration: 'until_closed',
    message: t`Notifications are blocked. Allow them for this site in your browser settings.`,
  });
}

function getTokenKey(): string {
  return TOKEN_KEY_PREFIX + (fyo.user ?? '');
}

function readStoredToken(): string | null {
  try {
    return globalThis.localStorage?.getItem(getTokenKey()) ?? null;
  } catch {
    return null;
  }
}

function storeToken(token: string) {
  try {
    globalThis.localStorage?.setItem(getTokenKey(), token);
  } catch {
    // Storage may be blocked; the entry then reads "Turn on" on the next start.
  }
}

function removeStoredToken() {
  try {
    globalThis.localStorage?.removeItem(getTokenKey());
  } catch {
    // Storage may be blocked; nothing to clear.
  }
}

function withTimeout<T>(promise: Promise<T>, timeout: number) {
  return Promise.race([
    promise,
    new Promise<void>((resolve) => setTimeout(resolve, timeout)),
  ]);
}

function logPushError(error: unknown) {
  if (error) {
    console.error('Push notifications:', error);
  }
}

/** Replaces the Firebase modules, for tests. */
export function stubFirebase(loader: () => Promise<Firebase>) {
  loadFirebase = loader;
  messaging = null;
}
