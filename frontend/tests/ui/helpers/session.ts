import { expect, test, type Cookie, type Page } from '@playwright/test';

/** Signs in once per file and opens Books before each test. */
export function useBooksSession(path = '/books') {
  let cookies: Cookie[];

  test.beforeAll(async ({ browser, baseURL }) => {
    const context = await browser.newContext({ baseURL });
    const response = await context.request.post('/api/method/login', {
      form: {
        usr: process.env.BOOKS_TEST_USER ?? 'Administrator',
        pwd: process.env.BOOKS_TEST_PASSWORD ?? 'admin',
      },
    });
    expect(response.ok()).toBe(true);
    cookies = await context.cookies();
    await context.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.context().addCookies(cookies);
    await page.goto(path);
    await waitForBooks(page);
  });
}

/**
 * Serves /books with rights on a DocType taken out of the boot, as for a user whose roles lack them.
 * Only the screens follow the boot; the server still answers with the signed-in user's rights.
 */
export async function withoutBootRights(
  page: Page,
  doctype: string,
  rights: ('read' | 'write')[]
) {
  await page.route('**/books**', async (route) => {
    if (route.request().resourceType() !== 'document') {
      return route.fallback();
    }

    const response = await route.fetch();
    const html = await response.text();
    const start = html.indexOf('frappe.boot = ') + 'frappe.boot = '.length;
    const end = html.indexOf(';\n', start);
    const boot = JSON.parse(html.slice(start, end));
    for (const right of rights) {
      const key = `can_${right}`;
      boot.user[key] = boot.user[key].filter(
        (name: string) => name !== doctype
      );
    }
    const body = html.slice(0, start) + JSON.stringify(boot) + html.slice(end);
    await route.fulfill({ response, body });
  });
}

export async function waitForBooks(page: Page) {
  await page.locator('header').first().waitFor();
}
