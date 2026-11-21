import { expect, test, type Page } from '@playwright/test';
import { insertDocument } from './helpers/records';
import { useBooksSession, waitForBooks } from './helpers/session';
import {
  bench,
  benchExecute,
  expectNoSidewaysScroll,
  getStatus,
  setPhase,
  signInAsBooksUser,
  site,
  waitForPhase,
} from './helpers/subscription';

// Every phase of spec 0005 on desktop and on a phone (AC-19, rechecking AC-2 to AC-16).
test.skip(!bench || !site, 'Requires an explicit Frappe test bench and site');
useBooksSession();

const PHONE = {
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
};
const LAYOUTS = [
  { name: 'desktop', use: {} },
  { name: 'phone', use: PHONE },
];

const LOCKED =
  /^Your books are read only\. Subscribe by .+ to keep this site\. After that it is removed and a copy of your data is emailed to the owner\.$/;
// A lapsed site names its removal date too (spec 0007 AC-2).
const LAPSED =
  /^Your books are read only\. Renew by .+ to keep this site\. After that it is removed and a copy of your data is emailed to the owner\.$/;
// Once the export email went out, the banner names the end of the hold (spec 0007 AC-8).
const HOLDING =
  /^Your books are read only\. A copy of your data was emailed to the owner\. This site will be removed after (.+)\.$/;
const PENDING =
  'Payment pending. The lock lifts as soon as your payment is confirmed.';
const ASK = 'Ask your administrator to subscribe.';
const BILLING_DOWN = "Couldn't reach billing. Try again.";
const ISO_DATE = /\d{4}-\d{2}-\d{2}/;

const banner = (page: Page) => page.getByTestId('subscription-banner');
const bannerText = (page: Page) => banner(page).locator('p').first();
const lockDialog = (page: Page) =>
  page.getByRole('dialog', { name: 'Read only' });

test.afterAll(() =>
  benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site')
);

async function open(page: Page, path: string) {
  await page.goto(path);
  await waitForBooks(page);
}

async function openSubscription(page: Page) {
  await open(page, '/books/subscription');
  await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible();
}

/** The banner fits the screen, and its Subscribe button is in reach (AC-19). */
async function expectBannerFits(page: Page) {
  const box = await banner(page).boundingBox();
  const width = page.viewportSize()!.width;
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(width);
  const subscribe = banner(page).getByRole('button', { name: 'Subscribe' });
  if (await subscribe.count()) {
    await expect(subscribe).toBeInViewport({ ratio: 1 });
  }
  await expectNoSidewaysScroll(page);
}

async function openNav(page: Page, isPhone: boolean) {
  if (isPhone) {
    await page.getByRole('button', { name: 'Menu' }).click();
    return page.getByRole('dialog', { name: 'Books' });
  }
  return page.locator('body');
}

