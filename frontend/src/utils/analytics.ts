/**
 * Product analytics through PostHog (spec 0027).
 *
 * The only module that imports `posthog-js`, and only with a dynamic import
 * once the app has started, so a site with analytics off never fetches the
 * chunk (AC-3). Nothing here names a record: pageviews carry the route
 * template, events carry only the schema name, and `scrubEvent` rewrites
 * every URL and error message before it leaves the browser (AC-6).
 */
import type {
  CaptureResult,
  PostHog,
  PostHogConfig,
  Properties,
} from 'posthog-js';
import type { NavigationFailure, RouteLocationNormalized } from 'vue-router';

/** `bootinfo.books.analytics`, built by `frappe_books.analytics.boot_block` (AC-1). */
export interface AnalyticsBoot {
  key: string;
  distinct_id: string;
  site_key: string;
  roles: string[];
  country_code: string;
  language: string;
}

type Loader = () => Promise<PostHog>;
type Pending =
  | { kind: 'event'; event: string; properties: Properties }
  | { kind: 'error'; error: unknown; properties: Properties };

export const API_HOST = 'https://eu.i.posthog.com';
export const UI_HOST = 'https://eu.posthog.com';
export const QUEUE_LIMIT = 50;
const BOOKS_BASE = '/books';
// Properties posthog-js adds that can hold a URL, a page title or a referrer.
const DROPPED_KEY =
  /^\$(title|referrer|referring_domain|initial_|session_entry_|prev_pageview_)/;
const URL_KEYS = new Set(['$current_url', '$pathname']);

let boot: AnalyticsBoot | null | undefined;
let client: PostHog | null = null;
let failed = false;
let started = false;
let queue: Pending[] = [];
let routeTemplate = '/';
// Errors already sent by `captureError`, so autocapture doesn't send them again (AC-9).
let captured = new WeakSet<object>();
let loader: Loader = async () => (await import('posthog-js')).default;

/** Reads the boot block once; undefined until the session boot is there. */
function getBoot(): AnalyticsBoot | null {
  boot ??= window.frappe?.boot?.books?.analytics ?? null;
  return boot;
}

function isOn(): boolean {
  return !failed && !!getBoot();
}

/**
 * Loads PostHog for a signed in shop user, after the app has mounted (AC-3).
 * Never throws and never shows anything: a load failure logs one warning and
 * turns analytics off for the session (AC-11).
 */
export async function startAnalytics(
  block: AnalyticsBoot | null | undefined,
  appVersion: string
): Promise<void> {
  boot = block ?? null;
  if (!boot || started || failed) {
    queue = [];
    return;
  }

  started = true;
  listenForCapturedErrors();
  try {
    const posthog = await loader();
    posthog.init(boot.key, getInitOptions());
    posthog.identify(boot.distinct_id, {
      books_roles: boot.roles,
      language: boot.language,
    });
    posthog.group('site', boot.site_key);
    posthog.register({
      site_key: boot.site_key,
      country_code: boot.country_code,
      app_version: appVersion,
    });
    client = posthog;
    flushQueue();
  } catch (error) {
    turnOff(error);
  }
}

/** The exact init options of AC-4. */
export function getInitOptions(): Partial<PostHogConfig> {
  return {
    api_host: API_HOST,
    ui_host: UI_HOST,
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
    before_send: (event) => scrubEvent(event, window.location.origin),
  };
}

/** Sends a usage event; queued until PostHog loads, dropped when analytics is off (AC-8). */
export function track(event: string, properties: Properties = {}): void {
  if (!isOn()) {
    return;
  }

  try {
    if (client) {
      client.capture(event, properties);
      return;
    }
    enqueue({ kind: 'event', event, properties });
  } catch (error) {
    turnOff(error);
  }
}

/** Reports a stored error: only its type and stack, plus `exc_type` and status for a server error (AC-9). */
export function captureError(error: unknown): void {
  if (!isOn()) {
    return;
  }

  if (error && typeof error === 'object') {
    captured.add(error);
  }
  const properties = getServerErrorProperties(error);
  try {
    if (client) {
      client.captureException(error, properties);
      return;
    }
    enqueue({ kind: 'error', error, properties });
  } catch (failure) {
    turnOff(failure);
  }
}

/**
 * One `$pageview` per completed navigation, by route template (AC-5). A failed
 * navigation and one that changes only the query string send nothing.
 */
export function trackPageview(
  to: RouteLocationNormalized,
  from: RouteLocationNormalized,
  failure?: NavigationFailure | void
): void {
  if (failure) {
    return;
  }

  const template = to.matched.at(-1)?.path;
  if (!template) {
    return;
  }
  if (from.matched.length && to.path === from.path) {
    return;
  }

  routeTemplate = template;
  const properties: Properties = { route_template: template };
  if (typeof to.name === 'string') {
    properties.route_name = to.name;
  }
  const { schemaName } = to.params;
  if (typeof schemaName === 'string' && schemaName) {
    properties.schema_name = schemaName;
  }
  track('$pageview', properties);
}

