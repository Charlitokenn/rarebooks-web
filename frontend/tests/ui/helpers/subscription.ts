import { expect, type Page } from '@playwright/test';
import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';

// Setting a phase needs `bench execute`; see frappe_books/tests/subscription.py.
export const bench = process.env.BOOKS_FILTER_TEST_BENCH;
export const site = process.env.BOOKS_FILTER_TEST_SITE;

export type TestPhase =
  | 'trial'
  | 'prompt'
  | 'locked'
  | 'pending'
  | 'holding'
  | 'active'
  | 'renew_soon'
  | 'grace'
  | 'lapsed'
  | 'exempt';

/** The phase `get_subscription` reports for each test phase. */
const SERVER_PHASE: Record<TestPhase, string> = {
  trial: 'trial',
  prompt: 'prompt',
  locked: 'locked',
  pending: 'locked',
  holding: 'locked',
  active: 'active',
  renew_soon: 'renew_soon',
  grace: 'grace',
  lapsed: 'lapsed',
  exempt: 'exempt',
};

export const BOOKS_USER = {
  usr: 'books-user@example.com',
  pwd: 'Books-User-Test-1',
};

export async function benchExecute(
  method: string,
  options: { args?: unknown[]; kwargs?: Record<string, unknown> } = {}
) {
  const argv = ['--site', site!, 'execute', method];
  if (options.args) {
    argv.push('--args', JSON.stringify(options.args));
  }
  if (options.kwargs) {
    argv.push('--kwargs', JSON.stringify(options.kwargs));
  }
  await promisify(execFile)('bench', argv, {
    cwd: bench,
    env: {
      ...process.env,
      PYTHONPATH: path.resolve(__dirname, '../../../..'),
    },
  });
}

/** Makes the site hosted and puts it in `phase`, then waits until the web workers see it. */
export async function setPhase(page: Page, phase: TestPhase) {
  await benchExecute('frappe_books.tests.subscription.set_hosted_phase', {
    kwargs: { phase },
  });
  await waitForPhase(page, SERVER_PHASE[phase]);
}

/** Web workers cache site_config.json for 60 seconds, so a hosted or self hosted switch takes a while. */
export async function waitForPhase(page: Page, phase: string) {
  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          '/api/method/frappe_books.subscription.get_subscription'
        );
        return (await response.json()).message.phase;
      },
      { timeout: 90_000, intervals: [1_000, 2_000] }
    )
    .toBe(phase);
}

export async function getStatus(page: Page) {
  const response = await page.request.get(
    '/api/method/frappe_books.subscription.get_subscription'
  );
  return (await response.json()).message as Record<string, unknown>;
}

/** Signs this page's context in as a Books User, who can't subscribe. */
export async function signInAsBooksUser(page: Page) {
  await benchExecute('frappe_books.tests.subscription.make_user', {
    args: [BOOKS_USER.usr, 'Books User', BOOKS_USER.pwd],
  });
  await page.context().clearCookies();
  const response = await page.request.post('/api/method/login', {
    form: BOOKS_USER,
  });
  expect(response.ok()).toBe(true);
}

/** No sideways page scroll at this width (AC-19). */
export async function expectNoSidewaysScroll(page: Page) {
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}