for (const layout of LAYOUTS) {
  const isPhone = layout.name === 'phone';

  test.describe(layout.name, () => {
    test.use(layout.use);
    test.setTimeout(150_000);

    test('a trial site has full access and shows its trial dates', async ({
      page,
    }) => {
      await setPhase(page, 'trial');
      await open(page, '/books');
      await expect(banner(page)).toHaveCount(0);

      const nav = await openNav(page, isPhone);
      await nav.getByRole('link', { name: 'Subscription' }).click();
      await expect(page).toHaveURL(/\/books\/subscription$/);
      await expect(
        page.getByRole('heading', { name: 'Free trial' })
      ).toBeVisible();
      await expect(page.getByTestId('trial-days-left')).toHaveText('21');
      for (const testid of ['trial-ends-on', 'lock-starts-on']) {
        await expect(page.getByTestId(testid)).not.toHaveText(ISO_DATE);
        await expect(page.getByTestId(testid)).not.toBeEmpty();
      }
      await expectNoSidewaysScroll(page);
    });

    test('the prompt counts down and hides until the next site day', async ({
      page,
    }) => {
      await setPhase(page, 'prompt');
      await open(page, '/books');
      await expect(bannerText(page)).toHaveText(
        '3 days left to subscribe before your books turn read only.'
      );
      await expectBannerFits(page);

      await banner(page).getByRole('button', { name: 'Dismiss' }).click();
      await expect(banner(page)).toHaveCount(0);
      await open(page, '/books');
      await expect(banner(page)).toHaveCount(0);

      // A dismissal from an earlier site day no longer hides it.
      await page.evaluate(() =>
        localStorage.setItem(
          'books_subscription_banner_dismissed',
          '2000-01-01'
        )
      );
      await open(page, '/books');
      await banner(page).getByRole('button', { name: 'Subscribe' }).click();
      await expect(page).toHaveURL(/\/books\/subscription$/);
      await expect(page.getByTestId('trial-days-left')).toHaveText('0');
    });

    test('a PayPal subscription waiting to start shows its start day and no Subscribe', async ({
      page,
    }) => {
      // covers: spec 0008 AC-21
      await setPhase(page, 'waiting');
      await open(page, '/books');
      await expect(banner(page)).toHaveCount(0);

      await open(page, '/books/subscription');
      await expect(page.getByTestId('subscription-starts-on')).toHaveText(
        /^Your subscription starts on \S+\.$/
      );
      await expect(page.getByTestId('subscription-starts-on')).not.toHaveText(
        ISO_DATE
      );
      await expect(page.getByTestId('subscription-plans')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Subscribe' })).toHaveCount(
        0
      );
      await expectNoSidewaysScroll(page);
    });

    test('a missing first PayPal payment says so, keeps Subscribe hidden and brings the prompt back', async ({
      page,
    }) => {
      // covers: spec 0008 AC-21
      await setPhase(page, 'overdue');
      await open(page, '/books');
      await expect(banner(page)).toHaveCount(1);

      await open(page, '/books/subscription');
      await expect(page.getByTestId('subscription-starts-on')).toHaveText(
        "Your first PayPal payment hasn't arrived. Check the payment method in your PayPal account."
      );
      await expect(page.getByTestId('subscription-plans')).toHaveCount(0);
      await expectNoSidewaysScroll(page);
    });

    test('a locked site keeps reads and refuses writes with the lock notice', async ({
      page,
    }) => {
      // An existing record, to edit once locked (InReadOnlyMode, 503).
      await setPhase(page, 'trial');
      const party = `Locked Party ${layout.name} ${Date.now()}`;
      await insertDocument(page, 'Books Party', {
        name: party,
        role: 'Customer',
      });

      await setPhase(page, 'locked');
      await open(page, '/books');
      await expect(bannerText(page)).toHaveText(LOCKED);
      await expect(
        banner(page).getByRole('button', { name: 'Dismiss' })
      ).toHaveCount(0);
      await expectBannerFits(page);

      // Reads keep working (AC-6).
      await open(page, '/books/list/Party');
      await expect(page.getByText(party).first()).toBeVisible();

      if (isPhone) {
        await open(page, `/books/edit/Party/${encodeURIComponent(party)}`);
        const taxId = page.getByRole('textbox', { name: 'Tax ID' });
        await taxId.fill(`LOCK-${Date.now()}`);
        await taxId.press('Tab');
        await page
          .locator('footer')
          .getByRole('button', { name: 'Save', exact: true })
          .click();
      } else {
        // A new record (SiteLockedError, 403).
        await open(page, '/books/list/Currency');
        await page.getByRole('button', { name: 'New', exact: true }).click();
        await page
          .getByRole('textbox', {
            name: 'Currency Name (required)',
            exact: true,
          })
          .fill(`Locked Coin ${Date.now()}`);
        await page.keyboard.press('Tab');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        await page.getByRole('button', { name: 'Yes', exact: true }).click();
      }

      await expect(lockDialog(page).getByText(LOCKED)).toBeVisible();
      await expect(lockDialog(page)).toBeInViewport();
      await expectNoSidewaysScroll(page);
      await lockDialog(page).getByRole('button', { name: 'Okay' }).click();

      await banner(page).getByRole('button', { name: 'Subscribe' }).click();
      await expect(page).toHaveURL(/\/books\/subscription$/);
      await expect(
        page.getByRole('heading', { name: 'Read only' })
      ).toBeVisible();
      // The fake control site can't be reached (AC-16).
      const plans = page.getByTestId('subscription-plans');
      await expect(plans.getByRole('alert')).toContainText(BILLING_DOWN);
      await plans.getByRole('button', { name: 'Retry' }).click();
      await expect(plans.getByRole('alert')).toContainText(BILLING_DOWN);
      await expectNoSidewaysScroll(page);
    });

    test('a user who cannot subscribe is told to ask', async ({ page }) => {
      await setPhase(page, 'locked');
      await signInAsBooksUser(page);
      await open(page, '/books');
      await expect(bannerText(page)).toHaveText(LOCKED);
      await expect(banner(page)).toContainText(ASK);
      await expect(
        banner(page).getByRole('button', { name: 'Subscribe' })
      ).toHaveCount(0);
      await expectBannerFits(page);

      await openSubscription(page);
      await expect(page.getByTestId('subscription-plans')).toHaveCount(0);
    });

    test('a started checkout adds the payment pending note', async ({
      page,
    }) => {
      await setPhase(page, 'pending');
      await open(page, '/books');
      await expect(banner(page)).toContainText(PENDING);
      await expect(bannerText(page)).toHaveText(
        new RegExp(
          `^${LOCKED.source.slice(1, -1)} ${PENDING.replace(/\./g, '\\.')}$`
        )
      );
      await expectBannerFits(page);

      await openSubscription(page);
      await expect(page.getByTestId('payment-pending')).toHaveText(PENDING);
    });

    test('once the export is emailed the banner names the hold date', async ({
      page,
    }) => {
      await setPhase(page, 'holding');
      await open(page, '/books');
      await expect(bannerText(page)).toHaveText(HOLDING);
      const text = await bannerText(page).innerText();
      expect(text.match(HOLDING)![1]).not.toMatch(ISO_DATE);
      await expect(
        banner(page).getByRole('button', { name: 'Dismiss' })
      ).toHaveCount(0);
      // An administrator can still pay to keep the site.
      await expect(
        banner(page).getByRole('button', { name: 'Subscribe' })
      ).toBeVisible();
      await expectBannerFits(page);

      await openSubscription(page);
      await expect(
        page.getByRole('heading', { name: 'Read only' })
      ).toBeVisible();
      await expect(page.getByTestId('removal-on')).not.toHaveText(ISO_DATE);
      await expect(page.getByTestId('removal-on')).not.toBeEmpty();
      await expectNoSidewaysScroll(page);
    });

    test('plans start a checkout and the return refreshes the status', async ({
      page,
    }) => {
      await setPhase(page, 'locked');
      // The control site is a stub address, so its plans come from here.
      await page.route(
        '**/api/method/frappe_books.subscription.get_subscription*',
        async (route) => {
          const response = await route.fetch();
          const body = await response.json();
          Object.assign(body.message, {
            plans_error: null,
            offered_provider: 'PayPal',
            offered_periods: ['Monthly', 'Yearly'],
            plans: [
              {
                provider: 'PayPal',
                billing_period: 'Monthly',
                amount: 9,
                currency: 'USD',
                label: null,
              },
              {
                provider: 'PayPal',
                billing_period: 'Yearly',
                amount: 90,
                currency: 'USD',
                label: null,
              },
            ],
          });
          await route.fulfill({ response, json: body });
        }
      );

      await openSubscription(page);
      const monthly = page.getByTestId('plan-Monthly');
      await expect(monthly).toContainText('Monthly');
      await expect(monthly).toContainText('a month');
      await expect(page.getByTestId('plan-Yearly')).toContainText('a year');
      await expectNoSidewaysScroll(page);

      // The real start_checkout can't reach the stub address either (AC-16).
      await monthly.getByRole('button', { name: 'Subscribe' }).click();
      await expect(
        page.getByTestId('subscription-plans').getByRole('alert')
      ).toHaveText(BILLING_DOWN);

      await page.route(
        '**/api/method/frappe_books.subscription.start_checkout*',
        (route) =>
          route.fulfill({
            json: {
              message: {
                checkout_url: '/books/subscription?checkout=returned',
              },
            },
          })
      );
      const pull = page.waitForRequest(
        (request) =>
          request.url().includes('get_subscription') &&
          (request.postData() ?? request.url()).includes('refresh')
      );
      await monthly.getByRole('button', { name: 'Subscribe' }).click();
      await pull;
      await expect(page).toHaveURL(/\/books\/subscription$/);
    });

    test('a paid site shows its renewal, renew soon, grace and lapsed texts', async ({
      page,
    }) => {
      await setPhase(page, 'active');
      await open(page, '/books');
      await expect(banner(page)).toHaveCount(0);
      await openSubscription(page);
      await expect(
        page.getByRole('heading', { name: 'Subscribed' })
      ).toBeVisible();
      await expect(page.getByTestId('renews-on')).not.toHaveText(ISO_DATE);
      await expect(page.getByTestId('subscription-plans')).toHaveCount(0);

      await setPhase(page, 'renew_soon');
      await openSubscription(page);
      const paidUntil = await page.getByTestId('paid-until').innerText();
      expect(paidUntil).not.toMatch(ISO_DATE);
      await expect(bannerText(page)).toHaveText(
        `Your subscription ends on ${paidUntil}. Renew to keep full access.`
      );
      await expectBannerFits(page);

      await setPhase(page, 'grace');
      await openSubscription(page);
      await expect(
        page.getByRole('heading', { name: 'Subscription ended' })
      ).toBeVisible();
      const endedOn = await page.getByTestId('ended-on').innerText();
      const renewBy = await page.getByTestId('renew-by').innerText();
      await expect(bannerText(page)).toHaveText(
        `Your subscription ended on ${endedOn}. Renew by ${renewBy} to keep full access.`
      );
      await expect(
        banner(page).getByRole('button', { name: 'Dismiss' })
      ).toBeVisible();
      await expectBannerFits(page);

      await setPhase(page, 'lapsed');
      await openSubscription(page);
      await expect(
        page.getByRole('heading', { name: 'Read only' })
      ).toBeVisible();
      await expect(page.getByTestId('renew-by')).toHaveCount(0);
      await expect(bannerText(page)).toHaveText(LAPSED);
      await expect(
        banner(page).getByRole('button', { name: 'Dismiss' })
      ).toHaveCount(0);
      // A lapsed site has a removal date now (spec 0007 AC-2), shown in the user's date format.
      expect((await getStatus(page)).removal_on).toMatch(ISO_DATE);
      await expect(page.getByTestId('removal-on')).not.toHaveText(ISO_DATE);
      await expect(page.getByTestId('removal-on')).not.toBeEmpty();
      await expectBannerFits(page);
    });

    test('an exempt site shows no banner and no Subscription item', async ({
      page,
    }) => {
      await setPhase(page, 'exempt');
      await open(page, '/books');
      await expect(banner(page)).toHaveCount(0);
      const nav = await openNav(page, isPhone);
      await expect(nav.getByRole('link', { name: 'Dashboard' })).toBeVisible();
      await expect(nav.getByRole('link', { name: 'Subscription' })).toHaveCount(
        0
      );
      await open(page, '/books/subscription');
      await expect(
        page.getByText('This site is not on a hosted plan.')
      ).toBeVisible();
    });
  });
}

test('a self hosted site is never locked and shows nothing', async ({
  page,
}) => {
  test.setTimeout(150_000);
  await benchExecute('frappe_books.tests.subscription.unlock_self_hosted_site');
  await waitForPhase(page, 'unmanaged');
  await open(page, '/books');
  await expect(banner(page)).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Subscription' })).toHaveCount(0);
  await open(page, '/books/subscription');
  await expect(
    page.getByText('This site is not on a hosted plan.')
  ).toBeVisible();
});