/**
 * The `before_send` hook (AC-6): every URL becomes `/books<route template>`
 * with no query or hash, titles and referrers go, and an exception keeps only
 * its type, so no record name or error message leaves the site.
 */
export function scrubEvent(
  event: CaptureResult | null,
  origin: string
): CaptureResult | null {
  if (!event) {
    return event;
  }

  const properties = event.properties ?? {};
  const template =
    typeof properties.route_template === 'string'
      ? properties.route_template
      : routeTemplate;
  const pathname = `${BOOKS_BASE}${template === '/' ? '/' : template}`;
  const urls: Record<string, string> = {
    $current_url: `${origin}${pathname}`,
    $pathname: pathname,
  };

  event.properties = scrubProperties(properties, urls);
  if (event.$set) {
    event.$set = scrubProperties(event.$set, {});
  }
  if (event.$set_once) {
    event.$set_once = scrubProperties(event.$set_once, {});
  }
  if (event.event === '$exception') {
    scrubException(event.properties);
  }
  return event;
}

function scrubProperties(
  properties: Properties,
  urls: Record<string, string>
): Properties {
  const scrubbed: Properties = {};
  for (const [key, value] of Object.entries(properties)) {
    if (DROPPED_KEY.test(key)) {
      continue;
    }
    if (URL_KEYS.has(key)) {
      if (urls[key]) {
        scrubbed[key] = urls[key];
      }
      continue;
    }
    scrubbed[key] = value;
  }
  for (const [key, value] of Object.entries(urls)) {
    scrubbed[key] ??= value;
  }
  return scrubbed;
}

interface ExceptionEntry {
  type?: string;
  value?: string;
}

function scrubException(properties: Properties) {
  const label = (type?: string) => getErrorLabel(type, properties);
  const list = properties.$exception_list as ExceptionEntry[] | undefined;
  const types: (string | undefined)[] = [];
  if (Array.isArray(list)) {
    for (const entry of list) {
      types.push(entry.type);
      entry.value = label(entry.type);
    }
  }

  const values = properties.$exception_values as unknown[] | undefined;
  if (Array.isArray(values)) {
    properties.$exception_values = values.map((_, index) =>
      label(types[index] ?? (properties.$exception_types as string[])?.[index])
    );
  }
  if ('$exception_message' in properties) {
    properties.$exception_message = label(
      properties.$exception_type as string | undefined
    );
  }
}

/** `TypeError`, or `Error (DoesNotExistError, 404)` for a server error. */
function getErrorLabel(type: string | undefined, properties: Properties) {
  const name = type || 'Error';
  const details = [properties.exc_type, properties.status].filter(
    (value) => value !== undefined && value !== null && value !== ''
  );
  return details.length ? `${name} (${details.join(', ')})` : name;
}

function getServerErrorProperties(error: unknown): Properties {
  const { excType, status } = (error ?? {}) as {
    excType?: string;
    status?: number;
  };
  const properties: Properties = {};
  if (excType) {
    properties.exc_type = excType;
  }
  if (status) {
    properties.status = status;
  }
  return properties;
}

function enqueue(item: Pending) {
  queue.push(item);
  if (queue.length > QUEUE_LIMIT) {
    queue.shift();
  }
}

function flushQueue() {
  const pending = queue;
  queue = [];
  for (const item of pending) {
    if (item.kind === 'event') {
      client!.capture(item.event, item.properties);
    } else {
      client!.captureException(item.error, item.properties);
    }
  }
}

function turnOff(error: unknown) {
  if (!failed) {
    // The one warning AC-11 allows; analytics never shows the user anything.
    // eslint-disable-next-line no-console
    console.warn('Usage analytics is off for this session', error);
  }
  failed = true;
  client = null;
  queue = [];
}

/**
 * posthog-js wraps `window.onerror` and `window.onunhandledrejection`. These
 * listeners are added first, so they run before those handlers and stop an
 * error `captureError` already sent from being sent again (AC-9).
 */
function listenForCapturedErrors() {
  if (typeof window.addEventListener !== 'function') {
    return;
  }
  window.addEventListener('error', (event) => {
    if (isCaptured(event.error)) {
      event.stopImmediatePropagation();
    }
  });
  window.addEventListener('unhandledrejection', (event) => {
    if (isCaptured(event.reason)) {
      event.stopImmediatePropagation();
    }
  });
}

function isCaptured(error: unknown): boolean {
  return !!error && typeof error === 'object' && captured.has(error);
}

/** For tests: replaces the posthog-js import. */
export function setLoader(value: Loader) {
  loader = value;
}

/** For tests: forgets the boot block, the client and the queue. */
export function resetAnalytics() {
  boot = undefined;
  client = null;
  failed = false;
  started = false;
  queue = [];
  routeTemplate = '/';
  captured = new WeakSet();
}

/** For tests: what waits for PostHog to load. */
export function getQueueLength(): number {
  return queue.length;
}
